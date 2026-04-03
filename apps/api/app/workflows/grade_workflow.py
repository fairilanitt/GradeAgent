from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.activities import run_grade_activity


@dataclass
class GradeWorkflowInput:
    grade_run_id: str


@workflow.defn
class GradeSubmissionWorkflow:
    @workflow.run
    async def run(self, payload: GradeWorkflowInput) -> dict:
        return await workflow.execute_activity(
            run_grade_activity,
            payload.grade_run_id,
            start_to_close_timeout=timedelta(minutes=5),
        )
