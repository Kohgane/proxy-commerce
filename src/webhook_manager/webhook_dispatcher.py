"""src/webhook_manager/webhook_dispatcher.py — 웹훅 이벤트 발송."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from .delivery_log import DeliveryLog
from .retry_scheduler import RetryScheduler
from .webhook_registry import WebhookRegistry
from .webhook_signer import WebhookSigner


class WebhookDispatcher:
    """이벤트 발생 시 등록된 웹훅으로 페이로드 전송 (비동기, 재시도)."""

    def __init__(self,
                 registry: Optional[WebhookRegistry] = None,
                 signer: Optional[WebhookSigner] = None,
                 log: Optional[DeliveryLog] = None,
                 scheduler: Optional[RetryScheduler] = None,
                 timeout: int = 10) -> None:
        self.registry = registry or WebhookRegistry()
        self.signer = signer or WebhookSigner()
        self.log = log or DeliveryLog()
        self.scheduler = scheduler or RetryScheduler()
        self.timeout = timeout

    def dispatch(self, event: str, payload: dict) -> list:
        """이벤트를 구독하는 모든 웹훅으로 페이로드 전송."""
        webhooks = self.registry.list(event=event, active_only=True)
        results = []
        for webhook in webhooks:
            result = self._send(webhook, event, payload, attempt=1)
            results.append(result)
        return results

    def _send(self, webhook: dict, event: str, payload: dict,
              attempt: int = 1) -> dict:
        """단일 웹훅으로 전송."""
        webhook_id = webhook["webhook_id"]
        secret = webhook.get("secret", "")
        url = webhook["url"]

        signed = self.signer.sign(payload, secret) if secret else {
            "body": json.dumps(payload, ensure_ascii=False),
            "signature": "",
            "timestamp": 0,
        }

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Event": event,
        }
        if signed.get("signature"):
            headers["X-Webhook-Signature"] = signed["signature"]
            headers["X-Webhook-Timestamp"] = str(signed["timestamp"])

        try:
            body_bytes = signed["body"].encode()
            req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                response_code = resp.getcode()
                response_body = resp.read(500).decode(errors="replace")
            record = self.log.record(
                webhook_id, event, "success",
                response_code=response_code,
                response_body=response_body,
                attempt=attempt,
            )
        except Exception as exc:
            record = self.log.record(
                webhook_id, event, "failed",
                response_code=0,
                error=str(exc)[:200],
                attempt=attempt,
            )
            if self.scheduler.should_retry(attempt):
                self.scheduler.schedule(webhook_id, event, payload, attempt + 1)

        return record

    def test_webhook(self, webhook_id: str) -> dict:
        """테스트 페이로드로 웹훅 전송."""
        webhook = self.registry.get(webhook_id)
        if not webhook:
            raise KeyError(f"웹훅 없음: {webhook_id}")
        return self._send(webhook, "test", {"test": True, "webhook_id": webhook_id})
