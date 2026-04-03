"""src/email_service/sendgrid_provider.py — SendGrid 이메일 공급자 모의 구현."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .email_provider import EmailProvider


class SendGridProvider(EmailProvider):
    """SendGrid 이메일 발송 모의 구현 (실제 API 호출 없음)."""

    def __init__(self, api_key: str = "mock-api-key") -> None:
        self.api_key = api_key
        self._sent: List[dict] = []

    def send(self, to: str, subject: str, body: str, html_body: Optional[str] = None) -> dict:
        result = {
            "email_id": str(uuid.uuid4()),
            "provider": "sendgrid",
            "to": to,
            "subject": subject,
            "sent_at": datetime.now(tz=timezone.utc).isoformat(),
            "status": "sent",
        }
        self._sent.append(result)
        return result

    def get_sent(self) -> List[dict]:
        return list(self._sent)
