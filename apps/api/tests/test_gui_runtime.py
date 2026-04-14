from app.gui_runtime import GuiRuntime
from app.prompt_library import PromptTemplate
from app.schemas.api import GuiAutopilotQueueItemRequest
from app.schemas.api import ExamSessionGradingTaskResult
from app.services.browser_navigation import SanomaOverviewExerciseColumn, SanomaOverviewState


class FakePromptLibrary:
    def __init__(self) -> None:
        self.prompt = PromptTemplate(
            prompt_id="prompt-1",
            title="Latest prompt",
            body='Use the latest saved instructions for "(TARGET)".',
            model_provider="vertex_ai",
            model_name="gemini-2.5-flash-lite",
            reasoning_level="low",
            built_in=False,
        )

    def load_prompts(self) -> list[PromptTemplate]:
        return [self.prompt]

    def get_prompt(self, prompt_id: str) -> PromptTemplate | None:
        return self.prompt if prompt_id == self.prompt.prompt_id else None

    def new_custom_prompt(self) -> PromptTemplate:
        return self.prompt

    def save_prompt(self, prompt: PromptTemplate) -> PromptTemplate:
        self.prompt = prompt
        return prompt


class FakeStatisticsStore:
    def load_runs(self) -> list[object]:
        return []

    def append_run(self, record) -> None:
        return None


class FakeBrowserNavigationService:
    def __init__(self) -> None:
        self.captured_payloads: list[tuple[str, object]] = []
        self.overview_state = SanomaOverviewState()

    async def launch_interactive_browser(self, job_id: str):
        return "session-1", object()

    async def list_open_tabs(self, browser_session) -> list[object]:
        return []

    def clear_stop_grading_request(self) -> None:
        return None

    def request_stop_grading(self) -> None:
        return None

    async def grade_sanomapro_exercise_column_from_current_page(self, payload, job_id, browser_session, column_key):
        self.captured_payloads.append((column_key, payload))
        return ExamSessionGradingTaskResult(
            job_id=job_id,
            status="completed",
            summary="ok",
        )

    async def inspect_sanomapro_overview_passively(self, browser_session) -> SanomaOverviewState:
        return self.overview_state

    def consume_last_sanomapro_report_entries(self, job_id: str) -> list[object]:
        return []

    def cleanup_browser_artifacts(self, current_job_id: str | None = None) -> None:
        return None


class FakeBrowserSession:
    async def kill(self) -> None:
        return None


def test_gui_runtime_uses_latest_saved_prompt_settings_when_grading() -> None:
    service = FakeBrowserNavigationService()
    runtime = GuiRuntime(
        service=service,
        prompt_library=FakePromptLibrary(),
        statistics_store=FakeStatisticsStore(),
    )
    runtime._browser_session = FakeBrowserSession()
    runtime._session_id = "session-1"

    try:
        runtime.grade_exercise(
            column_key="text-4-4",
            instructions="STALE instructions should not be used.",
            prompt_id="prompt-1",
            prompt_title="Old title",
            model_provider="vertex_ai",
            model_name="gemini-2.0-flash-001",
            reasoning_level="off",
        )
    finally:
        runtime.shutdown()

    assert len(service.captured_payloads) == 1
    payload = service.captured_payloads[0][1]
    assert payload.instructions == 'Use the latest saved instructions for "(TARGET)".'
    assert payload.grading_model_provider == "vertex_ai"
    assert payload.grading_model_name == "gemini-2.5-flash-lite"
    assert payload.grading_reasoning_level == "low"


def test_gui_runtime_grades_autopilot_queue_in_given_order() -> None:
    service = FakeBrowserNavigationService()
    runtime = GuiRuntime(
        service=service,
        prompt_library=FakePromptLibrary(),
        statistics_store=FakeStatisticsStore(),
    )
    runtime._browser_session = FakeBrowserSession()
    runtime._session_id = "session-1"
    service.overview_state = SanomaOverviewState(
        exercise_columns=[
            SanomaOverviewExerciseColumn(column_key="exercise-2", pending_cell_count=5),
            SanomaOverviewExerciseColumn(column_key="exercise-1", pending_cell_count=3),
        ]
    )
    runtime._last_overview_state = service.overview_state

    try:
        results, _, summary = runtime.grade_exercise_queue(
            items=[
                GuiAutopilotQueueItemRequest(
                    column_key="exercise-2",
                    instructions="stale",
                    prompt_id="prompt-1",
                    prompt_title="Old title",
                    model_provider="vertex_ai",
                    model_name="gemini-2.0-flash-001",
                    reasoning_level="off",
                    max_steps=260,
                ),
                GuiAutopilotQueueItemRequest(
                    column_key="exercise-1",
                    instructions="stale",
                    prompt_id="prompt-1",
                    prompt_title="Old title",
                    model_provider="vertex_ai",
                    model_name="gemini-2.0-flash-001",
                    reasoning_level="off",
                    max_steps=260,
                ),
            ]
        )
    finally:
        runtime.shutdown()

    assert [item.column_key for item, _ in results] == ["exercise-2", "exercise-1"]
    assert [column_key for column_key, _ in service.captured_payloads] == ["exercise-2", "exercise-1"]
    assert summary == "Autopilot processed 2 queued exercise(s)."
