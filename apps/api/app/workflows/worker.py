from __future__ import annotations

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from app.config import get_settings
from app.workflows.activities import run_grade_activity
from app.workflows.grade_workflow import GradeSubmissionWorkflow


async def main() -> None:
    settings = get_settings()
    client = await Client.connect(
        settings.temporal_target,
        namespace=settings.temporal_namespace,
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[GradeSubmissionWorkflow],
        activities=[run_grade_activity],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
