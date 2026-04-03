"""src/email_service/email_queue.py — 이메일 큐."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List

from .email_provider import EmailProvider
from .email_template import EmailTemplate


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class EmailQueue:
    """이메일 발송 큐 관리."""

    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries
        self._pending: List[dict] = []
        self._failed: List[dict] = []
        self._sent: List[dict] = []

    def enqueue(self, to: str, template_name: str, context: dict) -> str:
        email_id = str(uuid.uuid4())
        self._pending.append({
            "email_id": email_id,
            "to": to,
            "template_name": template_name,
            "context": context,
            "retries": 0,
            "enqueued_at": _now_iso(),
        })
        return email_id

    def process_queue(self, provider: EmailProvider) -> List[dict]:
        results = []
        remaining = []
        for item in self._pending:
            try:
                template = EmailTemplate.get_builtin(item["template_name"])
                subject, body = template.render(item["context"])
                result = provider.send(item["to"], subject, body)
                self._sent.append({**item, "result": result, "sent_at": _now_iso()})
                results.append({"email_id": item["email_id"], "status": "sent"})
            except Exception as exc:
                item["retries"] += 1
                item["last_error"] = str(exc)
                if item["retries"] >= self.max_retries:
                    self._failed.append(item)
                    results.append({"email_id": item["email_id"], "status": "failed"})
                else:
                    remaining.append(item)
                    results.append({"email_id": item["email_id"], "status": "retry"})
        self._pending = remaining
        return results

    def get_pending(self) -> List[dict]:
        return list(self._pending)

    def get_failed(self) -> List[dict]:
        return list(self._failed)

    def retry_failed(self, provider: EmailProvider) -> List[dict]:
        to_retry = list(self._failed)
        self._failed = []
        self._pending.extend(to_retry)
        return self.process_queue(provider)
