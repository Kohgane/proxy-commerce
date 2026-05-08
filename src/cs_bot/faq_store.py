from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_WORKSHEET_NAME = "cs_faq"
_HEADERS = [
    "faq_id",
    "category",
    "language",
    "question",
    "keywords",
    "answer_template",
    "priority",
    "enabled",
    "created_at",
    "updated_at",
]


@dataclass
class FAQEntry:
    faq_id: str
    category: str
    language: str
    question: str
    keywords: list[str]
    answer_template: str
    priority: int = 0
    enabled: bool = True
    embedding: list[float] | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "FAQEntry":
        keywords = payload.get("keywords") or []
        if isinstance(keywords, str):
            try:
                decoded = json.loads(keywords)
                if isinstance(decoded, list):
                    keywords = decoded
                else:
                    keywords = [k.strip() for k in keywords.split(",") if k.strip()]
            except Exception:
                keywords = [k.strip() for k in keywords.split(",") if k.strip()]
        embedding = payload.get("embedding")
        if isinstance(embedding, str):
            try:
                decoded = json.loads(embedding)
                embedding = decoded if isinstance(decoded, list) else None
            except Exception:
                embedding = None
        return cls(
            faq_id=str(payload.get("faq_id") or ""),
            category=str(payload.get("category") or "general"),
            language=str(payload.get("language") or "ko"),
            question=str(payload.get("question") or ""),
            keywords=[str(x) for x in keywords],
            answer_template=str(payload.get("answer_template") or ""),
            priority=int(payload.get("priority") or 0),
            enabled=_as_bool(payload.get("enabled", True)),
            embedding=[float(x) for x in embedding] if isinstance(embedding, list) else None,
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )


