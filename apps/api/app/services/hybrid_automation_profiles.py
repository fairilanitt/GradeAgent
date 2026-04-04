from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class HybridAutomationSelector:
    key: str
    selector: str
    description: str


@dataclass(frozen=True)
class HybridAutomationDomSignal:
    key: str
    signal: str
    description: str


@dataclass(frozen=True)
class HybridAutomationPageProfile:
    key: str
    description: str
    url_patterns: tuple[str, ...]
    selectors: tuple[HybridAutomationSelector, ...]
    dom_signals: tuple[HybridAutomationDomSignal, ...] = ()
    text_markers: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def matches(self, url: str | None) -> bool:
        normalized_url = _normalize_url(url)
        if not normalized_url:
            return False
        return any(re.search(pattern, normalized_url) for pattern in self.url_patterns)

    def render_prompt_block(self) -> str:
        lines = [
            f"Page profile: {self.description}",
            f"Route patterns: {', '.join(self.url_patterns)}",
        ]
        if self.selectors:
            lines.append("CSS selectors:")
            for selector in self.selectors:
                lines.append(f"- {selector.key}: `{selector.selector}` ({selector.description})")
        if self.dom_signals:
            lines.append("DOM hooks:")
            for signal in self.dom_signals:
                lines.append(f"- {signal.key}: `{signal.signal}` ({signal.description})")
        if self.text_markers:
            lines.append(f"Visible text markers: {', '.join(f'`{marker}`' for marker in self.text_markers)}")
        if self.notes:
            lines.append("Notes:")
            for note in self.notes:
                lines.append(f"- {note}")
        return "\n".join(lines)


SANOMAPRO_LOGIN_PROFILE = HybridAutomationPageProfile(
    key="sanomapro_login",
    description="Sanoma Pro ForgeRock login",
    url_patterns=(
        r"kirjautuminen\.sanomapro\.fi/.+#login/?$",
        r"www\.sanomapro\.fi/auth/login/?$",
    ),
    selectors=(
        HybridAutomationSelector("login_root", "#login-base", "Sanoma Pro login shell root."),
        HybridAutomationSelector(
            "login_form",
            "form.form.login[data-stage='LDAP1']",
            "Primary username and password login form.",
        ),
        HybridAutomationSelector(
            "username_input",
            "#idToken1",
            "Username or email field captured from the live login page.",
        ),
        HybridAutomationSelector(
            "password_input",
            "#idToken2",
            "Password field captured from the live login page.",
        ),
        HybridAutomationSelector(
            "show_password_toggle",
            "#showPassword",
            "Checkbox that toggles the password field visibility.",
        ),
        HybridAutomationSelector(
            "submit_button",
            "#loginButton_0",
            "Primary sign-in submit button.",
        ),
        HybridAutomationSelector(
            "message_holder",
            "#message-holder",
            "Inline error and status message container.",
        ),
        HybridAutomationSelector(
            "forgot_password_link",
            "a[href*='#passwordReset']",
            "Forgot-password recovery link.",
        ),
    ),
    dom_signals=(
        HybridAutomationDomSignal("username_name", "name='callback_0'", "ForgeRock callback for username."),
        HybridAutomationDomSignal("password_name", "name='callback_1'", "ForgeRock callback for password."),
        HybridAutomationDomSignal("submit_name", "name='callback_2'", "ForgeRock callback for submit."),
        HybridAutomationDomSignal("login_stage", "data-stage='LDAP1'", "Current login stage identifier."),
    ),
    text_markers=(
        "Kirjaudu sisään",
        "Tunnus tai sähköpostiosoite",
        "Salasana",
        "Käytä MPASSid:tä",
    ),
    notes=(
        "Selectors were captured from the live Sanoma Pro login page on 2026-04-04.",
        "The login flow redirects from www.sanomapro.fi/auth/login/ to kirjautuminen.sanomapro.fi.",
    ),
)


