from __future__ import annotations

from temporalio.client import Client

from app.config import Settings, get_settings
from app.workflows.grade_workflow import GradeSubmissionWorkflow, GradeWorkflowInput


class WorkflowDispatcher:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def schedule_grade_run(self, grade_run_id: str) -> str:
        client = await Client.connect(
            self.settings.temporal_target,
            namespace=self.settings.temporal_namespace,
        )
        handle = await client.start_workflow(
            GradeSubmissionWorkflow.run,
            GradeWorkflowInput(grade_run_id=grade_run_id),
            id=f"grade-run-{grade_run_id}",
            task_queue=self.settings.temporal_task_queue,
        )
        return handle.id
