from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CriterionDefinition(BaseModel):
    id: str
    label: str
    description: str
    max_score: float = Field(gt=0)
    weight: float = Field(gt=0, default=1.0)
    keywords: list[str] = Field(default_factory=list)
    expected_answer: str | None = None


class TeacherPreferenceConfig(BaseModel):
    tone: str = "supportive"
    strictness: str = "balanced"
    feedback_language: str = "sv"
    grading_guidance: str = ""
    banned_inferences: list[str] = Field(
        default_factory=lambda: ["ethnicity", "health", "religion", "gender identity"]
    )


class ExemplarAnswer(BaseModel):
    answer: str
    score: float
    rationale: str


class AssessmentCreate(BaseModel):
    course_code: str
    title: str
    task_type: str
    language: str = "sv"
    scale_max: int = 100
    release_mode: str = "teacher_batch_publish"
    is_exam: bool = False
    rubric_profile_id: str | None = None


class RubricProfileCreate(BaseModel):
    assessment_id: str | None = None
    name: str
    version: int = 1
    criteria: list[CriterionDefinition]
    preferences: TeacherPreferenceConfig = Field(default_factory=TeacherPreferenceConfig)
    exemplar_answers: list[ExemplarAnswer] = Field(default_factory=list)


class SubmissionCreate(BaseModel):
    assessment_id: str
    student_identifier: str
    answer_text: str
    answer_html: str | None = None
    language: str = "sv"
    metadata: dict[str, Any] = Field(default_factory=dict)


class GradeRunCreate(BaseModel):
    assessment_id: str
    submission_id: str
    rubric_profile_id: str


class TextScoringRequest(BaseModel):
    task_title: str = "Text submission scoring"
    submission_text: str
    criteria: list[CriterionDefinition]
    language: str = "sv"
    preferences: TeacherPreferenceConfig = Field(default_factory=TeacherPreferenceConfig)


class EvidenceSpan(BaseModel):
    excerpt: str
    reason: str


class CriterionScoreResult(BaseModel):
    criterion_id: str
    label: str
    score: float
    max_score: float
    rationale: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ProcessStep(BaseModel):
    name: str
    status: Literal["pending", "running", "completed", "failed"] = "completed"
    detail: str


class StructuredGradeResult(BaseModel):
    overall_score: float
    max_score: float
    grade_band: str
    feedback: str
    confidence: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)
    criterion_scores: list[CriterionScoreResult]


class TextScoringResponse(BaseModel):
    points_to_enter: float
    max_points: float
    routing_tier: str
    model_provider: str
    model_name: str
    complexity_score: int = Field(ge=0)
    submission_word_count: int = Field(ge=0)
    routing_reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list)
    feedback: str
    criterion_scores: list[CriterionScoreResult]
    steps: list[ProcessStep] = Field(default_factory=list)


class ReviewDecisionCreate(BaseModel):
    reviewer_id: str
    notes: str = ""
    overridden_result: StructuredGradeResult | None = None


class ReleaseResponse(BaseModel):
    assessment_id: str
    released_count: int
    released_at: datetime


class BrowserTaskCreate(BaseModel):
    target_url: str
    instruction: str
    screenshot_path: str | None = None


class QueueGradingTaskCreate(BaseModel):
    target_url: str
    criteria: list[CriterionDefinition]
    preferences: TeacherPreferenceConfig = Field(default_factory=TeacherPreferenceConfig)
    task_title: str = "Web platform text grading queue"
    queue_instruction: str = "Find the next ungraded text exercise."
    points_field_hint: str = "Look for the separate numeric points field."
    max_items: int = Field(default=1, ge=1, le=50)
    dry_run: bool = False
    submit_after_typing: bool = False
    screenshot_path: str | None = None


class ExamSessionGradingTaskCreate(BaseModel):
    instructions: str
    dry_run: bool = False
    submit_after_typing: bool = False
    max_steps: int = Field(default=260, ge=20, le=800)
    screenshot_path: str | None = None


class QueueGradingAgentOutput(BaseModel):
    summary: str
    processed_items: int = 0
    queue_empty: bool = False
    last_points_entered: float | None = None
    last_submission_excerpt: str | None = None


class ExamSessionGradingAgentOutput(BaseModel):
    summary: str
    processed_answers: int = 0
    skipped_dark_blue_boxes: int = 0
    completed_exercise_columns: int = 0
    filled_point_fields: int = 0
    current_exercise_label: str | None = None
    current_student_name: str | None = None


class BrowserTaskResult(BaseModel):
    job_id: str
    status: str
    summary: str
    agent_provider: str | None = None
    agent_model: str | None = None
    current_url: str | None = None
    screenshot_path: str | None = None
    extracted_text: str | None = None
    steps: list[ProcessStep] = Field(default_factory=list)


