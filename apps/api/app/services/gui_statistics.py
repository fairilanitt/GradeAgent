from __future__ import annotations

import json
import threading
from pathlib import Path

from app.schemas.api import GuiStatisticsRun


class GuiStatisticsStore:
    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = storage_path or Path("artifacts/gui/grading-run-history.json")
        self._lock = threading.RLock()

    def _ensure_parent_dir(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_runs_unlocked(self) -> list[GuiStatisticsRun]:
        if not self.storage_path.exists():
            return []
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        runs: list[GuiStatisticsRun] = []
        for item in payload if isinstance(payload, list) else []:
            try:
                runs.append(GuiStatisticsRun.model_validate(item))
            except Exception:
                continue
        return sorted(runs, key=lambda run: run.recorded_at, reverse=True)

    def load_runs(self) -> list[GuiStatisticsRun]:
        with self._lock:
            return self._load_runs_unlocked()

    def append_run(self, run: GuiStatisticsRun) -> GuiStatisticsRun:
        with self._lock:
            self._ensure_parent_dir()
            runs = self._load_runs_unlocked()
            runs.insert(0, run.model_copy())
            self.storage_path.write_text(
                json.dumps([item.model_dump(mode="json") for item in runs], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return run
