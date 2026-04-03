"""src/pipeline/pipeline_monitor.py — 파이프라인 모니터링."""
from __future__ import annotations

from typing import Dict, List

from .stage_result import StageResult


class PipelineMonitor:
    """파이프라인 실행 통계 수집."""

    def __init__(self) -> None:
        self._stats: Dict[str, list] = {}

    def record_execution(self, pipeline_name: str, results: Dict[str, StageResult]) -> None:
        if pipeline_name not in self._stats:
            self._stats[pipeline_name] = []
        success = all(r.status != "failure" for r in results.values())
        total_ms = sum(r.duration_ms for r in results.values())
        self._stats[pipeline_name].append({
            "success": success,
            "total_ms": total_ms,
            "stage_count": len(results),
        })

    def get_stats(self, pipeline_name: str) -> dict:
        runs = self._stats.get(pipeline_name, [])
        if not runs:
            return {"pipeline_name": pipeline_name, "runs": 0}
        successes = sum(1 for r in runs if r["success"])
        avg_ms = sum(r["total_ms"] for r in runs) / len(runs)
        return {
            "pipeline_name": pipeline_name,
            "runs": len(runs),
            "successes": successes,
            "failures": len(runs) - successes,
            "success_rate": round(successes / len(runs) * 100, 2),
            "avg_duration_ms": round(avg_ms, 2),
        }

    def get_all_stats(self) -> List[dict]:
        return [self.get_stats(name) for name in self._stats]
