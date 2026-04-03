"""src/webhook_manager/delivery_log.py — 전달 로그."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class DeliveryLog:
    """웹훅 전달 기록."""

    def __init__(self):
        self._deliveries: Dict[str, dict] = {}

    def log_delivery(
        self,
        webhook_id: str,
        event: str,
        status_code: int,
        response: str,
        attempt: int = 1,
    ) -> dict:
        delivery_id = str(uuid.uuid4())[:8]
        record = {
            'id': delivery_id,
            'webhook_id': webhook_id,
            'event': event,
            'status_code': status_code,
            'response': response,
            'attempt': attempt,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'success': 200 <= status_code < 300,
        }
        self._deliveries[delivery_id] = record
        return record

    def get_deliveries(self, webhook_id: str) -> List[dict]:
        return [d for d in self._deliveries.values() if d['webhook_id'] == webhook_id]

    def get_delivery(self, delivery_id: str) -> Optional[dict]:
        return self._deliveries.get(delivery_id)
