"""src/messaging/router.py — 다채널 메시지 라우터 (Phase 134).

고객 locale + 가용 채널 → 최적 채널 자동 선택.

기본 우선순위:
- ko: 카카오 알림톡 → SMS → 텔레그램 → 이메일
- ja: LINE → SMS → 이메일
- en/기타: WhatsApp → 이메일 → SMS
- zh-CN: WeChat → 이메일 → SMS
- zh-TW: LINE → 이메일 → SMS
- vi: WhatsApp → 이메일
- default: 이메일 → SMS

환경변수 미설정 채널 자동 skip.
preferred_channels가 있으면 그 순서 우선.
모든 채널 fail 시 운영자에게 텔레그램 fallback 알림.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.messaging.models import Recipient, SendResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 로케일별 채널 우선순위
# ---------------------------------------------------------------------------

LOCALE_PRIORITY: Dict[str, List[str]] = {
    "ko": ["kakao_alimtalk", "sms", "telegram", "email"],
    "ja": ["line", "line_notify", "sms", "email"],
    "en": ["whatsapp", "email", "sms"],
    "zh-CN": ["wechat", "email", "sms"],
    "zh-TW": ["line", "email", "sms"],
    "vi": ["whatsapp", "email"],
    "th": ["whatsapp", "email"],
    "default": ["email", "sms", "telegram"],
}


def _has_recipient_id(recipient: Recipient, channel_name: str) -> bool:
    """수신자가 해당 채널의 식별자를 갖고 있는지 확인."""
    if channel_name == "email":
        return bool(recipient.email)
    if channel_name in ("telegram",):
        return bool(recipient.telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID"))
    if channel_name == "kakao_alimtalk":
        return bool(recipient.phone_e164 or recipient.kakao_user_id)
    if channel_name in ("line", "line_notify"):
        return bool(recipient.line_user_id or channel_name == "line_notify")
    if channel_name == "whatsapp":
        return bool(recipient.whatsapp_phone or recipient.phone_e164)
    if channel_name == "wechat":
        return bool(recipient.wechat_openid)
    if channel_name == "sms":
        return bool(recipient.phone_e164)
    if channel_name == "discord":
        return True  # webhook 기반이라 수신자 식별자 불필요
    return False


class MessageRouter:
    """다채널 메시지 라우터."""

    def __init__(self) -> None:
        from src.messaging.channels.email_channel import ResendChannel
        from src.messaging.channels.telegram_channel import TelegramNotifyChannel
        from src.messaging.channels.kakao_channel import KakaoAlimtalkChannel
        from src.messaging.channels.line_channel import LineNotifyChannel, LineMessagingChannel
        from src.messaging.channels.whatsapp_channel import WhatsAppChannel
        from src.messaging.channels.wechat_channel import WeChatChannel
        from src.messaging.channels.sms_channel import SMSChannel
        from src.messaging.channels.discord_channel import DiscordChannel
        from src.messaging.templates import TemplateStore

        self.channels = {
            "email": ResendChannel(),
            "telegram": TelegramNotifyChannel(),
            "kakao_alimtalk": KakaoAlimtalkChannel(),
            "line_notify": LineNotifyChannel(),
            "line": LineMessagingChannel(),
            "whatsapp": WhatsAppChannel(),
            "wechat": WeChatChannel(),
            "sms": SMSChannel(),
            "discord": DiscordChannel(),
        }
        self.templates = TemplateStore()
        self._log = MessageLog()

    def send(self, recipient: Recipient, event: str, context: dict) -> dict:
        """이벤트 → 최적 채널로 발송.

        Args:
            recipient: 수신자 정보
            event: 이벤트 명 (order_received, order_shipped, ...)
            context: 템플릿 변수 딕셔너리

        Returns:
            {"sent": bool, "channel": str, "fallback": ...}
        """
        order = (
            recipient.preferred_channels
            or LOCALE_PRIORITY.get(recipient.locale, LOCALE_PRIORITY["default"])
        )

        last_error: Optional[Exception] = None
        for ch_name in order:
            ch = self.channels.get(ch_name)
            if ch is None:
                continue
            if not ch.is_active:
                logger.debug("채널 비활성 skip: %s", ch_name)
                continue
            if not _has_recipient_id(recipient, ch_name):
                logger.debug("수신자 식별자 없음 skip: %s", ch_name)
                continue

            try:
                tpl = self.templates.get(event, ch_name, recipient.locale)
                rendered = tpl.render({**context, "name": recipient.name})
                result = ch.send(recipient, rendered, context)
                self._log.append(recipient, ch_name, event, result)
                if result.sent:
                    logger.info(
                        "메시지 발송 성공: user=%s channel=%s event=%s",
                        recipient.user_id or recipient.name,
                        ch_name,
                        event,
                    )
                    return {"sent": True, "channel": ch_name, **result.to_dict()}
                last_error = Exception(result.error or "send_returned_false")
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "채널 발송 실패 %s: %s", ch_name, exc
                )
                self._log.append(
                    recipient, ch_name, event,
                    SendResult(sent=False, channel=ch_name, error=str(exc)),
                )
                continue

        # 모든 채널 실패 → 운영자 텔레그램 fallback
        logger.error(
            "모든 채널 실패 — 운영자 fallback: user=%s event=%s last_error=%s",
            recipient.user_id or recipient.name,
            event,
            last_error,
        )
        self._notify_admin_fallback(recipient, event, last_error)
        return {"sent": False, "fallback": "admin_telegram", "error": str(last_error)}

    def _notify_admin_fallback(self, recipient: Recipient, event: str, error: Optional[Exception]) -> None:
        """모든 채널 실패 시 운영자 텔레그램 알림."""
        try:
            from src.notifications.telegram import send_telegram
            msg = (
                f"⚠️ 고객 메시지 발송 실패\n"
                f"이벤트: {event}\n"
                f"수신자: {recipient.name} ({recipient.user_id or '-'})\n"
                f"locale: {recipient.locale}\n"
                f"오류: {error}"
            )
            send_telegram(msg, urgency="warning")
        except Exception as exc:
            logger.error("운영자 fallback 알림도 실패: %s", exc)

    def test_send(self, channel_name: str, locale: str, event: str, context: dict) -> dict:
        """테스트 메시지 발송 (운영자 본인에게).

        채널 + locale + 이벤트 선택 → 운영자 본인에게 발송.
        """
        admin_recipient = Recipient(
            name="관리자",
            user_id="admin",
            locale=locale,
            email=_first_admin_email(),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        )
        return self.send(admin_recipient, event, {
            "order_id": "TEST-001",
            "tracking_no": "TEST1234567890",
            "courier_name": "테스트택배",
            "eta_date": "2026-05-10",
            "tracking_url": "https://example.com/track",
            "shop_url": "https://kohganemultishop.org",
            "total_krw": "29900",
            "placed_at": "2026-05-05 10:00",
            "product_name": "테스트 상품",
            "refund_amount": "29900",
            "refund_method": "카드",
            "refund_date": "2026-05-05",
            **context,
        })

    def channels_status(self) -> list:
        """모든 채널 상태 반환."""
        return [ch.health_check() for ch in self.channels.values()]


def _first_admin_email() -> Optional[str]:
    raw = os.getenv("ADMIN_EMAILS", "")
    if not raw:
        return None
    parts = [e.strip() for e in raw.split(",") if e.strip()]
    return parts[0] if parts else None


# ---------------------------------------------------------------------------
# 메시지 발송 로그
# ---------------------------------------------------------------------------

class MessageLog:
    """Google Sheets message_log 워크시트 기록."""

    WORKSHEET_NAME = "message_log"
    HEADERS = [
        "sent_at", "recipient_user_id", "locale", "channel",
        "event", "template_key", "status", "provider_msg_id", "error",
    ]

    def __init__(self) -> None:
        self._ws = None

    def _get_ws(self):
        if self._ws is not None:
            return self._ws
        try:
            from src.utils.sheets import get_worksheet
            ws = get_worksheet(self.WORKSHEET_NAME, headers=self.HEADERS)
            self._ws = ws
            return ws
        except Exception as exc:
            logger.debug("message_log 워크시트 접근 불가: %s", exc)
            return None

    def append(self, recipient: Recipient, channel: str, event: str, result: SendResult) -> None:
        """발송 로그 추가."""
        ws = self._get_ws()
        if ws is None:
            return
        try:
            now = datetime.now(timezone.utc).isoformat()
            row = [
                now,
                recipient.user_id or "",
                recipient.locale,
                channel,
                event,
                f"{event}.{recipient.locale}.{channel}",
                "ok" if result.sent else "fail",
                result.provider_msg_id or "",
                result.error or "",
            ]
            ws.append_row(row)
        except Exception as exc:
            logger.debug("message_log 기록 오류: %s", exc)

    def recent(self, n: int = 50) -> list:
        """최근 N건 조회."""
        ws = self._get_ws()
        if ws is None:
            return []
        try:
            rows = ws.get_all_records()
            return rows[-n:] if len(rows) > n else rows
        except Exception as exc:
            logger.warning("message_log 조회 오류: %s", exc)
            return []
