from app.config import Settings
from app.schemas.api import ExamSessionGradingTaskCreate
from app.services.browser_navigation import BrowserNavigationService
from app.services.hybrid_automation_profiles import (
    matching_sanomapro_page_profiles,
    render_sanomapro_hybrid_automation_context,
)


def test_matching_sanomapro_page_profiles_returns_login_profile_for_auth_url() -> None:
    profiles = matching_sanomapro_page_profiles("https://www.sanomapro.fi/auth/login/")

    assert [profile.key for profile in profiles] == ["sanomapro_login"]


def test_matching_sanomapro_page_profiles_returns_grading_workflow_for_review_overview() -> None:
    profiles = matching_sanomapro_page_profiles("https://arvi.sanomapro.fi/as/teacher/assignment/demo/review")

    assert [profile.key for profile in profiles] == [
        "sanomapro_review_overview",
        "sanomapro_review_exercise",
    ]


def test_matching_sanomapro_page_profiles_returns_grading_workflow_for_review_exercise() -> None:
    profiles = matching_sanomapro_page_profiles(
        "https://arvi.sanomapro.fi/as/teacher/review/demo/activity/a/document/b/exercise?studentId=test"
    )

    assert [profile.key for profile in profiles] == [
        "sanomapro_review_overview",
        "sanomapro_review_exercise",
    ]


def test_render_sanomapro_hybrid_automation_context_includes_live_review_hooks() -> None:
    context = render_sanomapro_hybrid_automation_context(
        "https://arvi.sanomapro.fi/as/teacher/assignment/demo/review"
    )

    assert "div.review-assignment__document[ng-click=\"$ctrl.gotoReview(document, student)\"]" in context
    assert "input.manual-score[ng-model='ctrl.score'][ng-blur='ctrl.updateScore()']" in context
    assert "ctrl.gotoNextStudent()" in context


def test_build_exam_grading_task_includes_hybrid_automation_context_for_review_page() -> None:
    service = BrowserNavigationService(Settings())
    payload = ExamSessionGradingTaskCreate(instructions="Score Swedish answers.")

    task = service.build_exam_grading_task(
        payload,
        current_url="https://arvi.sanomapro.fi/as/teacher/assignment/demo/review",
    )

    assert "Hardcoded Hybrid Automation anchors:" in task
    assert "button.btn.btn-ghost[title='Poistu oppilaan vastauksista']" in task
    assert "div.review-assignment__document[ng-click=\"$ctrl.gotoReview(document, student)\"]" in task


def test_build_exam_grading_task_omits_hybrid_automation_context_without_known_url() -> None:
    service = BrowserNavigationService(Settings())
    payload = ExamSessionGradingTaskCreate(instructions="Score Swedish answers.")

    task = service.build_exam_grading_task(payload)

    assert "Hardcoded Hybrid Automation anchors:" not in task
