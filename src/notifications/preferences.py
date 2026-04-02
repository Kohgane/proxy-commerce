"""사용자 알림 설정 관리."""

import logging

logger = logging.getLogger(__name__)


class NotificationPreference:
    """사용자별 알림 설정."""

    def __init__(self):
        self._prefs: dict = {}

    def set(self, user_id: str, event_type: str, channel: str, enabled: bool) -> None:
        """알림 설정 저장.

        Args:
            user_id: 사용자 ID
            event_type: 이벤트 유형
            channel: 채널명
            enabled: 활성화 여부
        """
        if user_id not in self._prefs:
            self._prefs[user_id] = {}
        if event_type not in self._prefs[user_id]:
            self._prefs[user_id][event_type] = {}
        self._prefs[user_id][event_type][channel] = enabled
        logger.debug("알림 설정: user=%s, event=%s, channel=%s, enabled=%s",
                     user_id, event_type, channel, enabled)

    def get(self, user_id: str, event_type: str) -> list:
        """특정 이벤트에 대해 활성화된 채널 목록 반환.

        Args:
            user_id: 사용자 ID
            event_type: 이벤트 유형

        Returns:
            활성화된 채널명 목록
        """
        user_prefs = self._prefs.get(user_id, {})
        event_prefs = user_prefs.get(event_type, {})
        return [ch for ch, enabled in event_prefs.items() if enabled]

    def get_all(self, user_id: str) -> dict:
        """사용자의 모든 알림 설정 반환."""
        return self._prefs.get(user_id, {})
