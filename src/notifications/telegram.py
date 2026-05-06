"""src/notifications/telegram.py — 텔레그램 알림 전송 + health_check (Phase 130/136).

사용법:
    from src.notifications.telegram import send_telegram, health_check
    send_telegram("새 주문 3건 도착", urgency="info")
    result = health_check()  # {"status": "ok", "bot": "MyBot"} 또는 {"status": "fail", ...}

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


def health_check() -> dict:
    """텔레그램 봇 + chat_id 연결 상태 진단.

    Returns:
        {"status": "ok", "bot": "봇이름"} 성공 시
        {"status": "missing", "hint": "..."} 키 미설정 시
        {"status": "fail", "stage": "getMe"|"getChat", ...} 연결 실패 시
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token:
        return {"status": "missing", "hint": "TELEGRAM_BOT_TOKEN 미설정"}
    if not chat_id:
        return {"status": "missing", "hint": "TELEGRAM_CHAT_ID 미설정"}

    try:
        import requests as _requests

        # 봇 자체 정상성 확인
        try:
            r = _requests.get(
                f"https://api.telegram.org/bot{token}/getMe",
                timeout=5,
            )
            if r.status_code != 200 or not r.json().get("ok"):
                return {
                    "status": "fail",
                    "stage": "getMe",
                    "code": r.status_code,
                    "hint": "TELEGRAM_BOT_TOKEN이 올바른지 확인하세요.",
                }
            bot_info = r.json().get("result", {})
        except Exception as e:
            return {"status": "fail", "stage": "getMe", "error": str(e)}

        # chat_id 도달 가능성 확인
        try:
            r2 = _requests.get(
                f"https://api.telegram.org/bot{token}/getChat",
                params={"chat_id": chat_id},
                timeout=5,
            )
            if r2.status_code != 200 or not r2.json().get("ok"):
                return {
                    "status": "fail",
                    "stage": "getChat",
                    "hint": "봇을 채팅방에 초대했나요? TELEGRAM_CHAT_ID가 올바른가요?",
                    "response": r2.json(),
                }
            chat_info = r2.json().get("result", {})
        except Exception as e:
            return {"status": "fail", "stage": "getChat", "error": str(e)}

        return {
            "status": "ok",
            "bot": bot_info.get("username") or bot_info.get("first_name"),
            "chat_title": chat_info.get("title") or chat_info.get("username") or chat_id,
        }

    except ImportError:
        return {"status": "fail", "stage": "import", "error": "requests 패키지 없음"}
