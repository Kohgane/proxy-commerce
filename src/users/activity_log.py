"""src/users/activity_log.py — Phase 47: 사용자 활동 로그."""
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

ACTIVITY_TYPES = {'login', 'product_view', 'order', 'search', 'other'}
DEFAULT_MAX_RECORDS = 100


class ActivityLog:
    """사용자 활동 기록 (로그인, 상품 조회, 주문, 검색), 최근 N건 조회."""

    def __init__(self, max_records: int = DEFAULT_MAX_RECORDS):
        self._max_records = max_records
        # user_id → deque of activity records
        self._logs: Dict[str, Deque[dict]] = {}

    def log(self, user_id: str, activity_type: str, detail: Optional[dict] = None) -> dict:
        """활동 기록."""
        if activity_type not in ACTIVITY_TYPES:
            activity_type = 'other'
        record = {
            'user_id': user_id,
            'activity_type': activity_type,
            'detail': detail or {},
            'recorded_at': datetime.now(timezone.utc).isoformat(),
        }
        user_log = self._logs.setdefault(user_id, deque(maxlen=self._max_records))
        user_log.append(record)
        return record

    def get_recent(self, user_id: str, n: int = 10) -> List[dict]:
        """최근 N건 활동 조회."""
        user_log = self._logs.get(user_id, deque())
        records = list(user_log)
        return records[-n:]

    def get_by_type(self, user_id: str, activity_type: str) -> List[dict]:
        user_log = self._logs.get(user_id, deque())
        return [r for r in user_log if r['activity_type'] == activity_type]

    def get_all(self, user_id: str) -> List[dict]:
        return list(self._logs.get(user_id, deque()))
