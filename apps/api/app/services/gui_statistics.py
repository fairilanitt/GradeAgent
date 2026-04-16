from __future__ import annotations

import json
import threading
from pathlib import Path

from pydantic import ValidationError

from app.schemas.api import GuiStatisticsRun


class GuiStatisticsStore:
    def __init__(
        self,
        storage_path: Path | None = None,
        legacy_storage_paths: list[Path] | None = None,
    ) -> None:
        using_default_storage = storage_path is None
        self.storage_path = (storage_path or self._default_storage_path()).expanduser().resolve()
        self.legacy_storage_paths = [
            path.expanduser().resolve()
            for path in (
                legacy_storage_paths
                if legacy_storage_paths is not None
                else self._default_legacy_storage_paths(self.storage_path) if using_default_storage else []
            )
            if path.expanduser().resolve() != self.storage_path
        ]
        self._lock = threading.RLock()

    @staticmethod
    def _repo_root() -> Path:
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "apps").exists() and (parent / ".env.example").exists():
                return parent
        return Path.cwd().resolve()

    @classmethod
    def _default_storage_path(cls) -> Path:
        return cls._repo_root() / "artifacts/gui/grading-run-history.json"

    @classmethod
    def _default_legacy_storage_paths(cls, primary_path: Path) -> list[Path]:
        repo_root = cls._repo_root()
        candidates = [
            repo_root / "apps/api/artifacts/gui/grading-run-history.json",
        ]
        return [path for path in candidates if path.resolve() != primary_path.resolve()]

    def _ensure_parent_dir(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_runs_from_path(self, path: Path) -> list[GuiStatisticsRun]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Statistics history file is not valid JSON: {path}") from exc
        if not isinstance(payload, list):
            raise RuntimeError(f"Statistics history file must contain a list of runs: {path}")
        runs: list[GuiStatisticsRun] = []
        for index, item in enumerate(payload):
            try:
                runs.append(GuiStatisticsRun.model_validate(item))
            except ValidationError as exc:
                raise RuntimeError(
                    f"Statistics history file contains an invalid run at index {index}: {path}"
                ) from exc
        return runs

    def _write_runs_unlocked(self, runs: list[GuiStatisticsRun]) -> None:
        self._ensure_parent_dir()
        self.storage_path.write_text(
            json.dumps([item.model_dump(mode="json") for item in runs], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_runs_unlocked(self) -> list[GuiStatisticsRun]:
        merged_by_id: dict[str, GuiStatisticsRun] = {}
        for path in [self.storage_path, *self.legacy_storage_paths]:
            for run in self._load_runs_from_path(path):
                existing = merged_by_id.get(run.run_id)
                if existing is None or run.recorded_at >= existing.recorded_at:
                    merged_by_id[run.run_id] = run

        runs = sorted(merged_by_id.values(), key=lambda run: run.recorded_at, reverse=True)
        if runs and not self.storage_path.exists():
            self._write_runs_unlocked(runs)
        return runs

    def load_runs(self) -> list[GuiStatisticsRun]:
        with self._lock:
            return self._load_runs_unlocked()

    def append_run(self, run: GuiStatisticsRun) -> GuiStatisticsRun:
        with self._lock:
            runs = self._load_runs_unlocked()
            merged_by_id = {item.run_id: item for item in runs}
            merged_by_id[run.run_id] = run.model_copy()
            merged_runs = sorted(merged_by_id.values(), key=lambda item: item.recorded_at, reverse=True)
            self._write_runs_unlocked(merged_runs)
        return run
