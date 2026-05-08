from __future__ import annotations

import os
from dataclasses import dataclass

from src.messaging.models import Recipient


@dataclass
class Customer:
    customer_id: str
    customer_name: str
    language: str = "ko"
    email: str = ""
    phone: str = ""
    telegram_chat_id: str = ""
    kakao_user_id: str = ""


def send_to_channels(customer: Customer, message: str, channels: list[str]) -> dict[str, bool]:
    """채널별 발송 결과. 부분 실패 허용."""
    if os.getenv("CS_MULTICHANNEL_ENABLED", "1") != "1":
        return {ch: False for ch in channels}
    results: dict[str, bool] = {}
    for ch in channels:
        key = _normalize_channel(ch)
        payload = adjust_tone(message, key, customer.language)
        try:
            results[ch] = _send_one(customer, key, payload)
        except Exception:
            results[ch] = False
    return results


def adjust_tone(message: str, channel: str, language: str) -> str:
    """
    - telegram/sms: 짧고 친근
    - email: 격식 + 인사 + 서명
    - kakao_alimtalk: 템플릿 변수 형식
    """
    body = (message or "").strip()
    if not body:
        return ""
    if channel in {"telegram", "sms"}:
        short = body.replace("\n", " ").strip()
        return short if len(short) <= 140 else f"{short[:137]}..."
    if channel == "email":
        greet = "안녕하세요." if language == "ko" else "Hello,"
        sign = "감사합니다.\nKohgane CS팀" if language == "ko" else "Best regards,\nKohgane CS Team"
        return f"{greet}\n\n{body}\n\n{sign}"
    if channel == "kakao_alimtalk":
        return f"[Kohgane]\n{body}"
    return body


def _normalize_channel(channel: str) -> str:
    raw = (channel or "").strip().lower()
    if raw in {"kakao", "kakao_alimtalk"}:
        return "kakao_alimtalk"
    return raw


def _to_recipient(customer: Customer) -> Recipient:
    return Recipient(
        name=customer.customer_name or "고객님",
        user_id=customer.customer_id or None,
        locale=customer.language or "ko",
        email=customer.email or None,
        phone_e164=customer.phone or None,
        telegram_chat_id=customer.telegram_chat_id or None,
        kakao_user_id=customer.kakao_user_id or None,
    )


def _send_one(customer: Customer, channel: str, message: str) -> bool:
    recipient = _to_recipient(customer)
    if channel == "telegram":
        from src.messaging.channels.telegram_channel import TelegramNotifyChannel

        return bool(TelegramNotifyChannel().send(recipient, message, {}).sent)
    if channel == "email":
        from src.messaging.channels.email_channel import ResendChannel

        return bool(ResendChannel().send(recipient, message, {"subject": "CS 답변"}).sent)
    if channel == "sms":
        from src.messaging.channels.sms_channel import SMSChannel

        return bool(SMSChannel().send(recipient, message, {}).sent)
    if channel == "kakao_alimtalk":
        from src.messaging.channels.kakao_channel import KakaoAlimtalkChannel

        return bool(KakaoAlimtalkChannel().send(recipient, message, {}).sent)
    return False
