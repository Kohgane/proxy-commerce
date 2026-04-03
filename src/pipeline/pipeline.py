"""src/pipeline/pipeline.py — 파이프라인 실행기."""
from __future__ import annotations

import time
from typing import Dict, List, Tuple

from .stage import Stage
from .stage_result import StageResult


class Pipeline:
    """파이프라인 — 스테이지 목록을 순서대로 실행."""

    def __init__(self, name: str, stages: List[Stage]) -> None:
        self.name = name
        self.stages = stages

    def run(self, context: dict) -> Dict[str, StageResult]:
        results: Dict[str, StageResult] = {}
        executed: List[Tuple[Stage, StageResult]] = []

        for stage in self.stages:
            if not stage.validate(context):
                results[stage.name] = StageResult(status="skipped")
                continue
            start = time.monotonic()
            try:
                result = stage.process(context)
                result.duration_ms = (time.monotonic() - start) * 1000
            except Exception as exc:
                result = StageResult(
                    status="failure",
                    duration_ms=(time.monotonic() - start) * 1000,
                    error_message=str(exc),
                )
            results[stage.name] = result
            executed.append((stage, result))
            if result.failed:
                # Rollback completed stages in reverse
                for done_stage, _ in reversed(executed[:-1]):
                    try:
                        done_stage.rollback(context)
                    except Exception:
                        pass
                break

        return results
