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
            )
        ],
    )
    second = GuiStatisticsRun(
        run_id="run-2",
        job_id="job-2",
        recorded_at=datetime(2026, 4, 5, 10, 0, tzinfo=timezone.utc),
        status="needs_review",
        summary="Second run",
        category_name="Grammatik",
        exercise_label="Tehtävä 22",
        entries=[],
    )

    store.append_run(first)
    store.append_run(second)
    loaded = store.load_runs()

    assert [run.run_id for run in loaded] == ["run-2", "run-1"]
    assert loaded[0].category_name == "Grammatik"
    assert loaded[1].entries[0].score_possible == 2.0
