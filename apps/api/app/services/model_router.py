from __future__ import annotations

from abc import ABC, abstractmethod
from difflib import SequenceMatcher
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.schemas.api import CriterionDefinition, StructuredGradeResult
from app.services.llm_provider import (
    RoutingTier,
    build_grading_chat_model,
    extract_json_object,
    flatten_llm_content,
    grading_model_name,
    grading_provider,
    should_use_heuristic_grading,
)


class GradeRequest(BaseModel):
    assessment_title: str
    task_type: str
    is_exam: bool
    answer_text: str
    language: str
    criteria: list[CriterionDefinition]
    preferences: dict[str, Any]
    exemplars: list[dict[str, Any]]


class RoutingDecision(BaseModel):
    routing_tier: RoutingTier
    provider: str
    model_name: str
    complexity_score: int = Field(ge=0)
    word_count: int = Field(ge=0)
    reasons: list[str] = Field(default_factory=list)


def resolve_routing_decision(
    settings: Settings,
    payload: GradeRequest,
    provider_override: str | None = None,
) -> RoutingDecision:
    answer = payload.answer_text.strip()
    word_count = len(answer.split())
    criteria_count = len(payload.criteria)
    guidance_words = len(str(payload.preferences.get("grading_guidance", "")).split())
    score = 0
    reasons: list[str] = []

    if word_count <= 4:
        reasons.append("single_word_or_phrase_submission")
    elif word_count <= 24:
        score += 1
        reasons.append("short_response")
    elif word_count <= 90:
        score += 3
        reasons.append("paragraph_length_response")
    else:
        score += 5
        reasons.append("long_response")

    if "\n" in answer:
        score += 1
        reasons.append("multi_line_submission")

    if criteria_count >= 3:
        score += 1
        reasons.append("multi_criterion_rubric")

    if criteria_count >= 5:
        score += 1
        reasons.append("dense_rubric")

    if any(item.expected_answer for item in payload.criteria):
        score += 1
        reasons.append("expected_answer_matching")

    if guidance_words >= 18:
        score += 1
        reasons.append("custom_teacher_guidance")

    if payload.exemplars:
        score += 1
        reasons.append("exemplar_context_available")

    if payload.is_exam:
        score += 2
        reasons.append("exam_mode")

    if payload.task_type.lower() in {"essay", "exam", "long_answer", "paragraph"}:
        score += 1
        reasons.append("extended_text_task")

    if score <= 2:
        routing_tier: RoutingTier = "simple"
    elif score <= 4:
        routing_tier = "standard"
    else:
        routing_tier = "complex"

    provider = provider_override or grading_provider(settings)
    model_name = "local-ruleset" if provider == "heuristic" else grading_model_name(settings, routing_tier)
    if provider == "google":
        configured_model = (
            settings.model_router_simple_model
            if routing_tier == "simple"
            else settings.model_router_standard_model
            if routing_tier == "standard"
            else settings.model_router_complex_model
        )
        if model_name != configured_model:
            reasons.append("google_free_tier_fallback")
    if not reasons:
        reasons.append("default_simple_routing")

    return RoutingDecision(
        routing_tier=routing_tier,
        provider=provider,
        model_name=model_name,
        complexity_score=score,
        word_count=word_count,
        reasons=reasons,
    )


class ModelRouter(ABC):
    @abstractmethod
    def route(self, payload: GradeRequest) -> RoutingDecision:
        raise NotImplementedError

    @abstractmethod
    async def grade(
        self,
        payload: GradeRequest,
        routing_decision: RoutingDecision | None = None,
    ) -> StructuredGradeResult:
        raise NotImplementedError


