"""src/email_service/smtp_provider.py — SMTP 이메일 공급자 모의 구현."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .email_provider import EmailProvider


class SMTPProvider(EmailProvider):
    """SMTP 이메일 발송 모의 구현 (실제 SMTP 연결 없음)."""

    def __init__(self, host: str = "smtp.example.com", port: int = 587,
                 user: str = "noreply@example.com") -> None:
        self.host = host
        self.port = port
        self.user = user
        self._sent: List[dict] = []

    def send(self, to: str, subject: str, body: str, html_body: Optional[str] = None) -> dict:
        result = {
            "email_id": str(uuid.uuid4()),
            "provider": "smtp",
            "to": to,
            "subject": subject,
            "sent_at": datetime.now(tz=timezone.utc).isoformat(),
            "status": "sent",
        }
        self._sent.append(result)
        return result

    def get_sent(self) -> List[dict]:
        return list(self._sent)
