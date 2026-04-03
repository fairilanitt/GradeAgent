from __future__ import annotations

import base64
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from browser_use import Agent, BrowserSession
from browser_use.skill_cli.utils import find_chrome_executable, get_chrome_profile_path

from app.config import Settings, get_settings
from app.schemas.api import (
    BrowserTaskCreate,
    BrowserTaskResult,
    ExamSessionGradingAgentOutput,
    ExamSessionGradingTaskCreate,
    ExamSessionGradingTaskResult,
    QueueGradingAgentOutput,
    QueueGradingTaskCreate,
    QueueGradingTaskResult,
)
from app.services.llm_provider import ProviderConfigurationError, build_browser_use_llm, normalize_provider


class BrowserNavigationService:
    DIRECT_PROFILE_PREFIX = "browser-use-user-data-dir-"
    SYSTEM_TEMP_PREFIXES = (
        "browser_use_agent_",
        "browser-use-downloads-",
        "browser-use-user-data-dir-",
        "browseruse-tmp-",
    )
    CHROME_AUTH_BOOTSTRAP_ITEMS = (
        "Cookies",
        "Cookies-journal",
        "Network",
        "Local Storage",
        "Session Storage",
        "IndexedDB",
        "Shared Storage",
        "Login Data",
        "Login Data For Account",
        "Web Data",
    )

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _artifact_dir(self) -> Path:
        artifact_dir = Path("artifacts/browser")
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return artifact_dir

    def _chrome_profile_directory(self) -> str | None:
        profile_directory = self.settings.browser_chrome_profile_directory
        if profile_directory is None:
            return None
        profile_directory = profile_directory.strip()
        return profile_directory or None

    def _profile_directory_name(self) -> str:
        return self._chrome_profile_directory() or "Default"

    def _persistent_profile_root(self) -> Path:
        configured_dir = self.settings.browser_persistent_profile_dir
        if configured_dir:
            profile_root = Path(configured_dir)
        else:
            profile_root = self._artifact_dir() / "browser-use-user-data-dir-gradeagent"
        if self.settings.browser_direct_persistent_profile and self.DIRECT_PROFILE_PREFIX not in str(profile_root).lower():
            profile_root = profile_root.parent / f"{self.DIRECT_PROFILE_PREFIX}{profile_root.name}"
        profile_root.mkdir(parents=True, exist_ok=True)
        return profile_root

    def _resolved_browser_agent_model(self) -> str:
        provider = normalize_provider(self.settings.browser_agent_provider)
        if provider == "google":
            from app.services.llm_provider import resolve_google_model_name

            return resolve_google_model_name(self.settings.browser_agent_model, self.settings)
        return self.settings.browser_agent_model

    def _browser_model_supports_vision(self) -> bool:
        provider = normalize_provider(self.settings.browser_agent_provider)
        if provider == "ollama":
            model_name = self._resolved_browser_agent_model().lower()
            return any(marker in model_name for marker in ("vl", "vision", "gemma3", "llava", "qwen3.5"))
        return True

    def _agent_include_attributes(self) -> list[str]:
        return ["aria-label", "placeholder"]

    def _agent_kwargs(self) -> dict:
        return {
            "use_vision": self._browser_model_supports_vision(),
            "include_attributes": self._agent_include_attributes(),
            "max_actions_per_step": self.settings.browser_agent_max_actions_per_step,
            "use_thinking": self.settings.browser_agent_use_thinking,
            "flash_mode": self.settings.browser_agent_flash_mode,
            "max_history_items": self.settings.browser_agent_max_history_items,
            "vision_detail_level": self.settings.browser_agent_vision_detail_level,
            "llm_timeout": self.settings.browser_agent_llm_timeout_seconds,
        }

    def _bootstrap_profile_from_system_chrome(self, target_root: Path) -> None:
        source_root_str = get_chrome_profile_path(None)
        if not source_root_str:
            return

        profile_directory = self._profile_directory_name()
        source_root = Path(source_root_str)
        source_profile_dir = source_root / profile_directory
        target_profile_dir = target_root / profile_directory

        if target_profile_dir.exists():
            return

        target_root.mkdir(parents=True, exist_ok=True)
        target_profile_dir.mkdir(parents=True, exist_ok=True)
        if source_profile_dir.exists():
            for item_name in self.CHROME_AUTH_BOOTSTRAP_ITEMS:
                source_path = source_profile_dir / item_name
                target_path = target_profile_dir / item_name
                if not source_path.exists() or target_path.exists():
                    continue
                if source_path.is_dir():
                    shutil.copytree(source_path, target_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(source_path, target_path)

        source_local_state = source_root / "Local State"
        target_local_state = target_root / "Local State"
        if source_local_state.exists() and not target_local_state.exists():
            shutil.copy2(source_local_state, target_local_state)

    def _build_profiled_session(
        self,
        *,
        keep_alive: bool,
        allowed_domains: list[str] | None = None,
        downloads_path: str | None = None,
    ) -> BrowserSession:
        profile_root = self._persistent_profile_root()
        executable_path: str | None = None
        if self.settings.browser_use_system_chrome:
            self._bootstrap_profile_from_system_chrome(profile_root)
            executable_path = find_chrome_executable()

        session_kwargs = {
            "headless": self.settings.browser_headless,
            "keep_alive": keep_alive,
            "allowed_domains": allowed_domains,
            "downloads_path": downloads_path,
            "user_data_dir": str(profile_root),
            "profile_directory": self._profile_directory_name(),
            "enable_default_extensions": self.settings.browser_enable_default_extensions,
        }
        if executable_path:
            session_kwargs["executable_path"] = executable_path

        return BrowserSession(
            **session_kwargs,
        )

    def _job_downloads_dir(self, job_id: str) -> Path:
        return self._artifact_dir() / f"{job_id}-downloads"

    def _job_screenshot_path(self, job_id: str) -> Path:
        return self._artifact_dir() / f"{job_id}.png"

    def _is_stale(self, path: Path, min_age_seconds: int) -> bool:
        try:
            age_seconds = time.time() - path.stat().st_mtime
        except FileNotFoundError:
            return False
        return age_seconds >= min_age_seconds

    def _path_size_bytes(self, path: Path) -> int:
        if not path.exists():
            return 0
        if path.is_file():
            return path.stat().st_size
        total_size = 0
        for child in path.rglob("*"):
            if child.is_file():
                try:
                    total_size += child.stat().st_size
                except FileNotFoundError:
                    continue
        return total_size

    def _remove_path(self, path: Path) -> int:
        removed_bytes = self._path_size_bytes(path)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
        return removed_bytes

    def cleanup_browser_artifacts(
        self,
        *,
        current_job_id: str | None = None,
        preserve_current_screenshot: bool = True,
    ) -> dict[str, int]:
        artifact_dir = self._artifact_dir()
        stale_after = max(self.settings.browser_cleanup_stale_after_seconds, 0)
        kept_screenshots = max(self.settings.browser_max_saved_screenshots, 0)
        removed_paths = 0
        removed_bytes = 0

        if current_job_id:
            current_downloads_dir = self._job_downloads_dir(current_job_id)
            if current_downloads_dir.exists():
                removed_bytes += self._remove_path(current_downloads_dir)
                removed_paths += 1

        screenshot_paths = sorted(
            artifact_dir.glob("*.png"),
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
        protected_screenshot = self._job_screenshot_path(current_job_id) if current_job_id and preserve_current_screenshot else None
        kept_count = 0
        for screenshot_path in screenshot_paths:
            if protected_screenshot is not None and screenshot_path == protected_screenshot:
                kept_count += 1
                continue
            if kept_count < kept_screenshots:
                kept_count += 1
                continue
            removed_bytes += self._remove_path(screenshot_path)
            removed_paths += 1

        for downloads_dir in artifact_dir.glob("*-downloads"):
            if current_job_id and downloads_dir == self._job_downloads_dir(current_job_id):
                continue
            if not self._is_stale(downloads_dir, stale_after):
                continue
            removed_bytes += self._remove_path(downloads_dir)
            removed_paths += 1

        temp_dir = Path(tempfile.gettempdir())
        for prefix in self.SYSTEM_TEMP_PREFIXES:
            for stale_path in temp_dir.glob(f"{prefix}*"):
                if not self._is_stale(stale_path, stale_after):
                    continue
                removed_bytes += self._remove_path(stale_path)
                removed_paths += 1

        return {
            "removed_paths": removed_paths,
            "removed_bytes": removed_bytes,
        }

    def cleanup_agent_runtime_dir(self, agent: Agent | None) -> dict[str, int]:
        if agent is None:
            return {"removed_paths": 0, "removed_bytes": 0}

        agent_directory = getattr(agent, "agent_directory", None)
        if agent_directory is None:
            return {"removed_paths": 0, "removed_bytes": 0}

        path = Path(agent_directory)
        if not path.exists():
            return {"removed_paths": 0, "removed_bytes": 0}

        removed_bytes = self._remove_path(path)
        return {
            "removed_paths": 1,
            "removed_bytes": removed_bytes,
        }

    def _build_interactive_session(self, job_id: str) -> BrowserSession:
        return self._build_profiled_session(
            keep_alive=True,
            downloads_path=str(self._job_downloads_dir(job_id)),
        )

    def _build_session(self, target_url: str, job_id: str) -> BrowserSession:
        allowed_domain = urlparse(target_url).netloc or None
        return self._build_profiled_session(
            keep_alive=False,
            allowed_domains=[allowed_domain] if allowed_domain else None,
            downloads_path=str(self._job_downloads_dir(job_id)),
        )

    async def _capture_page_state(
        self,
        browser_session: BrowserSession,
        fallback_url: str,
        screenshot_path: Path,
    ) -> tuple[str, str | None]:
        current_url = fallback_url
        extracted_text: str | None = None

        try:
            current_url = await self.get_current_page_url(browser_session) or fallback_url
        except Exception:
            current_url = fallback_url

        try:
            await browser_session.take_screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            page = await browser_session.get_current_page()
            if page is not None:
                screenshot_data = await page.screenshot()
                screenshot_path.write_bytes(base64.b64decode(screenshot_data))

        page = await browser_session.get_current_page()
        if page is not None:
            try:
                page_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
                extracted_text = page_text[:4000] if page_text else None
            except Exception:
                extracted_text = None

        return current_url, extracted_text

    async def launch_interactive_browser(
        self,
        job_id: str | None = None,
        *,
        navigate_to_start_url: bool = True,
    ) -> tuple[str, BrowserSession]:
        session_id = job_id or str(uuid4())
        browser_session = self._build_interactive_session(session_id)
        await browser_session.start()
        if navigate_to_start_url and self.settings.browser_start_url:
            await browser_session.navigate_to(self.settings.browser_start_url)
        return session_id, browser_session

    async def get_current_page_url(self, browser_session: BrowserSession) -> str | None:
        current_url = await browser_session.get_current_page_url()
        if current_url:
            return current_url

        page = await browser_session.get_current_page()
        if page is None:
            return None
        return await page.get_url()

    def build_exam_grading_task(self, payload: ExamSessionGradingTaskCreate) -> str:
        action_instruction = (
            "Do not type anything into the site. Inspect the page and explain what you would grade."
            if payload.dry_run
            else "Type only the correct numeric score values into the correct points fields."
        )
        submit_instruction = (
            "After typing scores, use the site's obvious save or next controls if needed to preserve the entered values."
            if payload.submit_after_typing
            else "Do not trigger any final publish flow. Only move as needed to continue grading."
        )
        return f"""
You are already on the correct exam grading page.

Teacher grading instructions:
{payload.instructions}

Workflow:
- Grade one vertical exercise column at a time.
- Skip dark blue exercise boxes.
- Open a box, read "Oppilaan vastaus", compare against "Mallivastaus" and the teacher rules.
- If there is one total score, type it under "Pistemäärä".
- Use the green rounded arrows to move to the next student in the same exercise.
- After the whole column is done, press "Poistu oppilaan vastauksista", then start the next column.

Multi-field exercises:
- Some exercises have multiple answer fields.
- Green auto-correct overlays should be left unchanged.
- When there are several sub-answers, enter points under "Pisteytys".
- Never exceed the faded gray max shown in each scoring field.
- If needed, use the purple rounded icon to reveal the correct answer for a sub-answer.
- Score each sub-answer separately.

Rules:
- Work from the current page state. Do not start from another URL.
- Stay inside the same exam.
- Never use browser back/history. Use only website controls.
- Use only numeric values in score inputs.
- Be conservative if unsure.
- Stop when there are no obvious ungraded boxes or when it is unsafe to continue.
- {action_instruction}
- {submit_instruction}

Return a structured summary when finished.
""".strip()

    async def navigate(self, payload: BrowserTaskCreate, job_id: str) -> BrowserTaskResult:
        agent: Agent | None = None
        try:
            provider = normalize_provider(self.settings.browser_agent_provider)
            llm = build_browser_use_llm(self.settings)
        except ProviderConfigurationError as exc:
            return BrowserTaskResult(
                job_id=job_id,
                status="failed",
                summary=str(exc),
                agent_provider=self.settings.browser_agent_provider,
                agent_model=self._resolved_browser_agent_model(),
                current_url=payload.target_url,
                screenshot_path=payload.screenshot_path,
                extracted_text=None,
                steps=[
                    {
                        "name": "configuration_check",
                        "status": "failed",
                        "detail": str(exc),
                    }
                ],
            )

        artifact_dir = self._artifact_dir()
        screenshot_path = Path(payload.screenshot_path) if payload.screenshot_path else artifact_dir / f"{job_id}.png"
        browser_session = self._build_session(payload.target_url, job_id)
        agent = Agent(
            task=(
                f"Open {payload.target_url}. {payload.instruction} "
                f"Use both the page DOM and screenshots while navigating. The active browser model provider is {provider}. "
                "Stop when the task is complete and provide a concise operator-safe summary."
            ),
            llm=llm,
            browser_session=browser_session,
            directly_open_url=True,
            **self._agent_kwargs(),
        )

        try:
            await browser_session.start()
            history = await agent.run(max_steps=25)
            current_url, extracted_text = await self._capture_page_state(
                browser_session,
                payload.target_url,
                screenshot_path,
            )

            final_result = history.final_result() or ""
            extracted_chunks = history.extracted_content()
            summary = final_result.strip() or " | ".join(extracted_chunks[:3]) or "Browser task completed."

            return BrowserTaskResult(
                job_id=job_id,
                status="completed" if history.is_successful() else "needs_review",
                summary=summary,
                agent_provider=provider,
                agent_model=self._resolved_browser_agent_model(),
                current_url=current_url,
                screenshot_path=str(screenshot_path),
                extracted_text=extracted_text,
                steps=[
                    {"name": "session_started", "status": "completed", "detail": "Browser session started."},
                    {"name": "page_opened", "status": "completed", "detail": f"Opened {payload.target_url}."},
                    {"name": "task_executed", "status": "completed", "detail": summary},
                    {"name": "artifacts_saved", "status": "completed", "detail": f"Saved screenshot to {screenshot_path}."},
                ],
            )
        except Exception as exc:  # pragma: no cover - exercised manually with real browser setup
            return BrowserTaskResult(
                job_id=job_id,
                status="failed",
                summary=f"Browser navigation failed: {exc}",
                agent_provider=provider,
                agent_model=self._resolved_browser_agent_model(),
                current_url=payload.target_url,
                screenshot_path=str(screenshot_path),
                extracted_text=None,
                steps=[
                    {
                        "name": "browser_run",
                        "status": "failed",
                        "detail": f"Browser navigation failed: {exc}",
                    }
                ],
            )
        finally:
            await browser_session.kill()
            self.cleanup_agent_runtime_dir(agent)
            self.cleanup_browser_artifacts(current_job_id=job_id)

    async def grade_queue(self, payload: QueueGradingTaskCreate, job_id: str) -> QueueGradingTaskResult:
        agent: Agent | None = None
        try:
            provider = normalize_provider(self.settings.browser_agent_provider)
            llm = build_browser_use_llm(self.settings)
        except ProviderConfigurationError as exc:
            return QueueGradingTaskResult(
                job_id=job_id,
                status="failed",
                summary=str(exc),
                agent_provider=self.settings.browser_agent_provider,
                agent_model=self._resolved_browser_agent_model(),
                current_url=payload.target_url,
                screenshot_path=payload.screenshot_path,
                extracted_text=None,
                processed_items=0,
                queue_empty=False,
                last_points_entered=None,
                last_submission_excerpt=None,
                steps=[
                    {
                        "name": "configuration_check",
                        "status": "failed",
                        "detail": str(exc),
                    }
                ],
            )

        artifact_dir = self._artifact_dir()
        screenshot_path = Path(payload.screenshot_path) if payload.screenshot_path else artifact_dir / f"{job_id}.png"
        browser_session = self._build_session(payload.target_url, job_id)
        total_points = round(sum(item.max_score for item in payload.criteria), 2)
        criteria_text = "\n".join(
            f"- {item.label}: {item.description} (max {item.max_score}, weight {item.weight})"
            for item in payload.criteria
        )
        action_instruction = (
            "Do not change the page; only explain what score you would enter and where."
            if payload.dry_run
            else "Type only the numeric score into the separate points field."
        )
        submit_instruction = (
            "After typing the number, click the obvious save/submit action for each processed item."
            if payload.submit_after_typing
            else "Do not click a final submit or save action unless it is required to keep the typed number visible."
        )

        agent = Agent(
            task=(
                f"Open {payload.target_url} and navigate the exercise queue. {payload.queue_instruction} "
                "Each exercise contains a student text submission that is only a word, phrase, or paragraph. "
                f"Teacher task title: {payload.task_title}. "
                f"Teacher criteria:\n{criteria_text}\n"
                f"Total available points: {total_points}. "
                f"Teacher strictness: {payload.preferences.strictness}. "
                f"Teacher tone: {payload.preferences.tone}. "
                f"Teacher guidance: {payload.preferences.grading_guidance}. "
                f"Points field hint: {payload.points_field_hint}. "
                f"{action_instruction} {submit_instruction} "
                f"Process at most {payload.max_items} pending exercises. "
                "Always read the submission text from the page, score it against the teacher criteria, and use only a numeric value in the points field. "
                "Skip already graded items. Return a structured summary when done."
            ),
            llm=llm,
            browser_session=browser_session,
            output_model_schema=QueueGradingAgentOutput,
            directly_open_url=True,
            **self._agent_kwargs(),
        )

        try:
            await browser_session.start()
            history = await agent.run(max_steps=max(20, payload.max_items * 8))
            current_url, extracted_text = await self._capture_page_state(
                browser_session,
                payload.target_url,
                screenshot_path,
            )
            structured = history.structured_output or history.get_structured_output(QueueGradingAgentOutput)
            if structured is None:
                structured = QueueGradingAgentOutput(
                    summary=history.final_result() or "Queue grading task completed.",
                    processed_items=0,
                    queue_empty=False,
                    last_points_entered=None,
                    last_submission_excerpt=None,
                )

            return QueueGradingTaskResult(
                job_id=job_id,
                status="completed" if history.is_successful() else "needs_review",
                summary=structured.summary,
                agent_provider=provider,
                agent_model=self._resolved_browser_agent_model(),
                current_url=current_url,
                screenshot_path=str(screenshot_path),
                extracted_text=extracted_text,
                processed_items=structured.processed_items,
                queue_empty=structured.queue_empty,
                last_points_entered=structured.last_points_entered,
                last_submission_excerpt=structured.last_submission_excerpt,
                steps=[
                    {"name": "session_started", "status": "completed", "detail": "Browser session started."},
                    {
                        "name": "queue_scanned",
                        "status": "completed",
                        "detail": f"Visited grading queue at {payload.target_url}.",
                    },
                    {
                        "name": "submissions_processed",
                        "status": "completed",
                        "detail": f"Processed {structured.processed_items} item(s).",
                    },
                    {
                        "name": "artifacts_saved",
                        "status": "completed",
                        "detail": f"Saved screenshot to {screenshot_path}.",
                    },
                ],
            )
        except Exception as exc:  # pragma: no cover - exercised manually with real browser setup
            return QueueGradingTaskResult(
                job_id=job_id,
                status="failed",
                summary=f"Queue grading failed: {exc}",
                agent_provider=provider,
                agent_model=self._resolved_browser_agent_model(),
                current_url=payload.target_url,
                screenshot_path=str(screenshot_path),
                extracted_text=None,
                processed_items=0,
                queue_empty=False,
                last_points_entered=None,
                last_submission_excerpt=None,
                steps=[
                    {
                        "name": "queue_run",
                        "status": "failed",
                        "detail": f"Queue grading failed: {exc}",
                    }
                ],
            )
        finally:
            await browser_session.kill()
            self.cleanup_agent_runtime_dir(agent)
            self.cleanup_browser_artifacts(current_job_id=job_id)

    async def grade_exam_from_current_page(
        self,
        payload: ExamSessionGradingTaskCreate,
        job_id: str,
        browser_session: BrowserSession | None = None,
    ) -> ExamSessionGradingTaskResult:
        agent: Agent | None = None
        manage_session = browser_session is None
        try:
            provider = normalize_provider(self.settings.browser_agent_provider)
            llm = build_browser_use_llm(self.settings)
        except ProviderConfigurationError as exc:
            return ExamSessionGradingTaskResult(
                job_id=job_id,
                status="failed",
                summary=str(exc),
                agent_provider=self.settings.browser_agent_provider,
                agent_model=self._resolved_browser_agent_model(),
                current_url=None,
                screenshot_path=payload.screenshot_path,
                extracted_text=None,
                steps=[{"name": "configuration_check", "status": "failed", "detail": str(exc)}],
            )

        artifact_dir = self._artifact_dir()
        screenshot_path = Path(payload.screenshot_path) if payload.screenshot_path else artifact_dir / f"{job_id}.png"
        if browser_session is None:
            browser_session = self._build_interactive_session(job_id)

        try:
            if manage_session:
                await browser_session.start()

            current_url = await self.get_current_page_url(browser_session)
            if not current_url or current_url == "about:blank":
                return ExamSessionGradingTaskResult(
                    job_id=job_id,
                    status="failed",
                    summary="Open the exam main screen in the managed browser before starting grading.",
                    agent_provider=provider,
                    agent_model=self._resolved_browser_agent_model(),
                    current_url=current_url,
                    screenshot_path=str(screenshot_path),
                    extracted_text=None,
                    steps=[
                        {
                            "name": "page_check",
                            "status": "failed",
                            "detail": "The managed browser was not on the exam main screen.",
                        }
                    ],
                )

            agent = Agent(
                task=self.build_exam_grading_task(payload),
                llm=llm,
                browser_session=browser_session,
                output_model_schema=ExamSessionGradingAgentOutput,
                directly_open_url=False,
                **self._agent_kwargs(),
            )

            history = await agent.run(max_steps=payload.max_steps)
            current_url, extracted_text = await self._capture_page_state(
                browser_session,
                current_url,
                screenshot_path,
            )
            structured = history.structured_output or history.get_structured_output(ExamSessionGradingAgentOutput)
            if structured is None:
                structured = ExamSessionGradingAgentOutput(summary=history.final_result() or "Exam grading completed.")

            return ExamSessionGradingTaskResult(
                job_id=job_id,
                status="completed" if history.is_successful() else "needs_review",
                summary=structured.summary,
                agent_provider=provider,
                agent_model=self._resolved_browser_agent_model(),
                current_url=current_url,
                screenshot_path=str(screenshot_path),
                extracted_text=extracted_text,
                processed_answers=structured.processed_answers,
                skipped_dark_blue_boxes=structured.skipped_dark_blue_boxes,
                completed_exercise_columns=structured.completed_exercise_columns,
                filled_point_fields=structured.filled_point_fields,
                current_exercise_label=structured.current_exercise_label,
                current_student_name=structured.current_student_name,
                steps=[
                    {"name": "browser_ready", "status": "completed", "detail": "Used the current exam page."},
                    {
                        "name": "grading_run",
                        "status": "completed" if history.is_successful() else "failed",
                        "detail": structured.summary,
                    },
                    {
                        "name": "artifacts_saved",
                        "status": "completed",
                        "detail": f"Saved screenshot to {screenshot_path}.",
                    },
                ],
            )
        except Exception as exc:  # pragma: no cover - exercised manually with real browser setup
            return ExamSessionGradingTaskResult(
                job_id=job_id,
                status="failed",
                summary=f"Exam grading failed: {exc}",
                agent_provider=provider,
                agent_model=self._resolved_browser_agent_model(),
                current_url=await self.get_current_page_url(browser_session) if browser_session else None,
                screenshot_path=str(screenshot_path),
                extracted_text=None,
                steps=[{"name": "grading_run", "status": "failed", "detail": f"Exam grading failed: {exc}"}],
            )
        finally:
            if manage_session and browser_session is not None:
                await browser_session.kill()
                self.cleanup_browser_artifacts(current_job_id=job_id)
            self.cleanup_agent_runtime_dir(agent)
