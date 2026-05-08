from __future__ import annotations
import logging
import os
from datetime import datetime, timezone
from .base import InboundChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

class CoupangQAAdapter(InboundChannelAdapter):
    name = "coupang_qa"

    def is_active(self) -> bool:
        return bool(os.getenv("COUPANG_ACCESS_KEY") and os.getenv("COUPANG_SECRET_KEY"))

    def poll(self, since: str | None = None) -> list[InboundMessage]:
        if not self.is_active():
            return []
        try:
            return self._fetch_qna(since)
        except Exception as exc:
            logger.warning("coupang_qa 폴링 실패: %s", exc)
            return []

    def _fetch_qna(self, since: str | None) -> list[InboundMessage]:
        import hmac
        import hashlib
        import requests

        access_key = os.getenv("COUPANG_ACCESS_KEY", "")
        secret_key = os.getenv("COUPANG_SECRET_KEY", "")
        vendor_id = os.getenv("COUPANG_VENDOR_ID", "")
        if not vendor_id:
            logger.debug("COUPANG_VENDOR_ID 미설정 — coupang_qa 스킵")
            return []

        # Coupang Wing API signature
        dt_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        method = "GET"
        uri = f"/v2/providers/seller_api/apis/api/v1/vendors/{vendor_id}/qnas"
        params = "pageNum=1&pageSize=50&answered=false"
        message = f"{dt_str}{method}{uri}{params}"
        signature = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
        authorization = f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={dt_str}, signature={signature}"

        url = f"https://api-gateway.coupang.com{uri}?{params}"
        resp = requests.get(url, headers={"Authorization": authorization, "Content-Type": "application/json"}, timeout=10)
        if not resp.ok:
            logger.warning("coupang_qa API 실패 %s: %s", resp.status_code, resp.text[:200])
            return []

        data = resp.json()
        items = data.get("data", {}).get("content", []) if isinstance(data.get("data"), dict) else []
        messages: list[InboundMessage] = []
        for item in items:
            q_id = str(item.get("questionId") or item.get("qnaId") or "")
            writer = str(item.get("writerMemberId") or item.get("customerName") or "고객님")
            body = str(item.get("questionContent") or item.get("content") or "")
            created_at = str(item.get("createdAt") or item.get("questionCreatedAt") or datetime.now(timezone.utc).isoformat())
            product_id = str(item.get("productId") or "")
            messages.append(InboundMessage(
                raw_id=q_id,
                customer_id=writer,
                customer_name=writer,
                body=body,
                received_at=created_at,
                metadata={"product_id": product_id, "question_id": q_id},
            ))
        return messages

    def send_reply(self, customer_id: str, message: str, *, ref: str = "") -> bool:
        if not self.is_active():
            return False
        try:
            import hmac
            import hashlib
            import requests
            from datetime import datetime, timezone

            access_key = os.getenv("COUPANG_ACCESS_KEY", "")
            secret_key = os.getenv("COUPANG_SECRET_KEY", "")
            vendor_id = os.getenv("COUPANG_VENDOR_ID", "")
            if not (vendor_id and ref):
                return False

            dt_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            method = "POST"
            uri = f"/v2/providers/seller_api/apis/api/v1/vendors/{vendor_id}/qnas/{ref}/answers"
            message_str = f"{dt_str}{method}{uri}"
            signature = hmac.new(secret_key.encode(), message_str.encode(), hashlib.sha256).hexdigest()
            authorization = f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={dt_str}, signature={signature}"

            url = f"https://api-gateway.coupang.com{uri}"
            resp = requests.post(
                url,
                headers={"Authorization": authorization, "Content-Type": "application/json"},
                json={"content": message},
                timeout=10,
            )
            return resp.ok
        except Exception as exc:
            logger.warning("coupang_qa 답변 발송 실패: %s", exc)
            return False
