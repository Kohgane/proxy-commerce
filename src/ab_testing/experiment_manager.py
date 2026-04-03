"""src/ab_testing/experiment_manager.py — 실험 CRUD."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class ExperimentManager:
    """A/B 실험 생성/시작/중지/결과조회."""

    def __init__(self) -> None:
        self._experiments: Dict[str, dict] = {}

    def create(self, name: str, variants: List[str] = None, **kwargs) -> dict:
        """실험 생성."""
        if not name:
            raise ValueError("name은 필수입니다.")
        exp_id = kwargs.get("experiment_id") or str(uuid.uuid4())
        if exp_id in self._experiments:
            raise ValueError(f"이미 존재하는 실험 ID: {exp_id}")
        experiment = {
            "experiment_id": exp_id,
            "name": name,
            "variants": variants or ["control", "treatment"],
            "status": "created",
            "created_at": _now_iso(),
            "started_at": None,
            "stopped_at": None,
            **{k: v for k, v in kwargs.items() if k != "experiment_id"},
        }
        self._experiments[exp_id] = experiment
        return dict(experiment)

    def get(self, experiment_id: str) -> Optional[dict]:
        e = self._experiments.get(experiment_id)
        return dict(e) if e else None

    def list(self, status: str = None) -> List[dict]:
        experiments = list(self._experiments.values())
        if status:
            experiments = [e for e in experiments if e.get("status") == status]
        return [dict(e) for e in experiments]

    def start(self, experiment_id: str) -> dict:
        """실험 시작."""
        if experiment_id not in self._experiments:
            raise KeyError(f"실험 없음: {experiment_id}")
        self._experiments[experiment_id]["status"] = "running"
        self._experiments[experiment_id]["started_at"] = _now_iso()
        return dict(self._experiments[experiment_id])

    def stop(self, experiment_id: str) -> dict:
        """실험 중지."""
        if experiment_id not in self._experiments:
            raise KeyError(f"실험 없음: {experiment_id}")
        self._experiments[experiment_id]["status"] = "stopped"
        self._experiments[experiment_id]["stopped_at"] = _now_iso()
        return dict(self._experiments[experiment_id])

    def delete(self, experiment_id: str) -> bool:
        if experiment_id not in self._experiments:
            return False
        del self._experiments[experiment_id]
        return True
