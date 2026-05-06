"""src/messaging/models.py — 메시징 공통 데이터 모델 (Phase 134)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Recipient:
    """메시지 수신자 정보."""

    name: str
    user_id: Optional[str] = None
    locale: str = "ko"  # ko / ja / en / zh-CN / zh-TW / vi / th ...

    # 채널별 식별자
    email: Optional[str] = None
    phone_e164: Optional[str] = None          # +821012345678
    telegram_chat_id: Optional[str] = None
    kakao_user_id: Optional[str] = None
    line_user_id: Optional[str] = None
    whatsapp_phone: Optional[str] = None
    wechat_openid: Optional[str] = None

    preferred_channels: List[str] = field(default_factory=list)  # ["kakao", "email"]

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "locale": self.locale,
            "email": self.email,
            "phone_e164": self.phone_e164,
            "telegram_chat_id": self.telegram_chat_id,
            "kakao_user_id": self.kakao_user_id,
            "line_user_id": self.line_user_id,
            "whatsapp_phone": self.whatsapp_phone,
            "wechat_openid": self.wechat_openid,
            "preferred_channels": self.preferred_channels,
        }


@dataclass
class SendResult:
    """메시지 발송 결과."""

    sent: bool
    channel: str
    provider_msg_id: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "sent": self.sent,
            "channel": self.channel,
            "provider_msg_id": self.provider_msg_id,
            "error": self.error,
        }