class HeuristicModelRouter(ModelRouter):
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def route(self, payload: GradeRequest) -> RoutingDecision:
        return resolve_routing_decision(self.settings, payload, provider_override="heuristic")

    async def grade(
        self,
        payload: GradeRequest,
        routing_decision: RoutingDecision | None = None,
    ) -> StructuredGradeResult:
        decision = routing_decision or self.route(payload)
        answer = payload.answer_text.strip()
        if not answer:
            return StructuredGradeResult(
                overall_score=0,
                max_score=sum(item.max_score for item in payload.criteria),
                grade_band="F",
                feedback="Inget svar hittades. Läraren behöver granska och eventuellt be om komplettering.",
                confidence=0.98,
                flags=["blank_answer"],
                criterion_scores=[
                    {
                        "criterion_id": item.id,
                        "label": item.label,
                        "score": 0,
                        "max_score": item.max_score,
                        "rationale": "No answer content was available.",
                        "evidence": [{"excerpt": "", "reason": "No answer text to cite."}],
                    }
                    for item in payload.criteria
                ],
            )

        criterion_scores = []
        weighted_score = 0.0
        weight_total = sum(item.weight for item in payload.criteria) or 1.0
        max_score = sum(item.max_score for item in payload.criteria)
        answer_lower = answer.lower()

        for criterion in payload.criteria:
            score_ratio = 0.35
            evidence = []
            if criterion.expected_answer:
                similarity = SequenceMatcher(None, answer_lower, criterion.expected_answer.lower()).ratio()
                score_ratio = max(score_ratio, similarity)
                if similarity > 0.55:
                    evidence.append(
                        {
                            "excerpt": answer[:160],
                            "reason": "Answer overlaps strongly with the expected phrasing.",
                        }
                    )
            elif criterion.keywords:
                matches = [keyword for keyword in criterion.keywords if keyword.lower() in answer_lower]
                score_ratio = min(1.0, max(score_ratio, len(matches) / max(len(criterion.keywords), 1)))
                if matches:
                    evidence.append(
                        {
                            "excerpt": ", ".join(matches),
                            "reason": "Matched rubric keywords in the response.",
                        }
                    )
            else:
                density = min(len(answer.split()) / 120, 1.0)
                score_ratio = min(1.0, max(score_ratio, 0.45 + density * 0.4))
                evidence.append(
                    {
                        "excerpt": answer[:160],
                        "reason": "Used the response body as supporting evidence.",
                    }
                )

            criterion_score = round(criterion.max_score * score_ratio, 2)
            weighted_score += criterion_score * criterion.weight
            criterion_scores.append(
                {
                    "criterion_id": criterion.id,
                    "label": criterion.label,
                    "score": criterion_score,
                    "max_score": criterion.max_score,
                    "rationale": f"Initial {decision.routing_tier} routing estimate using rubric overlap heuristics.",
                    "evidence": evidence or [{"excerpt": answer[:120], "reason": "Generic answer excerpt."}],
                }
            )

        overall_score = round(weighted_score / weight_total, 2)
        percentage = overall_score / max(max_score, 1)
        grade_band = (
            "A"
            if percentage >= 0.9
            else "B"
            if percentage >= 0.8
            else "C"
            if percentage >= 0.7
            else "D"
            if percentage >= 0.6
            else "E"
            if percentage >= 0.5
            else "F"
        )
        confidence_by_tier = {"simple": 0.76, "standard": 0.8, "complex": 0.84}
        confidence = confidence_by_tier[decision.routing_tier]

        feedback_language = payload.preferences.get("feedback_language", "sv")
        feedback = (
            "Bedömningen följer lärarens aktuella kriterier. Kontrollera särskilt nyanser och språkbruk innan poängen sparas."
            if feedback_language == "sv"
            else "Arvio perustuu opettajan nykyisiin kriteereihin. Tarkista vivahteet ennen pisteiden tallennusta."
        )

        return StructuredGradeResult(
            overall_score=overall_score,
            max_score=max_score,
            grade_band=grade_band,
            feedback=feedback,
            confidence=confidence,
            flags=[],
            criterion_scores=criterion_scores,
        )


class ManagedModelRouter(ModelRouter):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.heuristic_router = HeuristicModelRouter(settings)

    def route(self, payload: GradeRequest) -> RoutingDecision:
        return resolve_routing_decision(self.settings, payload)

    async def grade(
        self,
        payload: GradeRequest,
        routing_decision: RoutingDecision | None = None,
    ) -> StructuredGradeResult:
        decision = routing_decision or self.route(payload)
        if decision.provider == "heuristic":
            return await self.heuristic_router.grade(payload, decision)

        model = build_grading_chat_model(self.settings, decision.routing_tier)
        parser = PydanticOutputParser(pydantic_object=StructuredGradeResult)
        criteria_text = "\n".join(
            f"- {item.id}: {item.label} (max {item.max_score}, weight {item.weight}) :: {item.description}"
            for item in payload.criteria
        )
        response = await model.ainvoke(
            [
                SystemMessage(
                    content=(
                        "You are a careful grading assistant for Swedish-language responses written by Finnish students. "
                        "Your job is to read one submitted text and decide how many points should be entered into the grading form. "
                        "Never reveal hidden reasoning. Return only machine-readable JSON that matches the required schema."
                    )
                ),
                HumanMessage(
                    content=f"""
Assessment: {payload.assessment_title}
Task type: {payload.task_type}
Exam mode: {payload.is_exam}
Routing tier: {decision.routing_tier}
Selected model: {decision.model_name}
Complexity score: {decision.complexity_score}
Routing reasons: {", ".join(decision.reasons)}
Feedback language: {payload.preferences.get("feedback_language", "sv")}
Teacher tone: {payload.preferences.get("tone", "supportive")}
Teacher strictness: {payload.preferences.get("strictness", "balanced")}
Teacher guidance: {payload.preferences.get("grading_guidance", "")}

Rubric:
{criteria_text}

Exemplars:
{payload.exemplars}

Student answer:
{payload.answer_text}

Requirements:
- Score criterion by criterion.
- Cite short evidence excerpts from the answer for every criterion.
- Keep rationale concise and review-safe.
- Add flags for blank, off-topic, mixed-language, or low-confidence cases.
- Return valid JSON only.

JSON schema instructions:
{parser.get_format_instructions()}
""".strip()
                ),
            ]
        )

        text = flatten_llm_content(response.content)
        try:
            return parser.parse(text)
        except Exception:
            return StructuredGradeResult.model_validate_json(extract_json_object(text))


def get_model_router(settings: Settings | None = None) -> ModelRouter:
    config = settings or get_settings()
    if should_use_heuristic_grading(config):
        return HeuristicModelRouter(config)
    return ManagedModelRouter(config)
