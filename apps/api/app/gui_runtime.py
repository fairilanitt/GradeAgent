from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from datetime import datetime, timezone
from uuid import uuid4

from app.config import Settings, get_settings
from app.prompt_library import PromptLibraryService, PromptTemplate
from app.schemas.api import (
    ExamSessionGradingTaskCreate,
    ExamSessionGradingTaskResult,
    GuiAutopilotQueueItemRequest,
    GuiStateResponse,
    GuiStatisticsEntry,
    GuiStatisticsRun,
)
from app.services.gui_statistics import GuiStatisticsStore
from app.services.llm_provider import (
    DEFAULT_VERTEX_AI_GRADING_MODEL,
    normalize_reasoning_level,
    normalize_vertex_ai_grading_selection,
)
from app.services.browser_navigation import (
    BrowserNavigationService,
    SanomaGradingReportEntry,
    SanomaOverviewExerciseColumn,
    SanomaOverviewState,
)


class GuiRuntime:
    def __init__(
        self,
        settings: Settings | None = None,
        service: BrowserNavigationService | None = None,
        prompt_library: PromptLibraryService | None = None,
        statistics_store: GuiStatisticsStore | None = None,
    ) -> None:
        self.settings = settings or get_settings().model_copy(
            update={
                "browser_headless": False,
                "browser_attach_to_existing_chrome": False,
            }
        )
        self.service = service or BrowserNavigationService(self.settings)
        self.prompt_library = prompt_library or PromptLibraryService()
        self.statistics_store = statistics_store or GuiStatisticsStore()
        self._lock = threading.RLock()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="gradeagent-gui-runtime", daemon=True)
        self._thread.start()
        self._browser_session = None
        self._session_id: str | None = None
        self._last_overview_state: SanomaOverviewState | None = None
        self._active_grading_future: concurrent.futures.Future | None = None
        self._queue_stop_requested = False
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def has_browser_session(self) -> bool:
        return self._browser_session is not None

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _call(self, coro):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def state(self) -> GuiStateResponse:
        self._clear_dead_browser_session_if_needed()
        return GuiStateResponse(
            browser_ready=self.has_browser_session,
            session_id=self._session_id,
            prompt_count=len(self.prompt_templates()),
        )

    @property
    def grading_active(self) -> bool:
        with self._lock:
            return self._active_grading_future is not None and not self._active_grading_future.done()

    def prompt_templates(self) -> list[PromptTemplate]:
        return self.prompt_library.load_prompts()

    def new_prompt_template(self) -> PromptTemplate:
        return self.prompt_library.new_custom_prompt()

    def save_prompt(
        self,
        *,
        title: str,
        body: str,
        model_provider: str,
        model_name: str,
        reasoning_level: str,
        prompt_id: str | None = None,
    ) -> PromptTemplate:
        normalized_title = title.strip()
        normalized_body = body.strip()
        normalized_provider, normalized_model_name = normalize_vertex_ai_grading_selection(
            model_provider,
            model_name,
        )
        normalized_reasoning_level = normalize_reasoning_level(reasoning_level)
        if not normalized_title:
            raise ValueError("Anna kriteerille nimi ennen tallennusta.")
        if not normalized_body:
            raise ValueError("Kirjoita kriteerin sisältö ennen tallennusta.")
        if not normalized_model_name:
            raise ValueError("Valitse kriteerille arviointimalli ennen tallennusta.")

        existing = self.prompt_library.get_prompt(prompt_id) if prompt_id else None
        draft_prompt = existing or self.prompt_library.new_custom_prompt()
        prompt = PromptTemplate(
            prompt_id=prompt_id or draft_prompt.prompt_id,
            title=normalized_title,
            body=normalized_body,
            model_provider=normalized_provider,
            model_name=normalized_model_name,
            reasoning_level=normalized_reasoning_level,
            built_in=existing.built_in if existing is not None else False,
        )
        return self.prompt_library.save_prompt(prompt)

    def ensure_browser_started(self) -> str:
        self._clear_dead_browser_session_if_needed()
        with self._lock:
            if self._browser_session is not None and self._session_id:
                return self._session_id

            session_id, browser_session = self._call(self.service.launch_interactive_browser(str(uuid4())))
            self._session_id = session_id
            self._browser_session = browser_session
            return session_id

    def refresh_overview(self) -> SanomaOverviewState:
        self._clear_dead_browser_session_if_needed()
        with self._lock:
            if self._browser_session is None:
                raise RuntimeError("Käynnistä GradeAgent-selain ensin.")
            overview_state = self._call(self.service.inspect_sanomapro_overview_passively(self._browser_session))
            self._last_overview_state = overview_state
            return overview_state

    def stop_browser(self) -> GuiStateResponse:
        with self._lock:
            browser_session = self._browser_session
            session_id = self._session_id
            self._browser_session = None
            self._session_id = None
            self._last_overview_state = None

        if browser_session is not None:
            self._call(browser_session.kill())
        if session_id:
            self.service.cleanup_browser_artifacts(current_job_id=session_id)
        return self.state()

    def pending_exercises(self) -> list[SanomaOverviewExerciseColumn]:
        overview_state = self.refresh_overview()
        return [column for column in overview_state.exercise_columns if column.pending_cell_count > 0]

    def statistics(self) -> list[GuiStatisticsRun]:
        return self.statistics_store.load_runs()

    def _resolve_grading_request(
        self,
        *,
        instructions: str,
        prompt_id: str | None,
        prompt_title: str | None,
        model_provider: str | None,
        model_name: str | None,
        reasoning_level: str | None,
        max_steps: int,
    ) -> tuple[ExamSessionGradingTaskCreate, str | None, str | None]:
        resolved_instructions = instructions.strip()
        resolved_prompt_id = prompt_id
        resolved_prompt_title = prompt_title
        resolved_provider = model_provider or "vertex_ai"
        resolved_model_name = model_name or DEFAULT_VERTEX_AI_GRADING_MODEL
        resolved_reasoning_level = normalize_reasoning_level(reasoning_level)

        if prompt_id:
            latest_prompt = self.prompt_library.get_prompt(prompt_id)
            if latest_prompt is None:
                raise RuntimeError("Valittua kriteeriä ei löytynyt enää kirjastosta. Päivitä näkymä ja valitse kriteeri uudelleen.")
            resolved_instructions = latest_prompt.body.strip()
            resolved_prompt_id = latest_prompt.prompt_id
            resolved_prompt_title = latest_prompt.title
            resolved_provider = latest_prompt.model_provider
            resolved_model_name = latest_prompt.model_name
            resolved_reasoning_level = latest_prompt.reasoning_level
        else:
            resolved_provider, resolved_model_name = normalize_vertex_ai_grading_selection(
                resolved_provider,
                resolved_model_name,
            )

        if not resolved_instructions:
            raise RuntimeError("Valitulla kriteerillä ei ole sisältöä. Tallenna prompti ennen arvioinnin aloittamista.")

        payload = ExamSessionGradingTaskCreate(
            instructions=resolved_instructions,
            grading_model_provider=resolved_provider,
            grading_model_name=resolved_model_name,
            grading_reasoning_level=resolved_reasoning_level,
            max_steps=max_steps,
        )
        return payload, resolved_prompt_id, resolved_prompt_title

    def _grade_exercise(
        self,
        *,
        column_key: str,
        instructions: str,
        prompt_id: str | None = None,
        prompt_title: str | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
        reasoning_level: str | None = None,
        max_steps: int = 260,
        reset_queue_stop: bool,
    ) -> tuple[ExamSessionGradingTaskResult, SanomaOverviewState]:
        self._clear_dead_browser_session_if_needed()
        with self._lock:
            if self._browser_session is None:
                raise RuntimeError("Käynnistä GradeAgent-selain ensin.")
            if self._active_grading_future is not None and not self._active_grading_future.done():
                raise RuntimeError("Arviointi on jo käynnissä. Pysäytä nykyinen ajo ennen uuden aloittamista.")

            overview_context = self._last_overview_state
            if reset_queue_stop:
                self._queue_stop_requested = False
            payload, resolved_prompt_id, resolved_prompt_title = self._resolve_grading_request(
                instructions=instructions,
                prompt_id=prompt_id,
                prompt_title=prompt_title,
                model_provider=model_provider,
                model_name=model_name,
                reasoning_level=reasoning_level,
                max_steps=max_steps,
            )
            self.service.clear_stop_grading_request()
            future = asyncio.run_coroutine_threadsafe(
                self.service.grade_sanomapro_exercise_column_from_current_page(
                    payload=payload,
                    job_id=str(uuid4()),
                    browser_session=self._browser_session,
                    column_key=column_key,
                ),
                self._loop,
            )
            self._active_grading_future = future

        try:
            result = future.result()
        finally:
            self.service.clear_stop_grading_request()
            with self._lock:
                if self._active_grading_future is future:
                    self._active_grading_future = None

        with self._lock:
            report_entries = self.service.consume_last_sanomapro_report_entries(result.job_id)
            overview_state = overview_context or self._last_overview_state or SanomaOverviewState()
            try:
                overview_state = self._call(self.service.inspect_sanomapro_overview_passively(self._browser_session))
                self._last_overview_state = overview_state
            except Exception:
                pass
            self._record_statistics_run(
                result=result,
                overview_context=overview_context,
                column_key=column_key,
                prompt_id=resolved_prompt_id,
                prompt_title=resolved_prompt_title,
                report_entries=report_entries,
            )
            return result, overview_state

    def grade_exercise(
        self,
        *,
        column_key: str,
        instructions: str,
        prompt_id: str | None = None,
        prompt_title: str | None = None,
        model_provider: str | None = None,
        model_name: str | None = None,
        reasoning_level: str | None = None,
        max_steps: int = 260,
    ) -> tuple[ExamSessionGradingTaskResult, SanomaOverviewState]:
        return self._grade_exercise(
            column_key=column_key,
            instructions=instructions,
            prompt_id=prompt_id,
            prompt_title=prompt_title,
            model_provider=model_provider,
            model_name=model_name,
            reasoning_level=reasoning_level,
            max_steps=max_steps,
            reset_queue_stop=True,
        )

    def grade_exercise_queue(
        self,
        *,
        items: list[GuiAutopilotQueueItemRequest],
    ) -> tuple[list[tuple[GuiAutopilotQueueItemRequest, ExamSessionGradingTaskResult]], SanomaOverviewState, str]:
        if not items:
            raise RuntimeError("Lisää Autopilotiin ainakin yksi tehtävä ennen aloitusta.")

        self._clear_dead_browser_session_if_needed()
        with self._lock:
            if self._browser_session is None:
                raise RuntimeError("Käynnistä GradeAgent-selain ensin.")
            if self._active_grading_future is not None and not self._active_grading_future.done():
                raise RuntimeError("Arviointi on jo käynnissä. Pysäytä nykyinen ajo ennen uuden aloittamista.")
            self._queue_stop_requested = False

        latest_overview = self._last_overview_state or SanomaOverviewState()
        results: list[tuple[GuiAutopilotQueueItemRequest, ExamSessionGradingTaskResult]] = []

        for item in items:
            if self._queue_stop_requested:
                break

            try:
                latest_overview = self.refresh_overview()
            except Exception:
                pass

            pending_column = next(
                (column for column in latest_overview.exercise_columns if column.column_key == item.column_key),
                None,
            )
            if pending_column is None or pending_column.pending_cell_count <= 0:
                results.append(
                    (
                        item,
                        ExamSessionGradingTaskResult(
                            job_id=str(uuid4()),
                            status="needs_review",
                            summary="Queued exercise was no longer available in the current overview.",
                            current_exercise_label=None,
                            current_student_name=None,
                            report_path=None,
                        ),
                    )
                )
                continue

            try:
                result, latest_overview = self._grade_exercise(
                    column_key=item.column_key,
                    instructions=item.instructions,
                    prompt_id=item.prompt_id,
                    prompt_title=item.prompt_title,
                    model_provider=item.model_provider,
                    model_name=item.model_name,
                    reasoning_level=item.reasoning_level,
                    max_steps=item.max_steps,
                    reset_queue_stop=False,
                )
            except Exception as exc:
                result = ExamSessionGradingTaskResult(
                    job_id=str(uuid4()),
                    status="failed",
                    summary=f"Autopilot could not grade the queued exercise: {exc}",
                    current_exercise_label=pending_column.label,
                    current_student_name=None,
                    report_path=None,
                )
                try:
                    latest_overview = self.refresh_overview()
                except Exception:
                    pass

            results.append((item, result))

        summary = (
            "Autopilot stopped gracefully at the user's request."
            if self._queue_stop_requested
            else f"Autopilot processed {len(results)} queued exercise(s)."
        )

        with self._lock:
            self._queue_stop_requested = False

        return results, latest_overview, summary

    def request_stop_grading(self) -> None:
        with self._lock:
            active_future = self._active_grading_future
            self._queue_stop_requested = True
        if active_future is None or active_future.done():
            return
        self.service.request_stop_grading()

    def _statistics_run_interrupted(self, result: ExamSessionGradingTaskResult) -> bool:
        normalized_summary = result.summary.lower()
        if "interrupted" in normalized_summary:
            return True
        if "stopped" in normalized_summary and "grace" in normalized_summary:
            return True
        if "stopped" in normalized_summary and "user" in normalized_summary:
            return True
        return False

    def _record_statistics_run(
        self,
        *,
        result: ExamSessionGradingTaskResult,
        overview_context: SanomaOverviewState | None,
        column_key: str,
        prompt_id: str | None,
        prompt_title: str | None,
        report_entries: list[SanomaGradingReportEntry],
    ) -> None:
        selected_column = None
        if overview_context is not None:
            selected_column = next(
                (column for column in overview_context.exercise_columns if column.column_key == column_key),
                None,
            )

        mapped_entries = [self._map_statistics_entry(entry) for entry in report_entries]
        primary_entry = mapped_entries[0] if mapped_entries else None

        record = GuiStatisticsRun(
            run_id=str(uuid4()),
            job_id=result.job_id,
            recorded_at=datetime.now(timezone.utc),
            status=result.status,
            interrupted=self._statistics_run_interrupted(result),
            summary=result.summary,
            assignment_title=(
                primary_entry.assignment_title
                if primary_entry and primary_entry.assignment_title
                else overview_context.assignment_title if overview_context is not None else ""
            ),
            group_name=(
                primary_entry.group_name
                if primary_entry and primary_entry.group_name
                else overview_context.group_name if overview_context is not None else None
            ),
            category_name=(
                primary_entry.category_name
                if primary_entry and primary_entry.category_name
                else selected_column.category_name if selected_column is not None else None
            ),
            exercise_label=(
                primary_entry.exercise_label
                if primary_entry and primary_entry.exercise_label
                else (
                    result.current_exercise_label
                    or (selected_column.label if selected_column is not None else None)
                )
            ),
            exercise_number=(
                primary_entry.exercise_number
                if primary_entry and primary_entry.exercise_number
                else selected_column.exercise_number if selected_column is not None else None
            ),
            students_answered_count=overview_context.students_answered_count if overview_context is not None else None,
            students_total_count=overview_context.students_total_count if overview_context is not None else None,
            processed_answers=result.processed_answers,
            filled_point_fields=result.filled_point_fields,
            report_path=result.report_path,
            prompt_id=prompt_id,
            prompt_title=prompt_title,
            entries=mapped_entries,
        )
        self.statistics_store.append_run(record)

    def _detach_browser_session_locked(self) -> tuple[object | None, str | None]:
        browser_session = self._browser_session
        session_id = self._session_id
        self._browser_session = None
        self._session_id = None
        self._last_overview_state = None
        return browser_session, session_id

    def _cleanup_detached_browser_session(self, browser_session, session_id: str | None) -> None:
        try:
            if browser_session is not None:
                self._call(browser_session.kill())
        except Exception:
            pass
        if session_id:
            self.service.cleanup_browser_artifacts(current_job_id=session_id)

    def _browser_session_is_usable(self, browser_session) -> bool:
        try:
            self._call(self.service.list_open_tabs(browser_session))
            return True
        except Exception:
            return False

    def _clear_dead_browser_session_if_needed(self) -> None:
        browser_session = None
        session_id: str | None = None
        with self._lock:
            if self._browser_session is None:
                return
            if self._browser_session_is_usable(self._browser_session):
                return
            browser_session, session_id = self._detach_browser_session_locked()
        self._cleanup_detached_browser_session(browser_session, session_id)

    def _map_statistics_entry(self, entry: SanomaGradingReportEntry) -> GuiStatisticsEntry:
        return GuiStatisticsEntry(
            student_name=entry.student_name,
            student_progress=entry.student_progress,
            assignment_title=entry.assignment_title,
            group_name=entry.group_name,
            category_name=entry.category_name,
            exercise_label=entry.exercise_label,
            exercise_number=entry.exercise_number,
            objective_text=entry.objective_text,
            target_text=entry.target_text,
            question_text=entry.question_text,
            answer_text=entry.answer_text,
            model_answer_text=entry.model_answer_text,
            points_text=entry.points_text,
            score_awarded=entry.score_awarded,
            score_possible=entry.score_possible,
            basis_lines=list(entry.basis_lines),
            prompt_template_text=entry.prompt_template_text,
            rendered_instructions_text=entry.rendered_instructions_text,
            submitted_prompt_text=entry.submitted_prompt_text,
            model_provider=entry.model_provider,
            model_name=entry.model_name,
            reasoning_level=entry.reasoning_level,
            model_response_text=entry.model_response_text,
            repair_prompt_text=entry.repair_prompt_text,
            repair_response_text=entry.repair_response_text,
            used_heuristic_fallback=entry.used_heuristic_fallback,
            fallback_reason=entry.fallback_reason,
            exercise_url=entry.exercise_url,
            status=entry.status,
        )

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return

            browser_session = self._browser_session
            session_id = self._session_id
            active_future = self._active_grading_future
            self._browser_session = None
            self._session_id = None
            self._last_overview_state = None
            self._active_grading_future = None
            self._closed = True

        try:
            self.service.request_stop_grading()
            if active_future is not None:
                active_future.cancel()
            if browser_session is not None:
                self._call(browser_session.kill())
        finally:
            if session_id:
                self.service.cleanup_browser_artifacts(current_job_id=session_id)
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2.0)
            self._loop.close()


_runtime_lock = threading.Lock()
_gui_runtime: GuiRuntime | None = None


def get_gui_runtime() -> GuiRuntime:
    global _gui_runtime
    with _runtime_lock:
        if _gui_runtime is None or _gui_runtime.closed:
            _gui_runtime = GuiRuntime()
        return _gui_runtime


def reset_gui_runtime() -> None:
    global _gui_runtime
    with _runtime_lock:
        runtime = _gui_runtime
        _gui_runtime = None
    if runtime is not None:
        runtime.shutdown()
