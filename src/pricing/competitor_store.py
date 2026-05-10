from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

from src.utils.persistent_store import PersistentStore

_WORKSHEET = "competitor_targets"
_HEADERS = [
    "competitor_id",
    "product_id",
    "name",
    "url",
    "enabled",
    "site",
    "created_at",
]


class CompetitorStore(PersistentStore[dict]):
    _LOCK = threading.RLock()

    def __init__(self, fallback_path: Optional[Path] = None):
        base = Path(os.getenv("COMPETITOR_SCRAPE_FALLBACK_PATH", "data/competitor_prices.jsonl"))
        target_path = fallback_path or base.with_name("competitor_targets.jsonl")
        super().__init__(sheet_name=_WORKSHEET, fallback_path=target_path, lock=self._LOCK)

    def _open_ws(self):
        try:
            from src.utils.sheets import get_worksheet

            return get_worksheet(_WORKSHEET, headers=_HEADERS)
        except Exception:
            return None

    def _sheets_available(self) -> bool:
        return self._open_ws() is not None

    def _sheets_read(self) -> list[dict]:
        ws = self._open_ws()
        return ws.get_all_records() if ws is not None else []

    def _sheets_write(self, items: list[dict]) -> bool:
        ws = self._open_ws()
        if ws is None:
            return False
        ws.clear()
        ws.append_row(_HEADERS)
        rows = []
        for item in items:
            rows.append([
                item.get("competitor_id", ""),
                item.get("product_id", ""),
                item.get("name", ""),
                item.get("url", ""),
                str(item.get("enabled", True)),
                item.get("site", ""),
                item.get("created_at", ""),
            ])
        if rows:
            if hasattr(ws, "append_rows"):
                ws.append_rows(rows)
            else:
                for row in rows:
                    ws.append_row(row)
        return True

    def health_check(self) -> dict:
        try:
            rows = self.read_all()
            return {"ok": True, "count": len(rows), "sheets": self._sheets_available(), "jsonl_path": str(self.fallback_path)}
        except Exception as exc:
            return {"ok": False, "error": str(exc), "sheets": self._sheets_available(), "jsonl_path": str(self.fallback_path)}
