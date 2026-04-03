"""src/pipeline/stages/translate_stage.py — 번역 스테이지."""
from __future__ import annotations

from ..stage import Stage
from ..stage_result import StageResult


class TranslateStage(Stage):
    """상품명 번역 스테이지."""

    name = "translate"

    def __init__(self, target_lang: str = "ko") -> None:
        self.target_lang = target_lang

    def validate(self, context: dict) -> bool:
        return bool(context.get("collected"))

    def process(self, context: dict) -> StageResult:
        collected = context.get("collected", [])
        translated = []
        for item in collected:
            t = dict(item)
            t["name_translated"] = f"[{self.target_lang}] {item.get('name', '')}"
            translated.append(t)
        context["translated"] = translated
        return StageResult(status="success", output={"translated_count": len(translated)})

    def rollback(self, context: dict) -> None:
        context.pop("translated", None)