SANOMAPRO_REVIEW_OVERVIEW_PROFILE = HybridAutomationPageProfile(
    key="sanomapro_review_overview",
    description="Sanoma Pro TEAS assignment review matrix",
    url_patterns=(
        r"arvi\.sanomapro\.fi/as/teacher/assignment/[^/]+/review(?:\?.*)?$",
    ),
    selectors=(
        HybridAutomationSelector(
            "back_button",
            "button.btn-back[title='Takaisin']",
            "Exit back to the previous TEAS page.",
        ),
        HybridAutomationSelector(
            "assignment_title",
            "h1",
            "Main review heading on the overview page.",
        ),
        HybridAutomationSelector(
            "hide_submissions_button",
            "button[title='Piilota suorituksia']",
            "Collapses or expands the review matrix.",
        ),
        HybridAutomationSelector(
            "students_completed_metric",
            "dd[data-testid='assignment-students-completed']",
            "Completed-students summary metric.",
        ),
        HybridAutomationSelector(
            "group_title",
            ".review-assignment__group-name",
            "Current student group heading.",
        ),
        HybridAutomationSelector(
            "student_name_cell",
            ".review-assignment__cell.review-assignment__cell--content",
            "Student name column cells.",
        ),
        HybridAutomationSelector(
            "student_status_icon",
            ".student-status-icon.icon-status-open-for-review",
            "Open-for-review status icon in the name column.",
        ),
        HybridAutomationSelector(
            "review_score_cell",
            "div.review-assignment__document[ng-click=\"$ctrl.gotoReview(document, student)\"]",
            "Clickable score cell that opens the detailed review route.",
        ),
        HybridAutomationSelector(
            "review_score_value",
            ".review-assignment__document-score",
            "Rendered score label inside each clickable score cell.",
        ),
        HybridAutomationSelector(
            "hide_grades_button",
            ".btn-hide-grades[ng-click*='hideGrades']",
            "Hide-grades action in the overview toolbar.",
        ),
        HybridAutomationSelector(
            "release_grades_button",
            ".btn-release-grades[ng-click='ctrl.releaseGrades()']",
            "Release-grades action in the overview toolbar.",
        ),
        HybridAutomationSelector(
            "edit_assignment_button",
            ".btn-edit-assessment[ng-click='ctrl.OpenAssessmentDialog()']",
            "Assessment edit dialog trigger.",
        ),
        HybridAutomationSelector(
            "completed_only_toggle",
            ".teas-switch[ng-model='$ctrl.showCompletedStudentsOnly']",
            "Toggle for hiding students without a submission.",
        ),
    ),
    dom_signals=(
        HybridAutomationDomSignal(
            "open_review",
            "$ctrl.gotoReview(document, student)",
            "Primary Angular hook for entering a student's detailed review page.",
        ),
        HybridAutomationDomSignal(
            "hide_grades",
            "ctrl.hideGrades(ctrl.assignment.hideGrades)",
            "Angular action behind the hide-grades button.",
        ),
        HybridAutomationDomSignal(
            "release_grades",
            "ctrl.releaseGrades()",
            "Angular action behind the release-grades button.",
        ),
        HybridAutomationDomSignal(
            "edit_assessment",
            "ctrl.OpenAssessmentDialog()",
            "Angular action behind the edit button.",
        ),
        HybridAutomationDomSignal(
            "show_completed_only",
            "$ctrl.showCompletedStudentsOnly",
            "Boolean switch model for the overview filter toggle.",
        ),
    ),
    text_markers=(
        "Tulokset",
        "Nimi",
        "Pisteet",
        "Arvosana",
        "Arvioitavissa",
    ),
    notes=(
        "The live review matrix uses review-assignment__document cells for per-student per-document navigation.",
        "The inner score label is separate from the outer clickable review-assignment__document wrapper.",
    ),
)


SANOMAPRO_REVIEW_EXERCISE_PROFILE = HybridAutomationPageProfile(
    key="sanomapro_review_exercise",
    description="Sanoma Pro TEAS per-student exercise review",
    url_patterns=(
        r"arvi\.sanomapro\.fi/as/teacher/review/[^/]+/activity/[^/]+/document/[^/]+/exercise(?:\?.*)?$",
    ),
    selectors=(
        HybridAutomationSelector(
            "exit_student_answers_button",
            "button.btn.btn-ghost[title='Poistu oppilaan vastauksista']",
            "Returns from the exercise view to the assignment review matrix.",
        ),
        HybridAutomationSelector(
            "feedback_toggle_button",
            "button.btn-toggle-feedback[ng-click='ctrl.toggleFeedback()']",
            "Opens the assignment feedback editor for the current student.",
        ),
        HybridAutomationSelector(
            "next_student_button",
            "button.student-feedback__student-navigation-button.right-button[ng-click='ctrl.gotoNextStudent()']",
            "Moves to the next student within the same exercise.",
        ),
        HybridAutomationSelector(
            "review_exercise_content",
            ".review-exercise-content",
            "Main review layout container for the opened exercise.",
        ),
        HybridAutomationSelector(
            "student_answer_panel",
            ".student-answer",
            "Container that renders the student's answer content.",
        ),
        HybridAutomationSelector(
            "interactions_review",
            ".interactions.interactions-review",
            "Exercise answer rendering block used during review.",
        ),
        HybridAutomationSelector(
            "student_answer_heading",
            "h4.contents[translate]",
            "Heading that labels the student answer section.",
        ),
        HybridAutomationSelector(
            "score_tab",
            "a[ng-click=\"ctrl.openTab('score')\"]",
            "Score tab in the right-side panel.",
        ),
        HybridAutomationSelector(
            "comments_tab",
            "a[ng-click=\"ctrl.openTab('annotations')\"]",
            "Comments tab in the right-side panel.",
        ),
        HybridAutomationSelector(
            "manual_score_input",
            "input.manual-score[ng-model='ctrl.score'][ng-blur='ctrl.updateScore()']",
            "Plain text input used to enter the numeric score.",
        ),
        HybridAutomationSelector(
            "assignment_feedback_textarea",
            "textarea[ng-model='ctrl.assignmentReview.feedback']",
            "Assignment-level student feedback field.",
        ),
        HybridAutomationSelector(
            "exercise_feedback_textarea",
            "textarea[ng-model='viewModel.ngModel']",
            "Exercise-level feedback field.",
        ),
        HybridAutomationSelector(
            "document_progress_link",
            "a[ng-click='ctrl.goToDocument(document)']",
            "Bottom progress navigation for switching exercises/documents.",
        ),
        HybridAutomationSelector(
            "next_document_button",
            "button.assessment-navigation-next[ng-click='ctrl.navigateNext()']",
            "Moves to the next document or exercise in the bottom navigator.",
        ),
    ),
    dom_signals=(
        HybridAutomationDomSignal(
            "update_score",
            "ctrl.updateScore()",
            "Blur handler that commits the numeric score input.",
        ),
        HybridAutomationDomSignal(
            "open_score_tab",
            "ctrl.openTab('score')",
            "Angular action for the score tab.",
        ),
        HybridAutomationDomSignal(
            "open_comments_tab",
            "ctrl.openTab('annotations')",
            "Angular action for the comments tab.",
        ),
        HybridAutomationDomSignal(
            "goto_next_student",
            "ctrl.gotoNextStudent()",
            "Angular action for the next-student button.",
        ),
        HybridAutomationDomSignal(
            "toggle_feedback",
            "ctrl.toggleFeedback()",
            "Angular action for the assignment feedback toggle.",
        ),
        HybridAutomationDomSignal(
            "assignment_feedback_model",
            "ctrl.assignmentReview.feedback",
            "Model used by the assignment feedback textarea.",
        ),
        HybridAutomationDomSignal(
            "exercise_feedback_model",
            "viewModel.ngModel",
            "Model used by the exercise-level feedback textarea.",
        ),
        HybridAutomationDomSignal(
            "document_progress_nav",
            "ctrl.goToDocument(document)",
            "Angular action behind the bottom document progress links.",
        ),
        HybridAutomationDomSignal(
            "next_document_nav",
            "ctrl.navigateNext()",
            "Angular action for the next-document wave button.",
        ),
    ),
    text_markers=(
        "Poistu oppilaan vastauksista",
        "Oppilaan vastaus",
        "Pistemäärä",
        "Kommentit",
        "Oppilas",
    ),
    notes=(
        "The detailed review route includes assignment, activity, document, and student identifiers in the URL.",
        "The numeric score field is a plain text input; Hybrid Automation should type only the number and let ctrl.updateScore() commit on blur.",
    ),
)


