from datetime import datetime, timezone

from app.prompt_library import PromptTemplate
from app.schemas.api import ExamSessionGradingTaskResult
from app.services.browser_navigation import SanomaOverviewExerciseColumn, SanomaOverviewState


def test_full_grading_review_release_flow(client) -> None:
    rubric = client.post(
        "/api/rubric-profiles",
        json={
            "name": "Swedish essay rubric",
            "criteria": [
                {
                    "id": "content",
                    "label": "Content",
                    "description": "Addresses the task clearly.",
                    "max_score": 10,
                    "weight": 1,
                    "keywords": ["klimat", "framtid"],
                },
                {
                    "id": "language",
                    "label": "Language",
                    "description": "Swedish language accuracy and clarity.",
                    "max_score": 10,
                    "weight": 1,
                    "keywords": ["svenska", "språk"],
                },
            ],
            "preferences": {
                "tone": "supportive",
                "strictness": "balanced",
                "feedback_language": "sv",
                "grading_guidance": "Prioritize communicative success.",
            },
            "exemplar_answers": [],
        },
    )
    rubric.raise_for_status()
    rubric_id = rubric.json()["id"]

    assessment = client.post(
        "/api/assessments",
        json={
            "course_code": "SVE101",
            "title": "Essay about climate",
            "task_type": "essay",
            "language": "sv",
            "scale_max": 20,
            "rubric_profile_id": rubric_id,
        },
    )
    assessment.raise_for_status()
    assessment_id = assessment.json()["id"]

    submission = client.post(
        "/api/submissions",
        json={
            "assessment_id": assessment_id,
            "student_identifier": "student-1",
            "answer_text": "Jag skriver om klimat och framtid. Svenska språk är viktigt för tydlig kommunikation.",
            "language": "sv",
        },
    )
    submission.raise_for_status()
    submission_id = submission.json()["id"]

    grade_run = client.post(
        "/api/grade-runs",
        json={
            "assessment_id": assessment_id,
            "submission_id": submission_id,
            "rubric_profile_id": rubric_id,
        },
    )
    grade_run.raise_for_status()
    assert grade_run.json()["status"] == "awaiting_review"
    assert grade_run.json()["reviewer_required"] is True
    assert grade_run.json()["routing_tier"] in {"simple", "standard", "complex"}

    grade_run_id = grade_run.json()["id"]
    approval = client.post(
        f"/api/reviews/{grade_run_id}/approve",
        json={"reviewer_id": "teacher-1", "notes": "Looks good."},
    )
    approval.raise_for_status()
    assert approval.json()["decision"] == "approved"

    release = client.post(f"/api/releases/{assessment_id}/publish")
    release.raise_for_status()
    assert release.json()["released_count"] == 1


def test_override_requires_payload(client) -> None:
    rubric = client.post(
        "/api/rubric-profiles",
        json={
            "name": "Simple rubric",
            "criteria": [
                {
                    "id": "content",
                    "label": "Content",
                    "description": "Covers the topic.",
                    "max_score": 5,
                    "weight": 1,
                }
            ],
        },
    )
    rubric.raise_for_status()
    rubric_id = rubric.json()["id"]

    assessment = client.post(
        "/api/assessments",
        json={"course_code": "SVE1", "title": "Short answer", "task_type": "short_answer", "rubric_profile_id": rubric_id},
    )
    assessment_id = assessment.json()["id"]
    submission = client.post(
        "/api/submissions",
        json={"assessment_id": assessment_id, "student_identifier": "student-2", "answer_text": "Kort svar."},
    )
    submission_id = submission.json()["id"]
    grade_run = client.post(
        "/api/grade-runs",
        json={"assessment_id": assessment_id, "submission_id": submission_id, "rubric_profile_id": rubric_id},
    )
    grade_run_id = grade_run.json()["id"]

    response = client.post(
        f"/api/reviews/{grade_run_id}/override",
        json={"reviewer_id": "teacher-1"},
    )
    assert response.status_code == 400


def test_browser_task_reports_missing_api_key(client) -> None:
    response = client.post(
        "/api/browser-tasks/run",
        json={
            "target_url": "https://example.com",
            "instruction": "Open the page and summarize the main headline.",
        },
    )
    response.raise_for_status()
    assert response.json()["status"] == "failed"
    assert "OLLAMA_HOST" in response.json()["summary"]


