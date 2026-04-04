from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.models.domain import (
    Assessment,
    BrowserAutomationJob,
    GradeRun,
    ReviewDecision,
    RubricProfile,
    Submission,
)
from app.schemas.api import (
    AssessmentCreate,
    BrowserTaskCreate,
    BrowserTaskResult,
    GradeRunCreate,
    QueueGradingTaskCreate,
    QueueGradingTaskResult,
    ReleaseResponse,
    RuntimeCounts,
    RuntimeOverview,
    ReviewDecisionCreate,
    RubricProfileCreate,
    SubmissionCreate,
    TextScoringRequest,
    TextScoringResponse,
)
from app.services.browser_navigation import BrowserNavigationService
from app.services.grading_pipeline import GradingPipeline
from app.services.llm_provider import (
    ProviderConfigurationError,
    grading_model_name,
    grading_reasoning_mode,
    normalize_provider,
    resolve_provider_model_name,
    resolve_browser_model_name,
    should_use_heuristic_grading,
)
from app.services.release_service import ReleaseService
from app.services.rubric_validator import RubricValidator
from app.services.text_scoring import TextScoringService
from app.services.workflow_dispatcher import WorkflowDispatcher

router = APIRouter()
settings = get_settings()


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/assessments", response_model=Assessment, status_code=status.HTTP_201_CREATED)
def create_assessment(payload: AssessmentCreate, session: Session = Depends(get_session)) -> Assessment:
    assessment = Assessment.model_validate(payload)
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


@router.post("/rubric-profiles", response_model=RubricProfile, status_code=status.HTTP_201_CREATED)
def create_rubric_profile(
    payload: RubricProfileCreate,
    session: Session = Depends(get_session),
) -> RubricProfile:
    validator = RubricValidator()
    report = validator.validate_profile(payload)
    profile = RubricProfile(
        assessment_id=payload.assessment_id,
        name=payload.name,
        version=payload.version,
        criteria_json=[item.model_dump(mode="json") for item in payload.criteria],
        preferences_json=payload.preferences.model_dump(mode="json"),
        exemplar_answers_json=[item.model_dump(mode="json") for item in payload.exemplar_answers],
        status="active" if report["valid"] else "draft",
        validation_report_json=report,
    )
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


@router.post("/submissions", response_model=Submission, status_code=status.HTTP_201_CREATED)
def create_submission(payload: SubmissionCreate, session: Session = Depends(get_session)) -> Submission:
    if not session.get(Assessment, payload.assessment_id):
        raise HTTPException(status_code=404, detail="Assessment not found.")
    submission = Submission(
        assessment_id=payload.assessment_id,
        student_identifier=payload.student_identifier,
        answer_text=payload.answer_text,
        answer_html=payload.answer_html,
        language=payload.language,
        metadata_json=payload.metadata,
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)
    return submission


@router.post("/grade-runs", response_model=GradeRun, status_code=status.HTTP_201_CREATED)
async def create_grade_run(payload: GradeRunCreate, session: Session = Depends(get_session)) -> GradeRun:
    assessment = session.get(Assessment, payload.assessment_id)
    submission = session.get(Submission, payload.submission_id)
    rubric = session.get(RubricProfile, payload.rubric_profile_id)
    if not assessment or not submission or not rubric:
        raise HTTPException(status_code=404, detail="Assessment, submission, or rubric was not found.")

    grade_run = GradeRun(
        assessment_id=assessment.id,
        submission_id=submission.id,
        rubric_profile_id=rubric.id,
        routing_tier="pending",
        status="queued",
    )
    session.add(grade_run)
    session.commit()
    session.refresh(grade_run)

    if settings.temporal_enabled:
        await WorkflowDispatcher(settings).schedule_grade_run(grade_run.id)
        return grade_run

    pipeline = GradingPipeline()
    try:
        return await pipeline.persist_grade_run(session, grade_run, assessment, submission, rubric)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/text-scoring/score", response_model=TextScoringResponse)