SANOMAPRO_GRADING_WORKFLOW_PROFILES = (
    SANOMAPRO_REVIEW_OVERVIEW_PROFILE,
    SANOMAPRO_REVIEW_EXERCISE_PROFILE,
)


def _normalize_url(url: str | None) -> str:
    return (url or "").strip().lower()


def _sanomapro_auth_url(url: str | None) -> bool:
    normalized_url = _normalize_url(url)
    if not normalized_url:
        return False
    parsed = urlparse(normalized_url)
    return parsed.netloc in {"www.sanomapro.fi", "kirjautuminen.sanomapro.fi"} and (
        "/auth/login" in parsed.path or "#login" in normalized_url
    )


def _sanomapro_grading_url(url: str | None) -> bool:
    normalized_url = _normalize_url(url)
    if not normalized_url:
        return False
    return "arvi.sanomapro.fi" in urlparse(normalized_url).netloc


def matching_sanomapro_page_profiles(url: str | None) -> tuple[HybridAutomationPageProfile, ...]:
    normalized_url = _normalize_url(url)
    if not normalized_url:
        return ()

    matched_profiles = tuple(
        profile
        for profile in (
            SANOMAPRO_LOGIN_PROFILE,
            SANOMAPRO_REVIEW_OVERVIEW_PROFILE,
            SANOMAPRO_REVIEW_EXERCISE_PROFILE,
        )
        if profile.matches(normalized_url)
    )
    if matched_profiles:
        if any(profile.key.startswith("sanomapro_review_") for profile in matched_profiles):
            return SANOMAPRO_GRADING_WORKFLOW_PROFILES
        return matched_profiles

    if _sanomapro_auth_url(normalized_url):
        return (SANOMAPRO_LOGIN_PROFILE,)
    if _sanomapro_grading_url(normalized_url):
        return SANOMAPRO_GRADING_WORKFLOW_PROFILES
    return ()


def render_sanomapro_hybrid_automation_context(url: str | None) -> str:
    profiles = matching_sanomapro_page_profiles(url)
    if not profiles:
        return ""

    lines = [
        "Use these hardcoded Sanoma Pro Hybrid Automation anchors before generic exploration.",
        "Selectors and DOM hooks were captured from live Sanoma Pro pages on 2026-04-04 via Playwright.",
    ]
    for profile in profiles:
        lines.append(profile.render_prompt_block())
    return "\n\n".join(lines)


def sanomapro_selector_map(url: str | None) -> dict[str, str]:
    selectors: dict[str, str] = {}
    for profile in matching_sanomapro_page_profiles(url):
        for selector in profile.selectors:
            selectors.setdefault(selector.key, selector.selector)
    return selectors


def sanomapro_selector(url: str | None, key: str) -> str | None:
    return sanomapro_selector_map(url).get(key)
