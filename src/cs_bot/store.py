from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from .models import FaqItem


class CsFaqStore:
    """Sheets 연동 전까지 JSONL 폴백 기반 FAQ 저장소."""

    def __init__(self, path: str | None = None) -> None:
        self._path = Path(path or os.getenv("CS_FAQ_FALLBACK_PATH", "data/cs_faq.jsonl"))
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.worksheet_name = "cs_faq"

    def list_items(self) -> list[FaqItem]:
        items: list[FaqItem] = []
        if not self._path.exists():
            return items
        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    items.append(FaqItem.from_dict(json.loads(raw)))
                except Exception:
                    continue
        return items

    def save_items(self, items: list[FaqItem]) -> None:
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as handle:
                for item in items:
                    handle.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
            tmp.replace(self._path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass

    def add_item(self, keyword: str, answer: str, locale: str = "ko") -> FaqItem:
        items = self.list_items()
        item = FaqItem(faq_id=f"faq_{uuid.uuid4().hex[:8]}", keyword=keyword, answer=answer, locale=locale)
        items.append(item)
        self.save_items(items)
        return item
