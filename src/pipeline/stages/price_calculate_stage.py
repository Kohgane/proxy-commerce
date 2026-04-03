"""src/pipeline/stages/price_calculate_stage.py — 가격 계산 스테이지."""
from __future__ import annotations

from ..stage import Stage
from ..stage_result import StageResult


class PriceCalculateStage(Stage):
    """가격 계산 스테이지."""

    name = "price_calculate"

    def __init__(self, markup_rate: float = 1.3) -> None:
        self.markup_rate = markup_rate

    def process(self, context: dict) -> StageResult:
        items = context.get("translated") or context.get("collected", [])
        priced = []
        for item in items:
            p = dict(item)
            p["final_price"] = round(item.get("price", 0) * self.markup_rate)
            priced.append(p)
        context["priced"] = priced
        return StageResult(status="success", output={"priced_count": len(priced)})

    def rollback(self, context: dict) -> None:
        context.pop("priced", None)