class FAQStore:
    """Sheets 우선, JSONL 폴백."""

    _LOCK = threading.RLock()

    def __init__(self, fallback_path: Optional[str] = None):
        path = fallback_path or os.getenv("CS_FAQ_FALLBACK_PATH", "data/cs_faq.jsonl")
        self._fallback_path = Path(path)
        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)

    def _open_ws(self):
        try:
            from src.utils.sheets import get_worksheet

            return get_worksheet(_WORKSHEET_NAME, headers=_HEADERS)
        except Exception as exc:
            logger.debug("cs_faq Sheets 연결 실패: %s", exc)
            return None

    def _read_fallback(self) -> list[FAQEntry]:
        if not self._fallback_path.exists():
            return []
        items: list[FAQEntry] = []
        try:
            with self._fallback_path.open("r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        items.append(FAQEntry.from_dict(json.loads(raw)))
                    except Exception as exc:
                        logger.warning("cs_faq JSONL 파싱 실패: %s", exc)
        except Exception as exc:
            logger.warning("cs_faq JSONL 읽기 실패: %s", exc)
        return items

    def _write_fallback(self, entries: list[FAQEntry]) -> None:
        with self._LOCK:
            tmp = self._fallback_path.with_suffix(".tmp")
            try:
                with tmp.open("w", encoding="utf-8") as f:
                    for entry in entries:
                        f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
                tmp.replace(self._fallback_path)
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except Exception:
                        pass

    @staticmethod
    def _row_to_entry(row: dict) -> FAQEntry:
        return FAQEntry.from_dict(row)

    @staticmethod
    def _entry_to_row(entry: FAQEntry) -> list[str]:
        data = entry.to_dict()
        return [
            data["faq_id"],
            data["category"],
            data["language"],
            data["question"],
            json.dumps(data["keywords"], ensure_ascii=False),
            data["answer_template"],
            str(data["priority"]),
            str(bool(data["enabled"])),
            data["created_at"],
            data["updated_at"],
        ]

    def list_all(
        self,
        language: str | None = None,
        category: str | None = None,
        enabled_only: bool = True,
    ) -> list[FAQEntry]:
        ws = self._open_ws()
        entries: list[FAQEntry] = []
        if ws is not None:
            try:
                entries = [self._row_to_entry(r) for r in ws.get_all_records()]
            except Exception as exc:
                logger.warning("cs_faq list Sheets 실패, 폴백 사용: %s", exc)
                entries = self._read_fallback()
        else:
            entries = self._read_fallback()

        if language:
            entries = [x for x in entries if x.language == language]
        if category:
            entries = [x for x in entries if x.category == category]
        if enabled_only:
            entries = [x for x in entries if x.enabled]
        return sorted(entries, key=lambda x: (-int(x.priority), x.updated_at, x.faq_id))

    def get(self, faq_id: str) -> FAQEntry | None:
        for entry in self.list_all(enabled_only=False):
            if entry.faq_id == faq_id:
                return entry
        return None

    def create(self, entry: FAQEntry) -> FAQEntry:
        now = _now_iso()
        if not entry.faq_id:
            entry.faq_id = f"faq_{uuid.uuid4().hex[:10]}"
        if not entry.created_at:
            entry.created_at = now
        entry.updated_at = now

        ws = self._open_ws()
        if ws is not None:
            try:
                ws.append_row(self._entry_to_row(entry))
                return entry
            except Exception as exc:
                logger.warning("cs_faq create Sheets 실패, 폴백 사용: %s", exc)

        with self._LOCK:
            rows = self._read_fallback()
            rows = [r for r in rows if r.faq_id != entry.faq_id]
            rows.append(entry)
            self._write_fallback(rows)
        return entry

    def update(self, entry: FAQEntry) -> bool:
        existing = self.get(entry.faq_id)
        if not existing:
            return False
        entry.created_at = entry.created_at or existing.created_at
        entry.updated_at = _now_iso()

        ws = self._open_ws()
        if ws is not None:
            try:
                rows = ws.get_all_records()
                for i, row in enumerate(rows):
                    if row.get("faq_id") == entry.faq_id:
                        row_num = i + 2
                        for col, value in enumerate(self._entry_to_row(entry), start=1):
                            ws.update_cell(row_num, col, value)
                        return True
            except Exception as exc:
                logger.warning("cs_faq update Sheets 실패, 폴백 사용: %s", exc)

        with self._LOCK:
            rows = self._read_fallback()
            for i, item in enumerate(rows):
                if item.faq_id == entry.faq_id:
                    rows[i] = entry
                    self._write_fallback(rows)
                    return True
        return False

    def delete(self, faq_id: str) -> bool:
        ws = self._open_ws()
        if ws is not None:
            try:
                rows = ws.get_all_records()
                for i, row in enumerate(rows):
                    if row.get("faq_id") == faq_id:
                        ws.delete_rows(i + 2)
                        return True
            except Exception as exc:
                logger.warning("cs_faq delete Sheets 실패, 폴백 사용: %s", exc)

        with self._LOCK:
            rows = self._read_fallback()
            filtered = [r for r in rows if r.faq_id != faq_id]
            if len(filtered) == len(rows):
                return False
            self._write_fallback(filtered)
            return True

    def search_by_keywords(self, query: str, language: str = "ko") -> list[FAQEntry]:
        q = (query or "").strip().lower()
        if not q:
            return []
        tokens = [t for t in q.replace("\n", " ").split(" ") if t]
        candidates = self.list_all(language=language, enabled_only=True)
        if not candidates and language != "ko":
            candidates = self.list_all(language="ko", enabled_only=True)

        scored: list[tuple[int, FAQEntry]] = []
        for entry in candidates:
            score = 0
            text = f"{entry.question} {' '.join(entry.keywords)}".lower()
            for token in tokens:
                if token and token in text:
                    score += 2
            for keyword in entry.keywords:
                kw = keyword.lower().strip()
                if kw and kw in q:
                    score += 3
            if score > 0:
                score += int(entry.priority)
                scored.append((score, entry))
        scored.sort(key=lambda x: (-x[0], -x[1].priority, x[1].faq_id))
        return [entry for _, entry in scored]


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
