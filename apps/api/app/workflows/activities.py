from __future__ import annotations

from sqlmodel import Session
from temporalio import activity

from app.db import engine
from app.models.domain import Assessment, GradeRun, RubricProfile, Submission
from app.services.grading_pipeline import GradingPipeline


@activity.defn
async def run_grade_activity(grade_run_id: str) -> dict:
    with Session(engine) as session:
        grade_run = session.get(GradeRun, grade_run_id)
        if not grade_run:
            return {"grade_run_id": grade_run_id, "status": "missing"}

        assessment = session.get(Assessment, grade_run.assessment_id)
        submission = session.get(Submission, grade_run.submission_id)
        rubric = session.get(RubricProfile, grade_run.rubric_profile_id)
        if not assessment or not submission or not rubric:
            grade_run.status = "failed"
            session.add(grade_run)
            session.commit()
            return {"grade_run_id": grade_run_id, "status": "failed"}

        await GradingPipeline().persist_grade_run(session, grade_run, assessment, submission, rubric)
        return {"grade_run_id": grade_run_id, "status": "awaiting_review"}