class QueueGradingTaskResult(BrowserTaskResult):
    processed_items: int = 0
    queue_empty: bool = False
    last_points_entered: float | None = None
    last_submission_excerpt: str | None = None


class ExamSessionGradingTaskResult(BrowserTaskResult):
    processed_answers: int = 0
    skipped_dark_blue_boxes: int = 0
    completed_exercise_columns: int = 0
    filled_point_fields: int = 0
    current_exercise_label: str | None = None
    current_student_name: str | None = None
    report_path: str | None = None


class GuiPromptTemplate(BaseModel):
    prompt_id: str
    title: str
    body: str
    built_in: bool = False


class GuiPromptSaveRequest(BaseModel):
    prompt_id: str | None = None
    title: str
    body: str


class GuiExerciseColumn(BaseModel):
    column_key: str
    title: str
    category_name: str | None = None
    exercise_number: str | None = None
    total_cell_count: int = 0
    reviewed_cell_count: int = 0
    pending_cell_count: int = 0


class GuiStateResponse(BaseModel):
    browser_ready: bool = False
    session_id: str | None = None
    prompt_count: int = 0


class GuiBrowserStartResponse(BaseModel):
    session_id: str
    browser_ready: bool = True


class GuiOverviewResponse(BaseModel):
    assignment_title: str = ""
    group_name: str | None = None
    students_answered_count: int | None = None
    students_total_count: int | None = None
    exercises: list[GuiExerciseColumn] = Field(default_factory=list)


class GuiGradeExerciseRequest(BaseModel):
    column_key: str
    instructions: str
    prompt_id: str | None = None
    prompt_title: str | None = None
    max_steps: int = Field(default=260, ge=20, le=800)


class GuiGradeExerciseResponse(BaseModel):
    result: ExamSessionGradingTaskResult
    exercises: list[GuiExerciseColumn] = Field(default_factory=list)


class GuiStatisticsEntry(BaseModel):
    student_name: str = ""
    student_progress: str | None = None
    assignment_title: str = ""
    group_name: str | None = None
    category_name: str | None = None
    exercise_label: str | None = None
    exercise_number: str | None = None
    objective_text: str = ""
    target_text: str = ""
    question_text: str = ""
    answer_text: str = ""
    model_answer_text: str = ""
    points_text: str = ""
    score_awarded: float | None = None
    score_possible: float | None = None
    basis_lines: list[str] = Field(default_factory=list)
    prompt_template_text: str = ""
    rendered_instructions_text: str = ""
    submitted_prompt_text: str = ""
    model_provider: str | None = None
    model_name: str | None = None
    model_response_text: str = ""
    repair_prompt_text: str = ""
    repair_response_text: str = ""
    used_heuristic_fallback: bool = False
    fallback_reason: str = ""
    exercise_url: str = ""
    status: str = "scored"


class GuiStatisticsRun(BaseModel):
    run_id: str
    job_id: str
    recorded_at: datetime
    status: str
    summary: str
    assignment_title: str = ""
    group_name: str | None = None
    category_name: str | None = None
    exercise_label: str | None = None
    exercise_number: str | None = None
    students_answered_count: int | None = None
    students_total_count: int | None = None
    processed_answers: int = 0
    filled_point_fields: int = 0
    report_path: str | None = None
    prompt_id: str | None = None
    prompt_title: str | None = None
    entries: list[GuiStatisticsEntry] = Field(default_factory=list)


class GuiStatisticsResponse(BaseModel):
    runs: list[GuiStatisticsRun] = Field(default_factory=list)


class RuntimeCounts(BaseModel):
    assessments: int = 0
    submissions: int = 0
    grade_runs: int = 0
    browser_jobs: int = 0
    active_rubrics: int = 0


class RuntimeOverview(BaseModel):
    app_name: str
    model_router_provider: str
    model_router_simple_model: str
    model_router_standard_model: str
    model_router_complex_model: str
    sanomapro_exercise_grading_provider: str
    sanomapro_exercise_grading_model: str
    ollama_simple_reasoning_mode: str | bool
    ollama_standard_reasoning_mode: str | bool
    ollama_complex_reasoning_mode: str | bool
    browser_agent_provider: str
    browser_agent_model: str
    browser_agent_use_thinking: bool
    ollama_host: str | None = None
    heuristic_fallback_enabled: bool
    temporal_enabled: bool
    browser_headless: bool
    browser_use_system_chrome: bool
    browser_chrome_profile_directory: str | None = None
    browser_persistent_profile_dir: str | None = None
    counts: RuntimeCounts