async def score_text_submission(payload: TextScoringRequest) -> TextScoringResponse:
    try:
        return await TextScoringService().score_text(payload)
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/grade-runs/{grade_run_id}", response_model=GradeRun)
def get_grade_run(grade_run_id: str, session: Session = Depends(get_session)) -> GradeRun:
    grade_run = session.get(GradeRun, grade_run_id)
    if not grade_run:
        raise HTTPException(status_code=404, detail="Grade run not found.")
    return grade_run


@router.post("/rubric-profiles/{rubric_profile_id}/validate")
def validate_rubric_profile(rubric_profile_id: str, session: Session = Depends(get_session)) -> dict:
    profile = session.get(RubricProfile, rubric_profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Rubric profile not found.")

    payload = RubricProfileCreate(
        assessment_id=profile.assessment_id,
        name=profile.name,
        version=profile.version,
        criteria=profile.criteria_json,
        preferences=profile.preferences_json,
        exemplar_answers=profile.exemplar_answers_json,
    )
    report = RubricValidator().validate_profile(payload)
    profile.validation_report_json = report
    profile.updated_at = datetime.now(timezone.utc)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return report


@router.post("/reviews/{grade_run_id}/approve", response_model=ReviewDecision, status_code=status.HTTP_201_CREATED)
def approve_grade_run(
    grade_run_id: str,
    payload: ReviewDecisionCreate,
    session: Session = Depends(get_session),
) -> ReviewDecision:
    grade_run = session.get(GradeRun, grade_run_id)
    if not grade_run:
        raise HTTPException(status_code=404, detail="Grade run not found.")
    grade_run.status = "approved"
    grade_run.updated_at = datetime.now(timezone.utc)
    session.add(grade_run)
    decision = ReviewDecision(
        grade_run_id=grade_run_id,
        reviewer_id=payload.reviewer_id,
        decision="approved",
        notes=payload.notes,
        overridden_result_json=grade_run.result_json,
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


@router.post("/reviews/{grade_run_id}/override", response_model=ReviewDecision, status_code=status.HTTP_201_CREATED)
def override_grade_run(
    grade_run_id: str,
    payload: ReviewDecisionCreate,
    session: Session = Depends(get_session),
) -> ReviewDecision:
    grade_run = session.get(GradeRun, grade_run_id)
    if not grade_run:
        raise HTTPException(status_code=404, detail="Grade run not found.")
    if not payload.overridden_result:
        raise HTTPException(status_code=400, detail="Override requires an overridden_result payload.")

    grade_run.status = "overridden"
    grade_run.result_json = payload.overridden_result.model_dump(mode="json")
    grade_run.feedback_text = payload.overridden_result.feedback
    grade_run.updated_at = datetime.now(timezone.utc)
    session.add(grade_run)
    decision = ReviewDecision(
        grade_run_id=grade_run_id,
        reviewer_id=payload.reviewer_id,
        decision="overridden",
        notes=payload.notes,
        overridden_result_json=payload.overridden_result.model_dump(mode="json"),
    )
    session.add(decision)
    session.commit()
    session.refresh(decision)
    return decision


@router.post("/releases/{assessment_id}/publish", response_model=ReleaseResponse)
def publish_assessment(assessment_id: str, session: Session = Depends(get_session)) -> ReleaseResponse:
    if not session.get(Assessment, assessment_id):
        raise HTTPException(status_code=404, detail="Assessment not found.")
    released_count, released_at = ReleaseService().publish(session, assessment_id)
    return ReleaseResponse(
        assessment_id=assessment_id,
        released_count=released_count,
        released_at=released_at,
    )


@router.post("/browser-tasks/run", response_model=BrowserTaskResult)
async def run_browser_task(
    payload: BrowserTaskCreate,
    session: Session = Depends(get_session),
) -> BrowserTaskResult:
    job = BrowserAutomationJob(target_url=payload.target_url, instruction=payload.instruction, status="running")
    session.add(job)
    session.commit()
    session.refresh(job)

    result = await BrowserNavigationService().navigate(payload, job.id)
    job.status = result.status
    job.result_json = result.model_dump(mode="json")
    job.updated_at = datetime.now(timezone.utc)
    session.add(job)
    session.commit()
    return result


@router.post("/browser-tasks/grade-queue", response_model=QueueGradingTaskResult)
async def run_queue_grading_task(
    payload: QueueGradingTaskCreate,
    session: Session = Depends(get_session),
) -> QueueGradingTaskResult:
    criteria_summary = ", ".join(item.label for item in payload.criteria)
    job = BrowserAutomationJob(
        target_url=payload.target_url,
        instruction=f"Queue grading with criteria: {criteria_summary}",
        status="running",
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    result = await BrowserNavigationService().grade_queue(payload, job.id)
    job.status = result.status
    job.result_json = result.model_dump(mode="json")
    job.updated_at = datetime.now(timezone.utc)
    session.add(job)
    session.commit()
    return result


@router.get("/runtime/overview", response_model=RuntimeOverview)
def get_runtime_overview(session: Session = Depends(get_session)) -> RuntimeOverview:
    active_rubrics = session.exec(select(RubricProfile).where(RubricProfile.status == "active")).all()
    model_router_provider = normalize_provider(settings.model_router_provider)
    browser_agent_provider = normalize_provider(settings.browser_agent_provider)
    sanomapro_provider, sanomapro_model = resolve_provider_model_name(
        settings.sanomapro_exercise_grading_provider,
        settings.sanomapro_exercise_grading_model,
        settings,
    )
    return RuntimeOverview(
        app_name=settings.app_name,
        model_router_provider=model_router_provider,
        model_router_simple_model=settings.model_router_simple_model,
        model_router_standard_model=settings.model_router_standard_model,
        model_router_complex_model=grading_model_name(settings, "complex")
        if model_router_provider in {"google", "vertex_ai"}
        else settings.model_router_complex_model,
        sanomapro_exercise_grading_provider=sanomapro_provider,
        sanomapro_exercise_grading_model=sanomapro_model,
        ollama_simple_reasoning_mode=grading_reasoning_mode(settings, "simple"),
        ollama_standard_reasoning_mode=grading_reasoning_mode(settings, "standard"),
        ollama_complex_reasoning_mode=grading_reasoning_mode(settings, "complex"),
        browser_agent_provider=browser_agent_provider,
        browser_agent_model=resolve_browser_model_name(settings),
        browser_agent_use_thinking=settings.browser_agent_use_thinking,
        ollama_host=settings.ollama_host,
        heuristic_fallback_enabled=should_use_heuristic_grading(settings),
        temporal_enabled=settings.temporal_enabled,
        browser_headless=settings.browser_headless,
        browser_use_system_chrome=settings.browser_use_system_chrome,
        browser_chrome_profile_directory=settings.browser_chrome_profile_directory,
        browser_persistent_profile_dir=settings.browser_persistent_profile_dir,
        counts=RuntimeCounts(
            assessments=len(session.exec(select(Assessment)).all()),
            submissions=len(session.exec(select(Submission)).all()),
            grade_runs=len(session.exec(select(GradeRun)).all()),
            browser_jobs=len(session.exec(select(BrowserAutomationJob)).all()),
            active_rubrics=len(active_rubrics),
        ),
    )


@router.get("/assessments/{assessment_id}/review")
def get_assessment_review(assessment_id: str, session: Session = Depends(get_session)) -> dict:
    assessment = session.get(Assessment, assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    submissions = session.exec(select(Submission).where(Submission.assessment_id == assessment_id)).all()
    grade_runs = session.exec(select(GradeRun).where(GradeRun.assessment_id == assessment_id)).all()
    rubric = session.get(RubricProfile, assessment.rubric_profile_id) if assessment.rubric_profile_id else None
    return {
        "assessment": assessment.model_dump(mode="json"),
        "rubric": rubric.model_dump(mode="json") if rubric else None,
        "submissions": [item.model_dump(mode="json") for item in submissions],
        "grade_runs": [item.model_dump(mode="json") for item in grade_runs],
    }
