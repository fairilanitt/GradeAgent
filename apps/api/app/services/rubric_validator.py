from __future__ import annotations

from typing import Any

from app.schemas.api import CriterionDefinition, RubricProfileCreate, StructuredGradeResult


class RubricValidator:
    def validate_profile(self, profile: RubricProfileCreate) -> dict[str, Any]:
        issues: list[str] = []
        warnings: list[str] = []

        if not profile.criteria:
            issues.append("Rubric must include at least one criterion.")

        total_weight = sum(item.weight for item in profile.criteria)
        if total_weight <= 0:
            issues.append("Criterion weights must sum to a positive number.")

        seen_ids: set[str] = set()
        for criterion in profile.criteria:
            if criterion.id in seen_ids:
                issues.append(f"Duplicate criterion id: {criterion.id}")
            seen_ids.add(criterion.id)
            if criterion.max_score <= 0:
                issues.append(f"Criterion {criterion.id} must have max_score > 0.")
            if not criterion.description.strip():
                warnings.append(f"Criterion {criterion.id} is missing a description.")

        if profile.preferences.feedback_language not in {"sv", "fi", "en"}:
            warnings.append("Feedback language should normally be sv, fi, or en.")

        return {
            "valid": not issues,
            "issues": issues,
            "warnings": warnings,
            "compiled_preferences": profile.preferences.model_dump(),
        }

    def validate_grade_result(
        self,
        grade: StructuredGradeResult,
        criteria: list[CriterionDefinition],
    ) -> list[str]:
        flags: list[str] = list(grade.flags)
        expected = {criterion.id: criterion for criterion in criteria}

        if grade.overall_score > grade.max_score:
            flags.append("overall_score_exceeds_max")

        for item in grade.criterion_scores:
            criterion = expected.get(item.criterion_id)
            if criterion is None:
                flags.append(f"unexpected_criterion:{item.criterion_id}")
                continue
            if item.score > item.max_score or item.score > criterion.max_score:
                flags.append(f"criterion_score_exceeds_max:{item.criterion_id}")
            if not item.evidence:
                flags.append(f"missing_evidence:{item.criterion_id}")

        return sorted(set(flags))
