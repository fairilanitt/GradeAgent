from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlmodel import Session

from app.models.domain import Assessment, GradeRun, RubricProfile, Submission
from app.schemas.api import CriterionDefinition, StructuredGradeResult
from app.services.model_router import GradeRequest, ModelRouter, RoutingDecision, get_model_router
from app.services.rubric_validator import RubricValidator


@dataclass
class PipelineOutcome:
    routing_tier: str
    reviewer_required: bool
    confidence: float
    flags: list[str]
    feedback: str
    model_summary: str
    result: StructuredGradeResult
    audit_snapshot: dict


class GradingPipeline:
    def __init__(
        self,
        model_router: ModelRouter | None = None,
        rubric_validator: RubricValidator | None = None,
    ) -> None:
        self.model_router = model_router or get_model_router()
        self.rubric_validator = rubric_validator or RubricValidator()

    async def run(
        self,
        assessment: Assessment,
        submission: Submission,
        rubric: RubricProfile,
    ) -> PipelineOutcome:
        criteria = [CriterionDefinition.model_validate(item) for item in rubric.criteria_json]
        request = GradeRequest(
            assessment_title=assessment.title,
            task_type=assessment.task_type,
            is_exam=assessment.is_exam,
            answer_text=submission.answer_text,
            language=submission.language,
            criteria=criteria,
            preferences=rubric.preferences_json,
            exemplars=rubric.exemplar_answers_json,
        )
        routing_decision: RoutingDecision = self.model_router.route(request)
        result = await self.model_router.grade(request, routing_decision)

        flags = self.rubric_validator.validate_grade_result(result, criteria)
        reviewer_required = True
        if assessment.is_exam:
            flags.append("exam_mode")
        if result.confidence < 0.8:
            flags.append("low_confidence")
        if rubric.version == 1:
            flags.append("new_rubric_version")

        answer_hash = hashlib.sha256(submission.answer_text.encode("utf-8")).hexdigest()
        audit_snapshot = {
            "assessment_id": assessment.id,
            "submission_id": submission.id,
            "submission_sha256": answer_hash,
            "rubric_profile_id": rubric.id,
            "rubric_version": rubric.version,
            "routing_tier": routing_decision.routing_tier,
            "model_provider": routing_decision.provider,
            "model_name": routing_decision.model_name,
            "complexity_score": routing_decision.complexity_score,
            "routing_reasons": routing_decision.reasons,
            "confidence": result.confidence,
            "flags": sorted(set(flags)),
        }

        return PipelineOutcome(
            routing_tier=routing_decision.routing_tier,
            reviewer_required=reviewer_required,
            confidence=result.confidence,
            flags=sorted(set(flags)),
            feedback=result.feedback,
            model_summary=(
                f"{routing_decision.provider}/{routing_decision.model_name} handled "
                f"{routing_decision.routing_tier} routing across {len(result.criterion_scores)} rubric criteria."
            ),
            result=result,
            audit_snapshot=audit_snapshot,
        )

    async def persist_grade_run(
        self,
        session: Session,
        grade_run: GradeRun,
        assessment: Assessment,
        submission: Submission,
        rubric: RubricProfile,
    ) -> GradeRun:
        outcome = await self.run(assessment, submission, rubric)
        grade_run.routing_tier = outcome.routing_tier
        grade_run.status = "awaiting_review"
        grade_run.reviewer_required = outcome.reviewer_required
        grade_run.confidence = outcome.confidence
        grade_run.feedback_text = outcome.feedback
        grade_run.model_summary = outcome.model_summary
        grade_run.policy_flags_json = outcome.flags
        grade_run.result_json = outcome.result.model_dump(mode="json")
        grade_run.audit_snapshot_json = outcome.audit_snapshot
        session.add(grade_run)
        session.commit()
        session.refresh(grade_run)
        return grade_run
