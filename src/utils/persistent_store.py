from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Generic, List, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PersistentStore(Generic[T]):
    """Sheets 우선 + JSONL atomic 폴백."""

    def __init__(
        self,
        *,
        sheet_name: str,
        fallback_path: Path,
        lock: threading.RLock | threading.Lock | None = None,
    ) -> None:
        self.sheet_name = sheet_name
        self.fallback_path = fallback_path
        self._lock = lock or threading.RLock()
        self.fallback_path.parent.mkdir(parents=True, exist_ok=True)

    def _atomic_write_jsonl(self, items: list[dict]) -> None:
        tmp = self.fallback_path.with_suffix(f"{self.fallback_path.suffix}.tmp.{os.getpid()}")
        with self._lock:
            try:
                with tmp.open("w", encoding="utf-8") as f:
                    for item in items:
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.fallback_path)
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except Exception:
                        pass

    def _read_jsonl(self) -> list[dict]:
        if not self.fallback_path.exists():
            return []
        with self._lock:
            items: List[dict] = []
            with self.fallback_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        items.append(json.loads(line))
                    except Exception:
                        continue
            return items

    def _sheets_available(self) -> bool:
        try:
            from src.utils.sheets import get_worksheet

            return get_worksheet(self.sheet_name) is not None
        except Exception:
            return False

    def _sheets_read(self) -> list[dict]:
        from src.utils.sheets import get_worksheet

        ws = get_worksheet(self.sheet_name)
        return ws.get_all_records() if ws is not None else []

    def _sheets_write(self, items: list[dict]) -> bool:
        _ = items
        return False

    def read_all(self) -> list[dict]:
        if self._sheets_available():
            try:
                return self._sheets_read()
            except Exception as exc:
                logger.warning("Sheets 읽기 실패, JSONL 폴백: %s", exc)
        return self._read_jsonl()

    def write_all(self, items: list[dict]) -> dict:
        sheets_ok = False
        if self._sheets_available():
            try:
                sheets_ok = bool(self._sheets_write(items))
            except Exception as exc:
                logger.warning("Sheets 쓰기 실패: %s", exc)
        self._atomic_write_jsonl(items)
        return {"sheets": sheets_ok, "jsonl": True}
