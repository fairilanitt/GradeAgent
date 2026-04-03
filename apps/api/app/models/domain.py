from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, Text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def json_column() -> Column:
    return Column(JSON, nullable=False)


class TimestampedModel(SQLModel):
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )


class Assessment(TimestampedModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    course_code: str
    title: str
    task_type: str
    language: str = "sv"
    scale_max: int = 100
    release_mode: str = "teacher_batch_publish"
    is_exam: bool = False
    rubric_profile_id: str | None = Field(default=None, index=True)


class RubricProfile(TimestampedModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    assessment_id: str | None = Field(default=None, index=True)
    name: str
    version: int = 1
    status: str = "draft"
    criteria_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=json_column())
    preferences_json: dict[str, Any] = Field(default_factory=dict, sa_column=json_column())
    exemplar_answers_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=json_column())
    validation_report_json: dict[str, Any] = Field(default_factory=dict, sa_column=json_column())


class Submission(TimestampedModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    assessment_id: str = Field(index=True)
    student_identifier: str = Field(index=True)
    answer_text: str = Field(sa_column=Column(Text, nullable=False))
    answer_html: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    language: str = "sv"
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=json_column())


class GradeRun(TimestampedModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    assessment_id: str = Field(index=True)
    submission_id: str = Field(index=True)
    rubric_profile_id: str = Field(index=True)
    routing_tier: str = Field(sa_column=Column("lane", Text, nullable=False))
    status: str = "queued"
    reviewer_required: bool = True
    confidence: float = 0.0
    feedback_text: str = Field(default="", sa_column=Column(Text, nullable=False))
    model_summary: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    policy_flags_json: list[str] = Field(default_factory=list, sa_column=json_column())
    result_json: dict[str, Any] = Field(default_factory=dict, sa_column=json_column())
    audit_snapshot_json: dict[str, Any] = Field(default_factory=dict, sa_column=json_column())


class ReviewDecision(TimestampedModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    grade_run_id: str = Field(index=True)
    reviewer_id: str
    decision: str
    notes: str = Field(default="", sa_column=Column(Text, nullable=False))
    overridden_result_json: dict[str, Any] = Field(default_factory=dict, sa_column=json_column())
    released_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class BrowserAutomationJob(TimestampedModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    target_url: str
    instruction: str = Field(sa_column=Column(Text, nullable=False))
    status: str = "queued"
    result_json: dict[str, Any] = Field(default_factory=dict, sa_column=json_column())


class EvaluationSet(TimestampedModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    assessment_id: str | None = Field(default=None, index=True)
    name: str
    examples_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=json_column())
    metrics_json: dict[str, Any] = Field(default_factory=dict, sa_column=json_column())
