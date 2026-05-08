from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from src.cs_bot.classifier import classify, detect_language
from src.cs_bot.auto_send_guard import should_auto_send
from src.cs_bot.faq_store import FAQStore
from src.cs_bot.inbox_store import CSMessage, InboxStore
from src.cs_bot.replier import suggest_reply_details
from src.cs_bot.sla import compute_deadline
from src.notifications.telegram import send_telegram

bp = Blueprint("cs_bot_inbound_telegram", __name__)


@bp.post("/webhooks/telegram/cs")
def telegram_inbound():
    """텔레그램 CS 웹훅 수신."""
    expected_secret = os.getenv("CS_TELEGRAM_WEBHOOK_SECRET", "")
    received_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if expected_secret and expected_secret != received_secret:
        return jsonify({"ok": False, "error": "invalid_secret"}), 403

    payload = request.get_json(silent=True) or {}
    message = payload.get("message") or {}
    text = str(message.get("text") or "").strip()
    chat = message.get("chat") or {}
    from_user = message.get("from") or {}

    customer_name = str(from_user.get("first_name") or "")
    if from_user.get("last_name"):
        customer_name = f"{customer_name} {from_user.get('last_name')}".strip()
    language = detect_language(text)
    category, priority = classify(text, language)

    store = InboxStore()
    faq_store = FAQStore()
    msg = CSMessage(
        message_id=f"tg_{message.get('message_id') or uuid.uuid4().hex[:10]}",
        channel="telegram",
        direction="inbound",
        customer_id=str(chat.get("id") or from_user.get("id") or ""),
        customer_name=customer_name or "고객",
        body=text,
        language=language,
        category=category,
        priority=priority,
        status="open",
    )
    msg.sla_deadline = compute_deadline(msg.received_at, msg.category)
    suggested, confidence, matched_faq = suggest_reply_details(msg, faq_store)
    msg.suggested_reply = suggested
    msg.matched_faq_id = matched_faq.faq_id if matched_faq else ""
    stored = store.upsert(msg)

    urgency = "긴급" if stored.priority >= 2 else "일반"
    send_telegram(
        f"📨 신규 CS 메시지 ({urgency})\n"
        f"- 채널: 텔레그램\n"
        f"- 고객: {stored.customer_name}\n"
        f"- 카테고리: {stored.category}\n"
        f"- 본문: \"{stored.body[:120]}\"\n"
        f"🔗 처리하기: /seller/cs/inbox?msg={stored.message_id}",
        urgency="critical" if stored.priority >= 2 else "info",
    )

    can_send, reason = should_auto_send(stored, stored.suggested_reply, confidence)
    if can_send:
        if _send_customer_reply(chat_id=stored.customer_id, text=stored.suggested_reply):
            stored.status = "auto_handled"
            stored.final_reply = stored.suggested_reply
            stored.responded_at = datetime.now(timezone.utc).isoformat()
            store.upsert(stored)
            send_telegram(
                f"🤖 CS 자동 발송 완료\n- 메시지: {stored.message_id}\n- 카테고리: {stored.category}\n- 신뢰도: {confidence:.2f}",
                urgency="warning",
            )
    elif os.getenv("CS_AUTO_SEND", "0") == "1":
        send_telegram(f"ℹ️ CS 자동 발송 보류: {reason} ({stored.message_id})", urgency="info")

    return jsonify({"ok": True, "message_id": stored.message_id})


def _send_customer_reply(chat_id: str, text: str) -> bool:
    if not chat_id or not text:
        return False
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return False
    try:
        import requests

        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=5,
        )
        return bool(resp.ok)
    except Exception:
        return False
