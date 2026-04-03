"""src/pipeline/stages/upload_stage.py — 업로드 스테이지."""
from __future__ import annotations

from ..stage import Stage
from ..stage_result import StageResult


class UploadStage(Stage):
    """상품 업로드 스테이지."""

    name = "upload"

    def process(self, context: dict) -> StageResult:
        items = context.get("priced") or context.get("translated") or context.get("collected", [])
        uploaded_ids = [f"uploaded-{i}" for i in range(len(items))]
        context["uploaded_ids"] = uploaded_ids
        return StageResult(
            status="success",
            output={"uploaded_count": len(uploaded_ids), "ids": uploaded_ids},
        )

    def rollback(self, context: dict) -> None:
        context.pop("uploaded_ids", None)
