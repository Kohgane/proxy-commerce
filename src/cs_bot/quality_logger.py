from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.cs_bot.faq_store import FAQEntry, FAQStore
from src.cs_bot.inbox_store import CSMessage

logger = logging.getLogger(__name__)

_WORKSHEET_NAME = "cs_reply_quality"
_HEADERS = [
    "logged_at",
    "message_id",
    "faq_id",
    "category",
    "language",
    "suggested",
    "final",
    "accepted",
    "score",
]
_LOCK = threading.RLock()


@dataclass
class QualityRecord:
    logged_at: str
    message_id: str
    faq_id: str
    category: str
    language: str
    suggested: str
    final: str
    accepted: bool
    score: float

    def to_dict(self) -> dict:
        return {
            "logged_at": self.logged_at,
            "message_id": self.message_id,
            "faq_id": self.faq_id,
            "category": self.category,
            "language": self.language,
            "suggested": self.suggested,
            "final": self.final,
            "accepted": self.accepted,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "QualityRecord":
        return cls(
            logged_at=str(payload.get("logged_at") or ""),
            message_id=str(payload.get("message_id") or ""),
            faq_id=str(payload.get("faq_id") or ""),
            category=str(payload.get("category") or ""),
            language=str(payload.get("language") or "ko"),
            suggested=str(payload.get("suggested") or ""),
            final=str(payload.get("final") or ""),
            accepted=str(payload.get("accepted")).strip().lower() in {"1", "true", "yes", "on"},
            score=float(payload.get("score") or 0.0),
        )


def log_reply_quality(msg: CSMessage, suggested: str, final: str, accepted: bool):
    """
    유사도(Levenshtein 또는 임베딩 코사인) 계산 → 0~1 점수.
    Sheets `cs_reply_quality` 워크시트 + JSONL 폴백 기록.
    """
    score = _normalized_similarity(suggested or "", final or "")
    row = QualityRecord(
        logged_at=datetime.now(timezone.utc).isoformat(),
        message_id=msg.message_id,
        faq_id=msg.matched_faq_id or "",
        category=msg.category or "general",
        language=msg.language or "ko",
        suggested=suggested or "",
        final=final or "",
        accepted=bool(accepted),
        score=score,
    )
    ws = _open_ws()
    if ws is not None:
        try:
            ws.append_row([
                row.logged_at,
                row.message_id,
                row.faq_id,
                row.category,
                row.language,
                row.suggested,
                row.final,
                str(row.accepted),
                str(round(row.score, 4)),
            ])
            return
        except Exception as exc:
            logger.warning("cs_reply_quality Sheets 기록 실패, 폴백 사용: %s", exc)
    _append_fallback(row)


def get_low_quality_faqs(threshold: float = 0.5, limit: int = 20) -> list[tuple[FAQEntry, float]]:
    """편집률 높은 FAQ 후보 반환 → 운영자가 검토/수정."""
    faq_store = FAQStore()
    faq_map = {x.faq_id: x for x in faq_store.list_all(enabled_only=False)}
    scores: dict[str, list[float]] = {}
    for row in _list_records():
        if not row.faq_id:
            continue
        scores.setdefault(row.faq_id, []).append(float(row.score))
    low: list[tuple[FAQEntry, float]] = []
    for faq_id, values in scores.items():
        if not values or faq_id not in faq_map:
            continue
        avg = sum(values) / len(values)
        if avg < threshold:
            low.append((faq_map[faq_id], round(avg, 4)))
    low.sort(key=lambda x: x[1])
    return low[: int(limit or 20)]


def get_low_quality_records(threshold: float = 0.5, limit: int = 20) -> list[dict]:
    rows = _list_records()
    by_faq: dict[str, dict] = {}
    for row in rows:
        if not row.faq_id:
            continue
        state = by_faq.setdefault(row.faq_id, {"scores": [], "last_final": "", "hits": 0})
        state["scores"].append(row.score)
        state["hits"] += 1
        if row.final:
            state["last_final"] = row.final
    faq_store = FAQStore()
    faq_map = {x.faq_id: x for x in faq_store.list_all(enabled_only=False)}
    out: list[dict] = []
    for faq_id, state in by_faq.items():
        faq = faq_map.get(faq_id)
        if not faq or not state["scores"]:
            continue
        avg = sum(state["scores"]) / len(state["scores"])
        if avg >= threshold:
            continue
        out.append({
            "faq": faq,
            "score": round(avg, 4),
            "hits": state["hits"],
            "last_final": state["last_final"],
        })
    out.sort(key=lambda x: x["score"])
    return out[: int(limit or 20)]


def _fallback_path() -> Path:
    path = os.getenv("CS_REPLY_QUALITY_FALLBACK_PATH", "data/cs_reply_quality.jsonl")
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _open_ws():
    try:
        from src.utils.sheets import get_worksheet

        return get_worksheet(_WORKSHEET_NAME, headers=_HEADERS)
    except Exception as exc:
        logger.debug("cs_reply_quality Sheets 연결 실패: %s", exc)
        return None


def _append_fallback(row: QualityRecord) -> None:
    with _LOCK:
        with _fallback_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(row.to_dict(), ensure_ascii=False) + "\n")


def _list_records() -> list[QualityRecord]:
    ws = _open_ws()
    if ws is not None:
        try:
            return [QualityRecord.from_dict(r) for r in ws.get_all_records()]
        except Exception as exc:
            logger.warning("cs_reply_quality Sheets 읽기 실패, 폴백 사용: %s", exc)
    path = _fallback_path()
    if not path.exists():
        return []
    out: list[QualityRecord] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            try:
                out.append(QualityRecord.from_dict(json.loads(raw)))
            except Exception:
                continue
    return out


def _normalized_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    dist = _levenshtein(a, b)
    base = max(len(a), len(b), 1)
    return round(max(0.0, 1.0 - (dist / base)), 4)


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]