def test_text_scoring_endpoint_returns_points(client) -> None:
    response = client.post(
        "/api/text-scoring/score",
        json={
            "task_title": "Short Swedish answer",
            "submission_text": "Klimat och framtid är viktiga ämnen.",
            "criteria": [
                {
                    "id": "topic",
                    "label": "Topic coverage",
                    "description": "Mentions the required topic.",
                    "max_score": 3,
                    "weight": 1,
                    "keywords": ["klimat", "framtid"],
                },
                {
                    "id": "clarity",
                    "label": "Clarity",
                    "description": "The answer is understandable Swedish.",
                    "max_score": 2,
                    "weight": 1,
                },
            ],
        },
    )
    response.raise_for_status()
    payload = response.json()
    assert payload["points_to_enter"] >= 0
    assert payload["max_points"] == 5
    assert payload["routing_tier"] == "simple"
    assert payload["model_name"] == "local-ruleset"
    assert payload["steps"]
    assert payload["criterion_scores"]


def test_queue_grading_task_reports_missing_provider_key(client) -> None:
    response = client.post(
        "/api/browser-tasks/grade-queue",
        json={
            "target_url": "https://example.com/queue",
            "criteria": [
                {
                    "id": "topic",
                    "label": "Topic coverage",
                    "description": "Mentions the main topic.",
                    "max_score": 5,
                    "weight": 1,
                }
            ],
        },
    )
    response.raise_for_status()
    assert response.json()["status"] == "failed"
    assert "OLLAMA_HOST" in response.json()["summary"]
    assert response.json()["steps"][0]["status"] == "failed"


def test_runtime_overview_exposes_router_configuration(client) -> None:
    response = client.get("/api/runtime/overview")
    response.raise_for_status()
    payload = response.json()
    assert payload["model_router_provider"] == "heuristic"
    assert payload["model_router_simple_model"] == "qwen3.5:4b"
    assert payload["model_router_complex_model"] == "qwen3.5:9b"
    assert payload["sanomapro_exercise_grading_provider"] == "vertex_ai"
    assert payload["sanomapro_exercise_grading_model"] == "gemini-3.1-pro-preview"
    assert payload["ollama_simple_reasoning_mode"] is False
    assert payload["ollama_complex_reasoning_mode"] == "high"
    assert payload["browser_agent_provider"] == "ollama"
    assert payload["browser_agent_model"] == "qwen3.5:9b"
    assert payload["browser_agent_use_thinking"] is False
    assert payload["ollama_host"] == "http://127.0.0.1:11439"
    assert payload["browser_use_system_chrome"] is False
    assert payload["browser_chrome_profile_directory"] == "Default"
    assert payload["browser_persistent_profile_dir"] == "artifacts/browser/browser-use-user-data-dir-gradeagent-test"
    assert "counts" in payload


def test_gui_prompt_routes_expose_prompt_library(client, monkeypatch) -> None:
    saved_payload: dict[str, str | None] = {}

    class FakeRuntime:
        def state(self) -> dict[str, object]:
            return {"browser_ready": True, "session_id": "session-123", "prompt_count": 1}

        def prompt_templates(self) -> list[PromptTemplate]:
            return [
                PromptTemplate(
                    prompt_id="default-2p",
                    title="2p Lauseet [SWE -> FIN]",
                    body="Prompt body",
                    built_in=True,
                )
            ]

        def new_prompt_template(self) -> PromptTemplate:
            return PromptTemplate(
                prompt_id="custom-new",
                title="Uusi kriteeri",
                body="",
                built_in=False,
            )

        def save_prompt(self, *, title: str, body: str, prompt_id: str | None = None) -> PromptTemplate:
            saved_payload.update({"prompt_id": prompt_id, "title": title, "body": body})
            return PromptTemplate(
                prompt_id=prompt_id or "custom-saved",
                title=title,
                body=body,
                built_in=False,
            )

        def statistics(self):
            return []

    monkeypatch.setattr("app.api.routes.get_gui_runtime", lambda: FakeRuntime())

    state_response = client.get("/api/gui/state")
    state_response.raise_for_status()
    assert state_response.json()["browser_ready"] is True
    assert state_response.json()["session_id"] == "session-123"

    prompt_response = client.get("/api/gui/prompts")
    prompt_response.raise_for_status()
    assert prompt_response.json()[0]["title"] == "2p Lauseet [SWE -> FIN]"
    assert prompt_response.json()[0]["built_in"] is True

    new_prompt_response = client.post("/api/gui/prompts/new")
    new_prompt_response.raise_for_status()
    assert new_prompt_response.json()["prompt_id"] == "custom-new"

    save_response = client.post(
        "/api/gui/prompts/save",
        json={
            "prompt_id": "custom-1",
            "title": "Oma kriteeri",
            "body": "Arvioi vastaus konservatiivisesti.",
        },
    )
    save_response.raise_for_status()
    assert save_response.json()["title"] == "Oma kriteeri"
    assert saved_payload == {
        "prompt_id": "custom-1",
        "title": "Oma kriteeri",
        "body": "Arvioi vastaus konservatiivisesti.",
    }


