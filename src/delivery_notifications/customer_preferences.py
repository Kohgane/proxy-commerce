"""고객별 알림 채널/언어/조용시간 설정 관리."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict

from .models import NotificationPreference


class CustomerPreferenceManager:
    """고객별 알림 설정 인메모리 관리자."""

    def __init__(self) -> None:
        # user_id → NotificationPreference
        self._prefs: Dict[str, NotificationPreference] = {}

    def get(self, user_id: str) -> NotificationPreference:
        """사용자 알림 설정 조회. 없으면 기본값 반환."""
        return self._prefs.get(user_id, NotificationPreference(user_id=user_id))

    def set(self, pref: NotificationPreference) -> NotificationPreference:
        """사용자 알림 설정 저장."""
        self._prefs[pref.user_id] = pref
        return pref

    def upsert(self, user_id: str, **kwargs) -> NotificationPreference:
        """설정 일부 업데이트."""
        existing = self.get(user_id)
        for k, v in kwargs.items():
            if hasattr(existing, k):
                setattr(existing, k, v)
        self._prefs[user_id] = existing
        return existing

    def is_quiet_time(self, user_id: str) -> bool:
        """현재 조용 시간 여부 확인."""
        pref = self.get(user_id)
        now_hour = datetime.now(timezone.utc).hour
        start = pref.quiet_hours_start
        end = pref.quiet_hours_end
        # 자정을 넘어가는 경우 처리 (예: 22 ~ 08)
        if start > end:
            return now_hour >= start or now_hour < end
        return start <= now_hour < end

    def all_prefs(self) -> list:
        """모든 저장된 설정 반환."""
        return list(self._prefs.values())
