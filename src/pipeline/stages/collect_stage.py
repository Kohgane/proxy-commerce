"""src/pipeline/stages/collect_stage.py — 데이터 수집 스테이지."""
from __future__ import annotations

from ..stage import Stage
from ..stage_result import StageResult


class CollectStage(Stage):
    """상품 데이터 수집 스테이지."""

    name = "collect"

    def process(self, context: dict) -> StageResult:
        items = context.get("items", [])
        # 모의 수집: 컨텍스트에 있는 items를 collected로 이동
        context["collected"] = list(items) or [{"id": "mock-1", "name": "상품1", "price": 10000}]
        return StageResult(status="success", output={"collected_count": len(context["collected"])})

    def rollback(self, context: dict) -> None:
        context.pop("collected", None)
