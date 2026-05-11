"""src/cs/unified_inbox.py — CS 통합 인박스 (Phase 145)."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class UnifiedMessage:
    message_id: str
    channel: str
    body: str
    status: str = "open"
    priority: str = "normal"
    unresolved_by_bot: bool = False
    received_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class UnifiedInbox:
    """마켓/이메일/카톡/챗봇 미해결 메시지를 단일 큐로 관리."""

    def __init__(self) -> None:
        self.enabled = os.getenv("CS_UNIFIED_INBOX_ENABLED", "1") == "1"
        self.ai_provider = os.getenv("CS_AI_DRAFT_PROVIDER", "openai")
        self._messages: list[UnifiedMessage] = []

    @staticmethod
    def classify_priority(body: str) -> str:
        text = (body or "").lower()
        if "환불" in text or "refund" in text or "지연" in text or "delay" in text:
            return "high"
        return "normal"

    def push(self, message: UnifiedMessage) -> UnifiedMessage:
        if not message.priority or message.priority == "normal":
            message.priority = self.classify_priority(message.body)
        if not message.received_at:
            message.received_at = datetime.now(timezone.utc).isoformat()
        self._messages.append(message)
        return message

    def list_messages(self, channel: str | None = None, status: str | None = None, priority: str | None = None) -> list[dict]:
        rows = self._messages
        if channel:
            rows = [m for m in rows if m.channel == channel]
        if status:
            rows = [m for m in rows if m.status == status]
        if priority:
            rows = [m for m in rows if m.priority == priority]
        return [m.to_dict() for m in rows]

    def draft_reply(self, message: UnifiedMessage) -> str:
        return f"[AI:{self.ai_provider}] 답변 초안: {message.body[:40]}"

    def sla_warning_count(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        threshold = now - timedelta(hours=24)
        count = 0
        for msg in self._messages:
            if msg.status != "open":
                continue
            try:
                received = datetime.fromisoformat(msg.received_at.replace("Z", "+00:00"))
            except Exception:
                received = now
            if received < threshold:
                count += 1
        return count

    def summary_24h(self) -> dict:
        open_count = len([m for m in self._messages if m.status == "open"])
        return {
            "unanswered": open_count,
            "sla_violations": self.sla_warning_count(),
            "ai_draft_enabled": bool(self.ai_provider),
            "processed_24h": len(self._messages) - open_count,
        }
