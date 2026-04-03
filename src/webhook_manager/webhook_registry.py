"""src/webhook_manager/webhook_registry.py — 웹훅 등록."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class WebhookRegistry:
    """웹훅 등록/조회/수정/삭제."""

    def __init__(self):
        self._webhooks: Dict[str, dict] = {}

    def register(self, url: str, events: List[str], secret: str = '') -> dict:
        webhook_id = str(uuid.uuid4())[:8]
        webhook = {
            'id': webhook_id,
            'url': url,
            'events': events,
            'secret': secret,
            'active': True,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._webhooks[webhook_id] = webhook
        logger.info("웹훅 등록: %s -> %s", webhook_id, url)
        return webhook

    def get_webhook(self, webhook_id: str) -> Optional[dict]:
        return self._webhooks.get(webhook_id)

    def update_webhook(self, webhook_id: str, **kwargs) -> dict:
        webhook = self._webhooks.get(webhook_id)
        if webhook is None:
            raise KeyError(f"웹훅 없음: {webhook_id}")
        for key in ('url', 'events', 'secret', 'active'):
            if key in kwargs:
                webhook[key] = kwargs[key]
        return webhook

    def delete_webhook(self, webhook_id: str) -> bool:
        if webhook_id not in self._webhooks:
            return False
        del self._webhooks[webhook_id]
        return True

    def list_webhooks(self) -> List[dict]:
        return list(self._webhooks.values())
