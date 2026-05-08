from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from .base import InboundChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

class ElevenQAAdapter(InboundChannelAdapter):
    name = "eleven_qa"

    def is_active(self) -> bool:
        return bool(os.getenv("ELEVEN_API_KEY") or os.getenv("ELEVEN_OPENAPIKEY"))

    def poll(self, since: str | None = None) -> list[InboundMessage]:
        if not self.is_active():
            return []
        try:
            return self._fetch_qna(since)
        except Exception as exc:
            logger.warning("eleven_qa 폴링 실패: %s", exc)
            return []

    def _fetch_qna(self, since: str | None) -> list[InboundMessage]:
        import requests
        api_key = os.getenv("ELEVEN_API_KEY") or os.getenv("ELEVEN_OPENAPIKEY", "")
        url = "https://api.11st.co.kr/rest/productservice/qa/unAnswered"
        params = {"key": api_key, "pageNum": 1, "pageSize": 50}
        resp = requests.get(url, params=params, timeout=10)
        if not resp.ok:
            logger.warning("eleven_qa API 실패 %s", resp.status_code)
            return []
        data = resp.json()
        items = data.get("ProductQnAList", {}).get("ProductQnA", [])
        if isinstance(items, dict):
            items = [items]
        messages: list[InboundMessage] = []
        for item in items:
            messages.append(InboundMessage(
                raw_id=str(item.get("qnaSeq", "")),
                customer_id=str(item.get("memberId") or item.get("memberID") or "고객님"),
                customer_name=str(item.get("memberNickname") or item.get("memberId") or "고객님"),
                body=str(item.get("question", "")),
                received_at=str(item.get("regDt") or datetime.now(timezone.utc).isoformat()),
                metadata={"product_id": str(item.get("prdNo", "")), "qna_seq": str(item.get("qnaSeq", ""))},
            ))
        return messages

    def send_reply(self, customer_id: str, message: str, *, ref: str = "") -> bool:
        if not self.is_active():
            return False
        try:
            import requests
            api_key = os.getenv("ELEVEN_API_KEY") or os.getenv("ELEVEN_OPENAPIKEY", "")
            if not ref:
                return False
            url = f"https://api.11st.co.kr/rest/productservice/qa/{ref}/answer"
            resp = requests.post(
                url,
                params={"key": api_key},
                json={"answer": message},
                timeout=8,
            )
            return resp.ok
        except Exception as exc:
            logger.warning("eleven_qa 답변 발송 실패: %s", exc)
            return False
