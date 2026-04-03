"""src/pipeline/pipeline_executor.py — 파이프라인 실행 관리."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from .pipeline import Pipeline
from .stage_result import StageResult


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class PipelineExecutor:
    """파이프라인 실행 및 이력 관리."""

    def __init__(self) -> None:
        self._history: List[dict] = []

    def execute(self, pipeline: Pipeline, context: dict) -> Dict[str, StageResult]:
        results = pipeline.run(context)
        self._record(pipeline.name, results, async_mode=False)
        return results

    def execute_async(self, pipeline: Pipeline, context: dict) -> Dict[str, StageResult]:
        """동기 실행 (async 표시만)."""
        results = pipeline.run(context)
        self._record(pipeline.name, results, async_mode=True)
        return results

    def _record(self, name: str, results: Dict[str, StageResult], async_mode: bool) -> None:
        self._history.append({
            "pipeline_name": name,
            "executed_at": _now_iso(),
            "async": async_mode,
            "results": {k: v.to_dict() for k, v in results.items()},
            "success": all(r.status != "failure" for r in results.values()),
        })

    def get_execution_history(self) -> List[dict]:
        return list(self._history)
