"""src/webhook_manager/webhook_dispatcher.py — 웹훅 발송."""
import json
import logging
import urllib.request
import urllib.error
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class WebhookDispatcher:
    """웹훅 발송, 서명, 로깅."""

    def __init__(self, request_func: Optional[Callable] = None):
        from .webhook_registry import WebhookRegistry
        from .webhook_signer import WebhookSigner
        from .delivery_log import DeliveryLog
        from .retry_scheduler import RetryScheduler
        self._registry = WebhookRegistry()
        self._signer = WebhookSigner()
        self._log = DeliveryLog()
        self._retry = RetryScheduler()
        self._request_func = request_func or self._default_request

    def _default_request(self, url: str, payload_bytes: bytes, headers: dict) -> tuple:
        """실제 HTTP POST 전송."""
        req = urllib.request.Request(url, data=payload_bytes, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read().decode('utf-8', errors='replace')
        except urllib.error.HTTPError as exc:
            return exc.code, str(exc)
        except Exception as exc:
            return 0, str(exc)

    def dispatch(self, webhook_id: str, event: str, payload: dict, attempt: int = 1) -> dict:
        webhook = self._registry.get_webhook(webhook_id)
        if webhook is None:
            raise KeyError(f"웹훅 없음: {webhook_id}")
        if not webhook.get('active', True):
            return {'status': 'skipped', 'reason': 'inactive'}
        payload_bytes = json.dumps(payload).encode()
        secret = webhook.get('secret', '')
        signature = self._signer.sign(payload_bytes, secret) if secret else ''
        headers = {
            'Content-Type': 'application/json',
            'X-Webhook-Event': event,
        }
        if signature:
            headers['X-Webhook-Signature'] = signature
        status_code, response = self._request_func(webhook['url'], payload_bytes, headers)
        record = self._log.log_delivery(webhook_id, event, status_code, response, attempt)
        if not record['success'] and attempt <= 5:
            self._retry.schedule_retry(webhook_id, event, payload, attempt + 1)
        return record
