"""src/email_service/email_provider.py — EmailProvider ABC."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class EmailProvider(ABC):
    """이메일 발송 추상 기반 클래스."""

    @abstractmethod
    def send(self, to: str, subject: str, body: str, html_body: Optional[str] = None) -> dict:
        """이메일 발송. 결과 dict 반환."""
