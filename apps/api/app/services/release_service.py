from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models.domain import GradeRun, ReviewDecision


class ReleaseService:
    def publish(self, session: Session, assessment_id: str) -> tuple[int, datetime]:
        release_time = datetime.now(timezone.utc)
        grade_runs = session.exec(select(GradeRun).where(GradeRun.assessment_id == assessment_id)).all()
        grade_run_ids = [item.id for item in grade_runs]
        if not grade_run_ids:
            return 0, release_time

        decisions = session.exec(
            select(ReviewDecision).where(ReviewDecision.grade_run_id.in_(grade_run_ids))
        ).all()

        released_count = 0
        for decision in decisions:
            if decision.decision not in {"approved", "overridden"}:
                continue
            if decision.released_at is None:
                decision.released_at = release_time
                released_count += 1
                session.add(decision)

        session.commit()
        return released_count, release_time
