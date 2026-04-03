from __future__ import annotations

from app.schemas.api import ProcessStep, TextScoringRequest, TextScoringResponse
from app.services.model_router import GradeRequest, ModelRouter, get_model_router
from app.services.rubric_validator import RubricValidator


class TextScoringService:
    def __init__(
        self,
        model_router: ModelRouter | None = None,
        rubric_validator: RubricValidator | None = None,
    ) -> None:
        self.model_router = model_router or get_model_router()
        self.rubric_validator = rubric_validator or RubricValidator()

    async def score_text(self, payload: TextScoringRequest) -> TextScoringResponse:
        if not payload.criteria:
            raise ValueError("At least one criterion is required.")

        request = GradeRequest(
            assessment_title=payload.task_title,
            task_type="text_submission_scoring",
            is_exam=False,
            answer_text=payload.submission_text,
            language=payload.language,
            criteria=payload.criteria,
            preferences=payload.preferences.model_dump(mode="json"),
            exemplars=[],
        )
        routing_decision = self.model_router.route(request)
        result = await self.model_router.grade(request, routing_decision)

        flags = self.rubric_validator.validate_grade_result(result, payload.criteria)
        if result.confidence < 0.8:
            flags.append("low_confidence")

        max_points = round(sum(item.max_score for item in payload.criteria), 2)
        bounded_points = min(max(round(result.overall_score, 2), 0), max_points)
        if bounded_points != round(result.overall_score, 2):
            flags.append("points_clipped_to_valid_range")

        steps = [
            ProcessStep(name="criteria_loaded", detail=f"Loaded {len(payload.criteria)} teacher criteria."),
            ProcessStep(
                name="complexity_routed",
                detail=(
                    f"Classified submission as {routing_decision.routing_tier} complexity "
                    f"with score {routing_decision.complexity_score}."
                ),
            ),
            ProcessStep(
                name="model_selected",
                detail=f"Selected {routing_decision.provider}/{routing_decision.model_name}.",
            ),
            ProcessStep(
                name="score_generated",
                detail=f"Generated {bounded_points} / {max_points} points with {result.confidence:.0%} confidence.",
            ),
            ProcessStep(
                name="validation_finished",
                detail="Validated criterion bounds, evidence coverage, and overall score limits.",
            ),
        ]

        return TextScoringResponse(
            points_to_enter=bounded_points,
            max_points=max_points,
            routing_tier=routing_decision.routing_tier,
            model_provider=routing_decision.provider,
            model_name=routing_decision.model_name,
            complexity_score=routing_decision.complexity_score,
            submission_word_count=routing_decision.word_count,
            routing_reasons=routing_decision.reasons,
            confidence=result.confidence,
            flags=sorted(set(flags)),
            feedback=result.feedback,
            criterion_scores=result.criterion_scores,
            steps=steps,
        )
