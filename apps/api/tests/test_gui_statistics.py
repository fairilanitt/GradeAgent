from datetime import datetime, timezone

from app.schemas.api import GuiStatisticsEntry, GuiStatisticsRun
from app.services.gui_statistics import GuiStatisticsStore


def test_gui_statistics_store_appends_and_loads_runs(tmp_path) -> None:
    store = GuiStatisticsStore(tmp_path / "grading-run-history.json")

    first = GuiStatisticsRun(
        run_id="run-1",
        job_id="job-1",
        recorded_at=datetime(2026, 4, 5, 9, 0, tzinfo=timezone.utc),
        status="completed",
        summary="First run",
        category_name="Text 4",
        exercise_label="Tehtävä 4",
        entries=[
            GuiStatisticsEntry(
                student_name="Aada",
                points_text="1 / 2",
                score_awarded=1.0,
                score_possible=2.0,
                submitted_prompt_text="Teacher grading instructions:\nPrompt body",
                model_name="gemini-3.1-pro-preview",
            )
        ],
    )
    second = GuiStatisticsRun(
        run_id="run-2",
        job_id="job-2",
        recorded_at=datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc),
        status="needs_review",
        interrupted=True,
        summary="Second run",
        category_name="Grammatik",
        exercise_label="Tehtävä 22",
        entries=[],
    )

    store.append_run(first)
    store.append_run(second)
    loaded = store.load_runs()

    assert [run.run_id for run in loaded] == ["run-2", "run-1"]
    assert loaded[0].interrupted is True
    assert loaded[0].category_name == "Grammatik"
    assert loaded[1].entries[0].score_possible == 2.0
    assert loaded[1].entries[0].model_name == "gemini-3.1-pro-preview"


def test_gui_statistics_store_reads_legacy_history_and_migrates_to_primary(tmp_path) -> None:
    primary_path = tmp_path / "artifacts/gui/grading-run-history.json"
    legacy_path = tmp_path / "apps/api/artifacts/gui/grading-run-history.json"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text(
        """
        [
          {
            "run_id": "legacy-run",
            "job_id": "job-legacy",
            "recorded_at": "2026-04-06T10:00:00Z",
            "status": "completed",
            "summary": "Legacy run",
            "assignment_title": "RUB14.7 koe",
            "category_name": "Text 4",
            "exercise_label": "Tehtävä 4",
            "entries": []
          }
        ]
        """.strip(),
        encoding="utf-8",
    )

    store = GuiStatisticsStore(primary_path, legacy_storage_paths=[legacy_path])

    loaded = store.load_runs()

    assert [run.run_id for run in loaded] == ["legacy-run"]
    assert primary_path.exists()
