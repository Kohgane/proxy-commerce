"""src/messaging/channels/kakao_channel.py — 카카오 알림톡 채널 (Phase 134).

카카오 알림톡 발송 (Aligo 또는 네이버클라우드 카카오 알림톡 API).
KAKAO_ALIMTALK_API_KEY, KAKAO_ALIMTALK_SENDER_KEY 필요.
"""
from __future__ import annotations

import logging
import os

from src.messaging.channels.base import MessageChannel, _dry_run
from src.messaging.models import Recipient, SendResult

logger = logging.getLogger(__name__)


class KakaoAlimtalkChannel(MessageChannel):
    """카카오 알림톡 채널 (Aligo 기반)."""

    name = "kakao_alimtalk"

    @property
    def is_active(self) -> bool:
        return bool(
            os.getenv("KAKAO_ALIMTALK_API_KEY")
            and os.getenv("KAKAO_ALIMTALK_SENDER_KEY")
        )

    def send(self, recipient: Recipient, template_body: str, context: dict) -> SendResult:
        if _dry_run():
            return self._dry_run_send(recipient, template_body)

        if not self.is_active:
            return SendResult(sent=False, channel=self.name, error="not_configured")

        phone = recipient.phone_e164 or recipient.kakao_user_id
        if not phone:
            return SendResult(sent=False, channel=self.name, error="no_phone")

        try:
            import requests
            api_key = os.getenv("KAKAO_ALIMTALK_API_KEY", "")
            sender_key = os.getenv("KAKAO_ALIMTALK_SENDER_KEY", "")
            user_id = os.getenv("KAKAO_ALIMTALK_USER_ID", "")
            template_code = context.get("kakao_template_code", "")

            # Aligo 카카오 알림톡 API
            payload = {
                "apikey": api_key,
                "userid": user_id,
                "senderkey": sender_key,
                "tpl_code": template_code,
                "sender": os.getenv("KAKAO_ALIMTALK_SENDER", ""),
                # E.164 → 한국 로컬 번호 변환 (+82XXXXXXXXX → 0XXXXXXXXX)
                "receiver_1": ("0" + phone[3:]) if phone.startswith("+82") else phone.replace("+", ""),
                "recvname_1": recipient.name,
                "subject_1": context.get("subject", "알림"),
                "message_1": template_body,
            }
            resp = requests.post(
                "https://kakaoapi.aligo.in/akv10/alimtalk/send/",
                data=payload,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 0:
                return SendResult(sent=True, channel=self.name)
            return SendResult(sent=False, channel=self.name, error=str(data.get("message", "")))
        except Exception as exc:
            logger.warning("카카오 알림톡 오류: %s", exc)
            return SendResult(sent=False, channel=self.name, error=str(exc))

    def health_check(self) -> dict:
        status = "ok" if self.is_active else "missing_key"
        return {
            "name": self.name,
            "status": status,
            "detail": "KAKAO_ALIMTALK_API_KEY + KAKAO_ALIMTALK_SENDER_KEY",
        }
