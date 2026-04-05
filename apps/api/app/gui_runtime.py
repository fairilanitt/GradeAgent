from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timezone
from uuid import uuid4

from app.config import Settings, get_settings
from app.prompt_library import PromptLibraryService, PromptTemplate
from app.schemas.api import (
    ExamSessionGradingTaskCreate,
    ExamSessionGradingTaskResult,
    GuiStatisticsEntry,
    GuiStatisticsRun,
)
from app.services.gui_statistics import GuiStatisticsStore
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

    def state(self) -> dict[str, object]:
        prompts = self.prompt_templates()
        return {
            "browser_ready": self.has_browser_session,
            "session_id": self._session_id,
            "prompt_count": len(prompts),
        }

    def prompt_templates(self) -> list[PromptTemplate]:
        return self.prompt_library.load_prompts()

    def new_prompt_template(self) -> PromptTemplate:
        return self.prompt_library.new_custom_prompt()

    def save_prompt(
        self,
        *,
        title: str,
        body: str,
        prompt_id: str | None = None,
    ) -> PromptTemplate:
        normalized_title = title.strip()
        normalized_body = body.strip()
        if not normalized_title:
            raise ValueError("Anna kriteerille nimi ennen tallennusta.")
        if not normalized_body:
            raise ValueError("Kirjoita kriteerin sisältö ennen tallennusta.")

        existing = self.prompt_library.get_prompt(prompt_id) if prompt_id else None
        draft_prompt = existing or self.prompt_library.new_custom_prompt()
        prompt = PromptTemplate(
            prompt_id=prompt_id or draft_prompt.prompt_id,
            title=normalized_title,
            body=normalized_body,
            built_in=existing.built_in if existing is not None else False,
        )
        return self.prompt_library.save_prompt(prompt)

    def ensure_browser_started(self) -> str:
        with self._lock:
            if self._browser_session is not None and self._session_id:
                return self._session_id

            session_id, browser_session = self._call(self.service.launch_interactive_browser(str(uuid4())))
            self._session_id = session_id
            self._browser_session = browser_session
            return session_id

    def refresh_overview(self) -> SanomaOverviewState:
        with self._lock:
            if self._browser_session is None:
                raise RuntimeError("Käynnistä GradeAgent-selain ensin.")
            overview_state = self._call(self.service.inspect_sanomapro_overview(self._browser_session))
            self._last_overview_state = overview_state
            return overview_state

    def stop_browser(self) -> dict[str, object]:
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

    def grade_exercise(
        self,
        *,
        column_key: str,
        instructions: str,
        prompt_id: str | None = None,
        prompt_title: str | None = None,
        max_steps: int = 260,
    ) -> tuple[ExamSessionGradingTaskResult, SanomaOverviewState]:
        with self._lock:
            if self._browser_session is None:
                raise RuntimeError("Käynnistä GradeAgent-selain ensin.")

            overview_context = self._last_overview_state
            payload = ExamSessionGradingTaskCreate(
                instructions=instructions.strip(),
                max_steps=max_steps,
            )
            result = self._call(
                self.service.grade_sanomapro_exercise_column_from_current_page(
                    payload=payload,
                    job_id=str(uuid4()),
                    browser_session=self._browser_session,
                    column_key=column_key,
                )
            )
            report_entries = self.service.consume_last_sanomapro_report_entries(result.job_id)
            overview_state = self._call(self.service.inspect_sanomapro_overview(self._browser_session))
            self._last_overview_state = overview_state
            self._record_statistics_run(
                result=result,
                overview_context=overview_context,
                column_key=column_key,
                prompt_id=prompt_id,
                prompt_title=prompt_title,
                report_entries=report_entries,
            )
            return result, overview_state

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
            exercise_url=entry.exercise_url,
            status=entry.status,
        )

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return

            browser_session = self._browser_session
            session_id = self._session_id
            self._browser_session = None
            self._session_id = None
            self._last_overview_state = None
            self._closed = True

        try:
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
