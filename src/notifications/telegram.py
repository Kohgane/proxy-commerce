"""src/notifications/telegram.py — 텔레그램 알림 전송 (Phase 130).

사용법:
    from src.notifications.telegram import send_telegram
    send_telegram("새 주문 3건 도착", urgency="info")

ADAPTER_DRY_RUN=1 또는 키 미설정 시 silently noop.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_URGENCY_PREFIX = {
    "info": "ℹ️",
    "warning": "⚠️",
    "critical": "🚨",
}


def send_telegram(message: str, urgency: str = "info") -> bool:
    """텔레그램 메시지 전송.

    Args:
        message: 전송할 메시지 내용
        urgency: "info" | "warning" | "critical"

    Returns:
        전송 성공 시 True, 키 미설정/dry-run/실패 시 False
    """
    # ADAPTER_DRY_RUN=1 시 모든 외부 API 호출 차단
    if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
        logger.info("ADAPTER_DRY_RUN=1 — 텔레그램 전송 차단: %s", message[:50])
        return False

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not (bot_token and chat_id):
        logger.debug("TELEGRAM_BOT_TOKEN/CHAT_ID 미설정 — 알림 비활성")
        return False

    prefix = _URGENCY_PREFIX.get(urgency, "ℹ️")
    text = f"{prefix} [proxy-commerce] {message}"

    try:
        import requests
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5,
        )
        if resp.ok:
            logger.info("텔레그램 전송 성공: urgency=%s", urgency)
            return True
        logger.warning("텔레그램 전송 실패 HTTP %s: %s", resp.status_code, resp.text[:200])
        return False
    except Exception as exc:
        logger.warning("텔레그램 전송 오류: %s", exc)
        return False
