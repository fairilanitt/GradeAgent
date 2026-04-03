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
    assert payload["model_router_simple_model"] == "qwen3:4b"
    assert payload["model_router_complex_model"] == "qwen3:8b"
    assert payload["browser_agent_provider"] == "ollama"
    assert payload["browser_agent_model"] == "qwen3-vl:4b"
    assert payload["ollama_host"] == "http://127.0.0.1:11439"
    assert payload["browser_use_system_chrome"] is False
    assert payload["browser_chrome_profile_directory"] == "Default"
    assert payload["browser_persistent_profile_dir"] == "artifacts/browser/browser-use-user-data-dir-gradeagent-test"
    assert "counts" in payload
