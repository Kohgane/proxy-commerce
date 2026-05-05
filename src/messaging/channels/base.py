"""src/messaging/channels/base.py — 채널 어댑터 추상 기반 클래스 (Phase 134)."""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

from src.messaging.models import Recipient, SendResult

logger = logging.getLogger(__name__)


def _dry_run() -> bool:
    return os.getenv("ADAPTER_DRY_RUN", "0") == "1"


class MessageChannel(ABC):
    """채널 어댑터 공통 인터페이스."""

    name: str  # 채널 식별자 (예: "email", "telegram", "kakao_alimtalk")

    @abstractmethod
    def send(self, recipient: Recipient, template_body: str, context: dict) -> SendResult:
        """메시지 발송.

        Args:
            recipient: 수신자 정보
            template_body: 렌더링된 메시지 본문
            context: 템플릿 변수 딕셔너리

        Returns:
            SendResult
        """
        ...

    @abstractmethod
    def health_check(self) -> dict:
        """채널 헬스 체크.

        Returns:
            {"name": ..., "status": "ok"|"error", "detail": ...}
        """
        ...

    @property
    def is_active(self) -> bool:
        """채널 활성 여부 (환경변수로 판단)."""
        return False

    def _dry_run_send(self, recipient: Recipient, template_body: str) -> SendResult:
        """dry-run 모드 공통 처리."""
        logger.info(
            "ADAPTER_DRY_RUN=1 — %s 전송 차단: recipient=%s body=%s",
            self.name,
            recipient.name,
            template_body[:50],
        )
        return SendResult(sent=False, channel=self.name, error="dry_run")
