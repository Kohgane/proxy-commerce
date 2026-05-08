from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_WORKSHEET_NAME = "cs_inbox"
_HEADERS = [
    "message_id",
    "channel",
    "direction",
    "customer_id",
    "customer_name",
    "order_no",
    "body",
    "language",
    "category",
    "priority",
    "status",
    "suggested_reply",
    "final_reply",
    "matched_faq_id",
    "sla_deadline",
    "received_at",
    "responded_at",
]


@dataclass
class CSMessage:
    message_id: str
    channel: str
    direction: str
    customer_id: str
    customer_name: str
    order_no: str = ""
    body: str = ""
    language: str = "ko"
    category: str = ""
    priority: int = 0
    status: str = "open"
    suggested_reply: str = ""
    final_reply: str = ""
    matched_faq_id: str = ""
    sla_deadline: str = ""
    received_at: str = ""
    responded_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "CSMessage":
        return cls(
            message_id=str(payload.get("message_id") or ""),
            channel=str(payload.get("channel") or "telegram"),
            direction=str(payload.get("direction") or "inbound"),
            customer_id=str(payload.get("customer_id") or ""),
            customer_name=str(payload.get("customer_name") or ""),
            order_no=str(payload.get("order_no") or ""),
            body=str(payload.get("body") or ""),
            language=str(payload.get("language") or "ko"),
            category=str(payload.get("category") or ""),
            priority=int(payload.get("priority") or 0),
            status=str(payload.get("status") or "open"),
            suggested_reply=str(payload.get("suggested_reply") or ""),
            final_reply=str(payload.get("final_reply") or ""),
            matched_faq_id=str(payload.get("matched_faq_id") or ""),
            sla_deadline=str(payload.get("sla_deadline") or ""),
            received_at=str(payload.get("received_at") or ""),
            responded_at=str(payload.get("responded_at") or ""),
        )


class InboxStore:
    """Sheets 우선, JSONL 폴백."""

    _LOCK = threading.RLock()

    def __init__(self, fallback_path: Optional[str] = None):
        path = fallback_path or os.getenv("CS_INBOX_FALLBACK_PATH", "data/cs_inbox.jsonl")
        self._fallback_path = Path(path)
        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)

    def _open_ws(self):
        try:
            from src.utils.sheets import get_worksheet

            return get_worksheet(_WORKSHEET_NAME, headers=_HEADERS)
        except Exception as exc:
            logger.debug("cs_inbox Sheets 연결 실패: %s", exc)
            return None

    def _read_fallback(self) -> list[CSMessage]:
        if not self._fallback_path.exists():
            return []
        items: list[CSMessage] = []
        try:
            with self._fallback_path.open("r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        items.append(CSMessage.from_dict(json.loads(raw)))
                    except Exception as exc:
                        logger.warning("cs_inbox JSONL 파싱 실패: %s", exc)
        except Exception as exc:
            logger.warning("cs_inbox JSONL 읽기 실패: %s", exc)
        return items

    def _write_fallback(self, entries: list[CSMessage]) -> None:
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
    def _row_to_message(row: dict) -> CSMessage:
        return CSMessage.from_dict(row)

    @staticmethod
    def _message_to_row(msg: CSMessage) -> list[str]:
        data = msg.to_dict()
        return [
            data["message_id"],
            data["channel"],
            data["direction"],
            data["customer_id"],
            data["customer_name"],
            data["order_no"],
            data["body"],
            data["language"],
            data["category"],
            str(data["priority"]),
            data["status"],
            data["suggested_reply"],
            data["final_reply"],
            data["matched_faq_id"],
            data["sla_deadline"],
            data["received_at"],
            data["responded_at"],
        ]

    def list_messages(self, status: str | None = None, channel: str | None = None, limit: int = 100) -> list[CSMessage]:
        ws = self._open_ws()
        rows: list[CSMessage]
        if ws is not None:
            try:
                rows = [self._row_to_message(r) for r in ws.get_all_records()]
            except Exception as exc:
                logger.warning("cs_inbox list Sheets 실패, 폴백 사용: %s", exc)
                rows = self._read_fallback()
        else:
            rows = self._read_fallback()

        if status:
            rows = [x for x in rows if x.status == status]
        if channel:
            rows = [x for x in rows if x.channel == channel]

        rows.sort(key=lambda x: (x.received_at, x.message_id), reverse=True)
        return rows[: max(1, int(limit or 100))]

    def get(self, message_id: str) -> CSMessage | None:
        for msg in self.list_messages(limit=5000):
            if msg.message_id == message_id:
                return msg
        return None

    def upsert(self, msg: CSMessage) -> CSMessage:
        now = _now_iso()
        if not msg.message_id:
            msg.message_id = f"msg_{uuid.uuid4().hex[:12]}"
        if not msg.received_at:
            msg.received_at = now

        ws = self._open_ws()
        if ws is not None:
            try:
                rows = ws.get_all_records()
                for i, row in enumerate(rows):
                    if row.get("message_id") == msg.message_id:
                        row_num = i + 2
                        for col, value in enumerate(self._message_to_row(msg), start=1):
                            ws.update_cell(row_num, col, value)
                        return msg
                ws.append_row(self._message_to_row(msg))
                return msg
            except Exception as exc:
                logger.warning("cs_inbox upsert Sheets 실패, 폴백 사용: %s", exc)

        with self._LOCK:
            rows = self._read_fallback()
            replaced = False
            for i, existing in enumerate(rows):
                if existing.message_id == msg.message_id:
                    rows[i] = msg
                    replaced = True
                    break
            if not replaced:
                rows.append(msg)
            self._write_fallback(rows)
        return msg

    def mark_responded(self, message_id: str, final_reply: str) -> bool:
        msg = self.get(message_id)
        if not msg:
            return False
        msg.final_reply = final_reply
        msg.status = "resolved"
        msg.responded_at = _now_iso()
        return self.upsert(msg).message_id == message_id

    def stats_24h(self) -> dict:
        now = datetime.now(timezone.utc)
        since = now - timedelta(hours=24)
        rows = self.list_messages(limit=5000)
        recent = [x for x in rows if _parse_dt(x.received_at) and _parse_dt(x.received_at) >= since]

        total = len(recent)
        unresolved = [x for x in recent if not x.responded_at and x.status not in {"resolved", "auto_handled"}]
        resolved = [x for x in recent if x.responded_at or x.status in {"resolved", "auto_handled"}]

        response_minutes: list[float] = []
        for row in recent:
            recv = _parse_dt(row.received_at)
            resp = _parse_dt(row.responded_at)
            if recv and resp and resp >= recv:
                response_minutes.append((resp - recv).total_seconds() / 60)

        avg_minutes = sum(response_minutes) / len(response_minutes) if response_minutes else 0.0
        response_rate = (len(resolved) / total * 100) if total else 0.0

        return {
            "new_24h": total,
            "unanswered": len(unresolved),
            "urgent_unanswered": len([x for x in unresolved if x.priority >= 2]),
            "responded": len(resolved),
            "response_rate": round(response_rate, 1),
            "avg_response_minutes": round(avg_minutes, 1),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        value = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None
