from __future__ import annotations
import logging
import os
from .base import InboundChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

class NaverTalkAdapter(InboundChannelAdapter):
    name = "naver_talk"

    def is_active(self) -> bool:
        return bool(os.getenv("NAVER_TALKTALK_BOT_ID") and os.getenv("NAVER_TALKTALK_ACCESS_TOKEN"))

    def poll(self, since: str | None = None) -> list[InboundMessage]:
        if not self.is_active():
            return []
        try:
            return self._fetch_messages(since)
        except Exception as exc:
            logger.warning("naver_talk 폴링 실패: %s", exc)
            return []

    def _fetch_messages(self, since: str | None) -> list[InboundMessage]:
        import requests
        bot_id = os.getenv("NAVER_TALKTALK_BOT_ID", "")
        token = os.getenv("NAVER_TALKTALK_ACCESS_TOKEN", "")
        url = f"https://gw.talk.naver.com/chatbot/v1/bot/{bot_id}/talk/message"
        params: dict = {"messageType": "TEXT", "since": since} if since else {"messageType": "TEXT"}
        resp = requests.get(url, headers={"Authorization": f"ct {token}"}, params=params, timeout=10)
        if not resp.ok:
            logger.warning("naver_talk API 실패 %s", resp.status_code)
            return []
        items = resp.json().get("messages", [])
        messages: list[InboundMessage] = []
        for item in items:
            messages.append(InboundMessage(
                raw_id=str(item.get("messageId", "")),
                customer_id=str(item.get("userId", "")),
                customer_name=str(item.get("userName") or item.get("userId") or "고객님"),
                body=str(item.get("textContent", {}).get("text", "") or item.get("content", "")),
                received_at=str(item.get("createdAt", "")),
                metadata={"channel": "naver_talk"},
            ))
        return messages

    def send_reply(self, customer_id: str, message: str, *, ref: str = "") -> bool:
        if not self.is_active():
            return False
        try:
            import requests
            bot_id = os.getenv("NAVER_TALKTALK_BOT_ID", "")
            token = os.getenv("NAVER_TALKTALK_ACCESS_TOKEN", "")
            url = f"https://gw.talk.naver.com/chatbot/v1/bot/{bot_id}/talk/send"
            resp = requests.post(
                url,
                headers={"Authorization": f"ct {token}", "Content-Type": "application/json"},
                json={"userId": customer_id, "textContent": {"text": message}},
                timeout=8,
            )
            return resp.ok
        except Exception as exc:
            logger.warning("naver_talk 발송 실패: %s", exc)
            return False
