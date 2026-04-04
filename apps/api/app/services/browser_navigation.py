from __future__ import annotations

import base64
import asyncio
import io
import platform
import shutil
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from ollama import AsyncClient as OllamaAsyncClient
from pydantic import BaseModel, Field
from browser_use import Agent, BrowserSession
from browser_use.browser.events import SwitchTabEvent
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
from app.services.llm_provider import (
    ProviderConfigurationError,
    browser_model_supports_vision,
    build_browser_use_llm,
    extract_json_object,
    normalize_provider,
    resolve_browser_model_name,
)
from app.services.mlx_vlm_visual import MLXVLMUnavailableError, MLXVLMVisualClient


class VisualExamPageAssessment(BaseModel):
    page_kind: Literal["exam_grading", "course_contents", "login", "loading", "other"] = "other"
    confidence: int = Field(default=0, ge=0, le=100)
    page_ready: bool = False
    reason: str = ""
    visible_signals: list[str] = Field(default_factory=list)


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

    def _resolved_existing_chrome_cdp_url(self) -> str:
        configured = (self.settings.browser_existing_chrome_cdp_url or "").strip()
        if configured:
            return configured
        return f"http://127.0.0.1:{self.settings.browser_debug_port}"

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
        return resolve_browser_model_name(self.settings)

    def _browser_model_supports_vision(self) -> bool:
        if not self.settings.browser_agent_use_vision:
            return False
        return browser_model_supports_vision(
            self.settings.browser_agent_provider,
            self._resolved_browser_agent_model(),
        )

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

    def _is_usable_page_url(self, url: str | None) -> bool:
        if not url:
            return False
        normalized = url.strip().lower()
        return normalized not in {
            "about:blank",
            "chrome://newtab/",
            "chrome://new-tab-page/",
        } and not normalized.startswith("chrome://")

    def _exam_page_signal_score(self, url: str | None, title: str | None = None) -> int:
        normalized_url = (url or "").strip().lower()
        normalized_title = (title or "").strip().lower()
        if not normalized_url and not normalized_title:
            return 0

        parsed = urlparse(normalized_url) if normalized_url else urlparse("")
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        score = 0

        if "teas" in normalized_title or "teas" in normalized_url or "teas" in host:
            score += 100
        if host == "arvi.sanomapro.fi" or host.endswith(".arvi.sanomapro.fi"):
            score += 120
        elif "arvi" in host or "arvi" in normalized_url or "arvi" in normalized_title:
            score += 80

        exam_markers = (
            "exam",
            "koe",
            "piste",
            "pisteytys",
            "oppilaan vastaus",
            "arvio",
            "suoritus",
            "mallivastaus",
        )
        if any(marker in normalized_title or marker in normalized_url for marker in exam_markers):
            score += 40

        if host == "kampus.sanomapro.fi" or host.endswith(".kampus.sanomapro.fi"):
            if "/content-feed/" in path:
                score -= 120
            elif "/exam" in path or "/digikokeet" in path:
                score += 30

        launcher_markers = (
            "course contents",
            "kurssin sisalto",
            "kurssin sisältö",
            "content-feed",
            "kompassi-digikokeet",
        )
        if any(marker in normalized_title or marker in normalized_url for marker in launcher_markers):
            score -= 80

        login_markers = (
            "/auth/login",
            "/login",
            "kirjaudu",
            "sign in",
            "log in",
            "kirjaut",
        )
        if any(marker in normalized_title or marker in normalized_url for marker in login_markers):
            score -= 80
        if host == "www.sanomapro.fi" and any(marker in normalized_url for marker in ("/auth/login", "/kirjaut")):
            score -= 40

        return score

    def _is_exam_grading_page(self, url: str | None, title: str | None = None) -> bool:
        return self._exam_page_signal_score(url, title) >= 100

    async def _raw_cdp_page_targets(self, browser_session: BrowserSession) -> list[dict[str, str]]:
        cdp_client = getattr(browser_session, "_cdp_client_root", None)
        if cdp_client is None:
            return []

        send_api = getattr(cdp_client, "send", None)
        target_api = getattr(send_api, "Target", None) if send_api is not None else None
        get_targets = getattr(target_api, "getTargets", None) if target_api is not None else None
        if not callable(get_targets):
            return []

        try:
            result = await get_targets()
        except Exception:
            return []

        raw_targets = result.get("targetInfos", []) if isinstance(result, dict) else []
        page_targets: list[dict[str, str]] = []
        for target in raw_targets:
            target_type = str(target.get("type", "") or "").lower()
            if target_type not in {"page", "tab"}:
                continue
            page_targets.append(
                {
                    "target_id": str(target.get("targetId", "") or ""),
                    "title": str(target.get("title", "") or ""),
                    "url": str(target.get("url", "") or ""),
                }
            )
        return page_targets

    def _sync_session_target_metadata(
        self,
        browser_session: BrowserSession,
        *,
        target_id: str,
        url: str,
        title: str,
    ) -> None:
        if not target_id:
            return

        session_manager = getattr(browser_session, "session_manager", None)
        get_target = getattr(session_manager, "get_target", None) if session_manager is not None else None
        if not callable(get_target):
            return

        target = get_target(target_id)
        if target is None:
            return

        current_url = getattr(target, "url", "") or ""
        current_title = getattr(target, "title", "") or ""
        current_score = self._exam_page_signal_score(current_url, current_title)
        raw_score = self._exam_page_signal_score(url, title)

        if url and (not current_url or current_url == "about:blank" or raw_score >= current_score):
            target.url = url
        if title and (not current_title or current_title == "Unknown title" or raw_score >= current_score):
            target.title = title

    async def _target_known_to_session(self, browser_session: BrowserSession, target_id: str) -> bool:
        if not target_id:
            return False

        session_manager = getattr(browser_session, "session_manager", None)
        if session_manager is not None:
            get_target = getattr(session_manager, "get_target", None)
            if callable(get_target) and get_target(target_id) is not None:
                return True

        try:
            tabs = await browser_session.get_tabs()
        except Exception:
            tabs = []
        return any((getattr(tab, "target_id", "") or "") == target_id for tab in tabs)

    async def _ensure_target_known_to_session(self, browser_session: BrowserSession, target_id: str) -> bool:
        if not target_id or target_id == "current-page":
            return True
        if await self._target_known_to_session(browser_session, target_id):
            return True

        cdp_client = getattr(browser_session, "_cdp_client_root", None)
        send_api = getattr(cdp_client, "send", None) if cdp_client is not None else None
        target_api = getattr(send_api, "Target", None) if send_api is not None else None
        attach_to_target = getattr(target_api, "attachToTarget", None) if target_api is not None else None
        if not callable(attach_to_target):
            return False

        try:
            await attach_to_target(params={"targetId": target_id, "flatten": True})
        except Exception:
            pass

        for _ in range(12):
            if await self._target_known_to_session(browser_session, target_id):
                for target in await self._raw_cdp_page_targets(browser_session):
                    if target.get("target_id", "") == target_id:
                        self._sync_session_target_metadata(
                            browser_session,
                            target_id=target_id,
                            url=target.get("url", ""),
                            title=target.get("title", ""),
                        )
                return True
            await asyncio.sleep(0.1)
        return await self._target_known_to_session(browser_session, target_id)

    def _visual_exam_page_score(self, assessment: VisualExamPageAssessment) -> int:
        kind_score = {
            "exam_grading": 400,
            "course_contents": -120,
            "login": -150,
            "loading": -60,
            "other": 0,
        }.get(assessment.page_kind, 0)
        readiness_bonus = 60 if assessment.page_ready else 0
        return kind_score + readiness_bonus + assessment.confidence

    def _visual_assessment_is_exam_page(self, assessment: VisualExamPageAssessment | None) -> bool:
        if assessment is None:
            return False
        return assessment.page_kind == "exam_grading" and assessment.confidence >= 60

    def _visual_candidate_priority(self, tab: dict[str, str], index: int) -> tuple[int, int]:
        score = self._exam_page_signal_score(tab.get("url"), tab.get("title"))
        current_bias = 40 if tab.get("target_id") == "current-page" else 0
        return score + current_bias, -index

    def _resolved_visual_backend(self) -> str | None:
        backend = self.settings.browser_visual_backend
        if backend == "off":
            return None
        if backend == "mlx_vlm":
            return "mlx_vlm"
        if backend == "ollama":
            return "ollama"
        if platform.system() == "Darwin" and MLXVLMVisualClient.is_available():
            return "mlx_vlm"
        return "ollama"

    def resolved_visual_backend_label(self) -> str:
        return self._resolved_visual_backend() or "off"

    def _resolved_visual_navigation_ollama(self) -> tuple[str, str] | None:
        if self._resolved_visual_backend() != "ollama":
            return None

        provider = normalize_provider(self.settings.browser_agent_provider)
        if provider != "ollama":
            return None

        model_name = (self.settings.browser_agent_visual_model or "").strip() or self._resolved_browser_agent_model()
        if not browser_model_supports_vision(provider, model_name):
            return None

        host = self.settings.ollama_host.strip()
        if not host:
            return None
        return host, model_name

    def _resolved_visual_navigation_mlx_model(self) -> str | None:
        if self._resolved_visual_backend() != "mlx_vlm":
            return None
        model_name = self.settings.browser_visual_model.strip()
        return model_name or None

    def resolved_visual_model_label(self) -> str:
        backend = self._resolved_visual_backend()
        if backend == "ollama":
            return (self.settings.browser_agent_visual_model or "").strip() or self._resolved_browser_agent_model()
        if backend == "mlx_vlm":
            return (self.settings.browser_visual_model or "").strip() or "-"
        return "-"

    def _exam_page_visual_prompt(self) -> str:
        return """
You are classifying a screenshot from a Chrome tab during Sanoma exam grading.

Return JSON only using the provided schema.

Classification rules:
- exam_grading: the actual teacher grading or review screen where student answers can be inspected and scored.
- course_contents: a course or launcher page that may contain links such as "Kompassi-digikokeet". This is not the grading page.
- login: a sign-in or authentication page.
- loading: a blank, nearly blank, spinner, skeleton, or SPA shell that is not ready to use yet.
- other: anything else.

Visible clues for exam_grading may include labels or sections such as:
- Oppilaan vastaus
- Mallivastaus
- Pisteytys
- Pistemäärä
- teacher review panes
- next-student arrows
- scoring inputs beside student answers

Set page_ready=true only if the screenshot clearly shows the actual grading UI and it looks usable right now.
Be conservative. If uncertain, do not choose exam_grading.
""".strip()

    async def _capture_current_page_image_bytes(self, browser_session: BrowserSession) -> bytes | None:
        page = await browser_session.get_current_page()
        if page is not None:
            try:
                screenshot_data = await page.screenshot()
                if isinstance(screenshot_data, bytes) and screenshot_data:
                    return screenshot_data
                if isinstance(screenshot_data, str) and screenshot_data:
                    return base64.b64decode(screenshot_data)
            except Exception:
                pass

        temp_screenshot_path = self._artifact_dir() / f"vision-preflight-{uuid4()}.png"
        try:
            screenshot_data = await browser_session.take_screenshot(path=str(temp_screenshot_path), full_page=True)
            if isinstance(screenshot_data, bytes) and screenshot_data:
                return screenshot_data
            if temp_screenshot_path.exists():
                return temp_screenshot_path.read_bytes()
        except Exception:
            return None
        finally:
            temp_screenshot_path.unlink(missing_ok=True)

        return None

    def _downscale_visual_image_bytes(self, image_bytes: bytes) -> bytes:
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as image:
            image = image.convert("RGB")
            max_side = self.settings.browser_visual_max_image_side
            if max(image.size) > max_side:
                image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue()

    def _load_visual_pil_image(self, image_bytes: bytes):
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes))
        image.load()
        image = image.convert("RGB")
        max_side = self.settings.browser_visual_max_image_side
        if max(image.size) > max_side:
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        return image

    async def _assess_current_page_visually_with_ollama(
        self,
        browser_session: BrowserSession,
        *,
        host: str,
        model_name: str,
    ) -> VisualExamPageAssessment | None:
        image_bytes = await self._capture_current_page_image_bytes(browser_session)
        if not image_bytes:
            return None

        try:
            image_bytes = self._downscale_visual_image_bytes(image_bytes)
            response = await OllamaAsyncClient(host=host, timeout=self.settings.ollama_timeout_seconds).chat(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": self._exam_page_visual_prompt(),
                        "images": [image_bytes],
                    }
                ],
                stream=False,
                think=False,
                format=VisualExamPageAssessment.model_json_schema(),
                options={
                    "temperature": 0,
                    "num_ctx": min(self.settings.ollama_browser_num_ctx, 4096),
                    "num_predict": min(self.settings.browser_visual_max_tokens, 128),
                },
                keep_alive=self.settings.ollama_keep_alive,
            )
            content = response.message.content or ""
            return VisualExamPageAssessment.model_validate_json(content)
        except Exception:
            return None

    async def _assess_current_page_visually_with_mlx_vlm(
        self,
        browser_session: BrowserSession,
        *,
        model_name: str,
    ) -> VisualExamPageAssessment | None:
        image_bytes = await self._capture_current_page_image_bytes(browser_session)
        if not image_bytes:
            return None

        try:
            image = self._load_visual_pil_image(image_bytes)
            try:
                content = await asyncio.to_thread(
                    MLXVLMVisualClient.classify_image,
                    model_name=model_name,
                    image=image,
                    prompt=self._exam_page_visual_prompt(),
                    max_tokens=self.settings.browser_visual_max_tokens,
                )
            finally:
                image.close()
            return VisualExamPageAssessment.model_validate_json(extract_json_object(content))
        except (MLXVLMUnavailableError, ValueError):
            return None
        except Exception:
            return None

    async def _assess_current_page_visually(
        self,
        browser_session: BrowserSession,
        *,
        host: str | None = None,
        model_name: str | None = None,
    ) -> VisualExamPageAssessment | None:
        if host and model_name:
            return await self._assess_current_page_visually_with_ollama(
                browser_session,
                host=host,
                model_name=model_name,
            )

        mlx_model_name = self._resolved_visual_navigation_mlx_model()
        if mlx_model_name:
            return await self._assess_current_page_visually_with_mlx_vlm(
                browser_session,
                model_name=mlx_model_name,
            )

        resolved = self._resolved_visual_navigation_ollama()
        if resolved is None:
            return None
        return await self._assess_current_page_visually_with_ollama(
            browser_session,
            host=resolved[0],
            model_name=resolved[1],
        )

    async def _focus_best_available_page_by_vision(self, browser_session: BrowserSession) -> str | None:
        backend = self._resolved_visual_backend()
        if backend is None:
            return None

        candidates = await self._collect_tab_candidates(browser_session)
        if not candidates:
            return None

        current_url = ""
        try:
            current_url = (await browser_session.get_current_page_url()) or ""
        except Exception:
            current_url = ""

        original_target = next((tab for tab in candidates if tab.get("url") == current_url), None)
        current_candidate = original_target or (
            {
                "target_id": "current-page",
                "title": "Current page",
                "url": current_url,
            }
            if self._is_usable_page_url(current_url)
            else None
        )

        if current_candidate is not None:
            assessment = await self._assess_current_page_visually(
                browser_session,
            )
            if self._visual_assessment_is_exam_page(assessment):
                return current_candidate.get("url")
            if assessment is not None and assessment.page_kind not in {"course_contents", "login", "loading"}:
                return None

        alternative_candidates = [
            candidate
            for candidate in candidates
            if candidate is not current_candidate
            and candidate.get("url") != current_url
            and self._exam_page_signal_score(candidate.get("url"), candidate.get("title")) >= 100
        ]
        prioritized_candidates = sorted(
            enumerate(alternative_candidates),
            key=lambda item: self._visual_candidate_priority(item[1], item[0]),
            reverse=True,
        )

        best_candidate: dict[str, str] | None = None
        best_assessment: VisualExamPageAssessment | None = None
        best_score: int | None = None

        for _, candidate in prioritized_candidates[:1]:
            target_id = candidate.get("target_id", "")
            if target_id and target_id != "current-page":
                await self._ensure_target_known_to_session(browser_session, target_id)
                await self._switch_to_target(browser_session, target_id)
                await asyncio.sleep(0.15)

            assessment = await self._assess_current_page_visually(
                browser_session,
            )
            if assessment is None:
                continue

            score = self._visual_exam_page_score(assessment)
            if best_score is None or score > best_score:
                best_candidate = candidate
                best_assessment = assessment
                best_score = score

            if assessment.page_kind == "exam_grading" and assessment.page_ready and assessment.confidence >= 75:
                return candidate.get("url")

        if best_candidate is not None and self._visual_assessment_is_exam_page(best_assessment):
            target_id = best_candidate.get("target_id", "")
            if target_id and target_id != "current-page":
                await self._ensure_target_known_to_session(browser_session, target_id)
                await self._switch_to_target(browser_session, target_id)
            return best_candidate.get("url")

        if original_target is not None:
            target_id = original_target.get("target_id", "")
            if target_id and target_id != "current-page":
                await self._ensure_target_known_to_session(browser_session, target_id)
                await self._switch_to_target(browser_session, target_id)

        return None

    async def _wait_for_exam_page_ready(
        self,
        browser_session: BrowserSession,
        *,
        timeout_seconds: float = 12.0,
    ) -> bool:
        if self._resolved_visual_backend() is not None:
            deadline = time.monotonic() + timeout_seconds
            saw_visual_assessment = False
            while time.monotonic() < deadline:
                assessment = await self._assess_current_page_visually(
                    browser_session,
                )
                if assessment is None:
                    break
                saw_visual_assessment = True
                if assessment is not None and assessment.page_kind == "exam_grading" and assessment.page_ready:
                    return True
                await asyncio.sleep(0.6)
            if saw_visual_assessment:
                return False

        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                current_url = await browser_session.get_current_page_url()
            except Exception:
                current_url = None
            page = await browser_session.get_current_page()
            if page is None:
                await asyncio.sleep(0.5)
                continue

            try:
                metrics = await page.evaluate(
                    """
                    () => {
                      const body = document.body;
                      const bodyText = body?.innerText?.trim() ?? '';
                      const root = document.querySelector('[ui-view], .mb-view');
                      const interactiveCount = document.querySelectorAll(
                        'input, textarea, select, button, a, [role="button"]'
                      ).length;
                      return {
                        readyState: document.readyState,
                        textLength: bodyText.length,
                        uiViewChildren: root ? root.children.length : 0,
                        interactiveCount,
                      };
                    }
                    """
                )
            except Exception:
                metrics = None

            if isinstance(metrics, dict):
                ready_state = str(metrics.get("readyState", "") or "").lower()
                text_length = int(metrics.get("textLength", 0) or 0)
                ui_view_children = int(metrics.get("uiViewChildren", 0) or 0)
                interactive_count = int(metrics.get("interactiveCount", 0) or 0)
                if (
                    ready_state in {"interactive", "complete"}
                    and (
                        text_length >= 40
                        or ui_view_children > 0
                        or interactive_count >= 3
                        or not current_url
                        or "arvi.sanomapro.fi" not in current_url
                    )
                ):
                    return True

            await asyncio.sleep(0.5)

        return False

    async def _collect_tab_candidates(self, browser_session: BrowserSession) -> list[dict[str, str]]:
        seen: set[tuple[str, str]] = set()
        candidates: list[dict[str, str]] = []

        def add_candidate(target_id: str, title: str, url: str) -> None:
            normalized_url = (url or "").strip()
            if not self._is_usable_page_url(normalized_url):
                return
            key = (target_id or "", normalized_url)
            if key in seen:
                return
            seen.add(key)
            candidates.append(
                {
                    "target_id": target_id or "",
                    "title": title or "",
                    "url": normalized_url,
                }
            )

        try:
            tabs = await browser_session.get_tabs()
        except Exception:
            tabs = []
        for tab in tabs:
            add_candidate(
                getattr(tab, "target_id", "") or "",
                getattr(tab, "title", "") or "",
                getattr(tab, "url", "") or "",
            )

        for target in await self._raw_cdp_page_targets(browser_session):
            self._sync_session_target_metadata(
                browser_session,
                target_id=target.get("target_id", ""),
                url=target.get("url", ""),
                title=target.get("title", ""),
            )
            add_candidate(
                target.get("target_id", ""),
                target.get("title", ""),
                target.get("url", ""),
            )

        cdp_pages_getter = getattr(browser_session, "_cdp_get_all_pages", None)
        if callable(cdp_pages_getter):
            try:
                for target in await cdp_pages_getter(include_http=True, include_about=False):
                    add_candidate(
                        str(target.get("targetId", "") or ""),
                        str(target.get("title", "") or ""),
                        str(target.get("url", "") or ""),
                    )
            except Exception:
                pass

        current_url = ""
        current_title = ""
        try:
            current_page = await browser_session.get_current_page()
            if current_page is not None:
                current_url = (await current_page.get_url()) or ""
                try:
                    current_title = (await current_page.get_title()) or ""
                except Exception:
                    current_title = ""
        except Exception:
            current_page = None

        if not current_url:
            try:
                current_url = (await browser_session.get_current_page_url()) or ""
            except Exception:
                current_url = ""

        if self._is_usable_page_url(current_url):
            existing_tab = next((tab for tab in candidates if tab["url"] == current_url), None)
            if existing_tab is not None:
                if current_title and not existing_tab["title"]:
                    existing_tab["title"] = current_title
            else:
                candidates.insert(
                    0,
                    {
                        "target_id": "current-page",
                        "title": f"{current_title} (current page)" if current_title else "Current page",
                        "url": current_url,
                    },
                )

        return candidates

    async def _switch_to_target(self, browser_session: BrowserSession, target_id: str) -> None:
        for _ in range(10):
            if getattr(browser_session, "_cdp_client_root", None) is not None:
                break
            await asyncio.sleep(0.1)

        try:
            await browser_session.on_SwitchTabEvent(SwitchTabEvent(target_id=target_id))
        except (AssertionError, RuntimeError) as exc:
            if "cdp client" not in str(exc).lower():
                raise

            # Fall back to updating agent focus directly when browser-use has not yet
            # finished wiring its root CDP client, but cached target data is available.
            browser_session.agent_focus_target_id = target_id

    def _tab_selection_score(self, tab, index: int) -> tuple[int, int]:
        url = getattr(tab, "url", "") or ""
        title = getattr(tab, "title", "") or ""
        parsed = urlparse(url)
        score = self._exam_page_signal_score(url, title)

        if parsed.path and parsed.path not in {"/", ""}:
            score += 10

        # Prefer later tabs as a tiebreaker since the exam portal is usually opened after login.
        return score, index

    async def _focus_best_available_page(
        self,
        browser_session: BrowserSession,
        *,
        prefer_exam_page: bool = False,
    ) -> str | None:
        focused_target = browser_session.get_focused_target()
        focused_url = getattr(focused_target, "url", None)
        focused_title = getattr(focused_target, "title", None)
        if self._is_usable_page_url(focused_url) and (
            not prefer_exam_page or self._is_exam_grading_page(focused_url, focused_title)
        ):
            return focused_url

        for attempt in range(4):
            candidates = await self._collect_tab_candidates(browser_session)
            if not candidates:
                if attempt < 3:
                    await asyncio.sleep(0.35)
                continue

            if prefer_exam_page:
                exam_candidates = [
                    tab
                    for tab in candidates
                    if self._is_exam_grading_page(tab.get("url"), tab.get("title"))
                ]
                if exam_candidates:
                    candidates = exam_candidates
                elif attempt < 3:
                    await asyncio.sleep(0.35)
                    continue

            indexed_candidates = list(enumerate(candidates))
            selected_tab = max(
                indexed_candidates,
                key=lambda item: self._tab_selection_score(SimpleNamespace(**item[1]), item[0]),
            )[1]

            target_id = selected_tab.get("target_id", "")
            if target_id and target_id != "current-page":
                await self._ensure_target_known_to_session(browser_session, target_id)
                await self._switch_to_target(browser_session, target_id)
            return selected_tab.get("url")

        return None

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
        if self.settings.browser_attach_to_existing_chrome:
            return BrowserSession(
                cdp_url=self._resolved_existing_chrome_cdp_url(),
                keep_alive=keep_alive,
                allowed_domains=allowed_domains,
                downloads_path=downloads_path,
            )

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

    async def list_open_tabs(self, browser_session: BrowserSession) -> list[dict[str, str]]:
        return await self._collect_tab_candidates(browser_session)

    def can_reach_existing_chrome_debugger(self) -> bool:
        if not self.settings.browser_attach_to_existing_chrome:
            return False
        try:
            response = httpx.get(
                f"{self._resolved_existing_chrome_cdp_url().rstrip('/')}/json/version",
                timeout=2.0,
            )
            response.raise_for_status()
            return True
        except Exception:
            return False

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
        try:
            best_visual_url = await self._focus_best_available_page_by_vision(browser_session)
        except Exception:
            best_visual_url = None
        if best_visual_url:
            return best_visual_url

        current_url = await browser_session.get_current_page_url()
        focused_target_getter = getattr(browser_session, "get_focused_target", None)
        focused_target = focused_target_getter() if callable(focused_target_getter) else None
        focused_title = getattr(focused_target, "title", None)
        if self._is_usable_page_url(current_url) and self._is_exam_grading_page(current_url, focused_title):
            return current_url

        page = await browser_session.get_current_page()
        page_url = None
        page_title = None
        if page is not None:
            page_url = await page.get_url()
            try:
                page_title = await page.get_title()
            except Exception:
                page_title = None
        if self._is_usable_page_url(page_url) and self._is_exam_grading_page(page_url, page_title):
            return page_url

        try:
            best_available_url = await self._focus_best_available_page(browser_session, prefer_exam_page=True)
        except Exception:
            best_available_url = None
        if best_available_url:
            return best_available_url

        if self._is_usable_page_url(current_url):
            return current_url
        if self._is_usable_page_url(page_url):
            return page_url

        return await self._focus_best_available_page(browser_session)

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
- Use the visible page state only to confirm you are in the right panel or exercise.
- Prefer DOM text, labels, and semantic controls for the actual grading actions.
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
                f"Use DOM text and semantic controls as the primary source of truth while navigating. The active browser model provider is {provider}. "
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
                "Use the visible page state only to confirm where you are. Prefer DOM text and semantic controls for navigation and control selection. "
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
            if not current_url or not self._is_exam_grading_page(current_url):
                current_url, extracted_text = await self._capture_page_state(
                    browser_session,
                    current_url or self.settings.browser_start_url,
                    screenshot_path,
                )
                return ExamSessionGradingTaskResult(
                    job_id=job_id,
                    status="failed",
                    summary="Open the actual exam review/grading page in the managed browser before starting grading.",
                    agent_provider=provider,
                    agent_model=self._resolved_browser_agent_model(),
                    current_url=current_url,
                    screenshot_path=str(screenshot_path),
                    extracted_text=extracted_text,
                    steps=[
                        {
                            "name": "page_check",
                            "status": "failed",
                            "detail": "The managed browser was not on a loaded exam review or grading page.",
                        }
                    ],
                )

            await self._wait_for_exam_page_ready(browser_session)

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