def test_gui_overview_grading_shutdown_and_statistics_routes(client, monkeypatch) -> None:
    grade_calls: list[tuple[str, str, str | None, str | None, int]] = []
    shutdown_calls = {"count": 0}
    stop_grading_calls = {"count": 0}

    overview_before = SanomaOverviewState(
        assignment_title="RUB14.7 koe",
        group_name="Katjas grupp RUB14.7",
        students_answered_count=31,
        students_total_count=31,
        exercise_columns=[
            SanomaOverviewExerciseColumn(
                column_key="text-4-4",
                column_index=3,
                label="Text 4 · Tehtävä 4",
                category_name="Text 4",
                exercise_number="4",
                total_cell_count=31,
                reviewed_cell_count=10,
                pending_cell_count=21,
                first_pending_selector_index=7,
            ),
            SanomaOverviewExerciseColumn(
                column_key="kuuntelut-8",
                column_index=7,
                label="Kuuntelut · Tehtävä 8",
                category_name="Kuuntelut",
                exercise_number="8",
                total_cell_count=31,
                reviewed_cell_count=31,
                pending_cell_count=0,
                first_pending_selector_index=None,
            ),
        ],
    )
    overview_after = SanomaOverviewState(
        assignment_title="RUB14.7 koe",
        group_name="Katjas grupp RUB14.7",
        students_answered_count=31,
        students_total_count=31,
        exercise_columns=[],
    )

    class FakeRuntime:
        def ensure_browser_started(self) -> str:
            return "session-456"

        def stop_browser(self) -> dict[str, object]:
            return {"browser_ready": False, "session_id": None, "prompt_count": 1}

        def refresh_overview(self) -> SanomaOverviewState:
            return overview_before

        def grade_exercise(
            self,
            *,
            column_key: str,
            instructions: str,
            prompt_id: str | None = None,
            prompt_title: str | None = None,
            max_steps: int = 260,
        ) -> tuple[ExamSessionGradingTaskResult, SanomaOverviewState]:
            grade_calls.append((column_key, instructions, prompt_id, prompt_title, max_steps))
            return (
                ExamSessionGradingTaskResult(
                    job_id="job-1",
                    status="completed",
                    summary="Tehtävä arvioitiin onnistuneesti.",
                    current_exercise_label="Tehtävä 4",
                    current_student_name="Veeti Räikkönen",
                    report_path="artifacts/browser/job-1-grading-report.txt",
                ),
                overview_after,
            )

        def request_stop_grading(self) -> None:
            stop_grading_calls["count"] += 1

        def statistics(self):
            return [
                {
                    "run_id": "run-1",
                    "job_id": "job-1",
                    "recorded_at": datetime(2026, 4, 5, 10, 15, tzinfo=timezone.utc),
                    "status": "completed",
                    "summary": "Tehtävä arvioitiin onnistuneesti.",
                    "assignment_title": "RUB14.7 koe",
                    "group_name": "Katjas grupp RUB14.7",
                    "category_name": "Text 4",
                    "exercise_label": "Tehtävä 4",
                    "exercise_number": "4",
                    "students_answered_count": 31,
                    "students_total_count": 31,
                    "processed_answers": 21,
                    "filled_point_fields": 21,
                    "report_path": "artifacts/browser/job-1-grading-report.txt",
                    "prompt_id": "default-2p",
                    "prompt_title": "2p Lauseet [SWE -> FIN]",
                    "entries": [
                        {
                            "student_name": "Veeti Räikkönen",
                            "student_progress": "Oppilas 27/31",
                            "assignment_title": "RUB14.7 koe",
                            "group_name": "Katjas grupp RUB14.7",
                            "category_name": "Text 4",
                            "exercise_label": "Tehtävä 4",
                            "exercise_number": "4",
                            "objective_text": "Käännä lauseet suomeksi.",
                            "target_text": "Tycker du att det är möjligt att påverka?",
                            "question_text": "Käännä lauseet suomeksi.",
                            "answer_text": "Onko nuorten mahdollista vaikuttaa",
                            "model_answer_text": "Onko sinusta mahdollista vaikuttaa",
                            "points_text": "1 / 2",
                            "score_awarded": 1.0,
                            "score_possible": 2.0,
                            "basis_lines": ["Summary: Meaning partly matches."],
                            "submitted_prompt_text": "Teacher grading instructions:\\nPrompt body",
                            "model_provider": "vertex_ai",
                            "model_name": "gemini-3.1-pro-preview",
                            "model_response_text": "Grade: 1 / 2 points",
                            "used_heuristic_fallback": False,
                            "exercise_url": "https://arvi.sanomapro.fi/demo",
                            "status": "scored",
                        }
                    ],
                }
            ]

    monkeypatch.setattr("app.api.routes.get_gui_runtime", lambda: FakeRuntime())
    monkeypatch.setattr("app.api.routes.reset_gui_runtime", lambda: shutdown_calls.__setitem__("count", 1))

    browser_response = client.post("/api/gui/browser/start")
    browser_response.raise_for_status()
    assert browser_response.json()["session_id"] == "session-456"

    stop_response = client.post("/api/gui/browser/stop")
    stop_response.raise_for_status()
    assert stop_response.json()["browser_ready"] is False
    assert stop_response.json()["session_id"] is None

    overview_response = client.get("/api/gui/overview")
    overview_response.raise_for_status()
    payload = overview_response.json()
    assert payload["group_name"] == "Katjas grupp RUB14.7"
    assert payload["students_total_count"] == 31
    assert len(payload["exercises"]) == 1
    assert payload["exercises"][0]["category_name"] == "Text 4"
    assert payload["exercises"][0]["exercise_number"] == "4"

    grade_response = client.post(
        "/api/gui/exercises/grade",
        json={
            "column_key": "text-4-4",
            "instructions": "Käytä valittua kirjastokriteeriä.",
            "prompt_id": "default-2p",
            "prompt_title": "2p Lauseet [SWE -> FIN]",
            "max_steps": 300,
        },
    )
    grade_response.raise_for_status()
    assert grade_response.json()["result"]["summary"] == "Tehtävä arvioitiin onnistuneesti."
    assert grade_response.json()["exercises"] == []
    assert grade_calls == [("text-4-4", "Käytä valittua kirjastokriteeriä.", "default-2p", "2p Lauseet [SWE -> FIN]", 300)]

    statistics_response = client.get("/api/gui/statistics")
    statistics_response.raise_for_status()
    statistics_payload = statistics_response.json()
    assert statistics_payload["runs"][0]["category_name"] == "Text 4"
    assert statistics_payload["runs"][0]["prompt_title"] == "2p Lauseet [SWE -> FIN]"
    assert statistics_payload["runs"][0]["entries"][0]["score_possible"] == 2.0
    assert statistics_payload["runs"][0]["entries"][0]["model_name"] == "gemini-3.1-pro-preview"
    assert statistics_payload["runs"][0]["entries"][0]["submitted_prompt_text"].startswith("Teacher grading instructions:")

    stop_grading_response = client.post("/api/gui/exercises/stop")
    assert stop_grading_response.status_code == 204
    assert stop_grading_calls["count"] == 1

    shutdown_response = client.post("/api/gui/shutdown")
    assert shutdown_response.status_code == 204
    assert shutdown_calls["count"] == 1
