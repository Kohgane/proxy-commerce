"""src/users/preferences.py — Phase 47: 사용자 설정."""
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {'ko', 'en', 'ja', 'zh'}
NOTIFICATION_CHANNELS = {'telegram', 'email', 'sms'}


class UserPreferences:
    """선호 언어, 선호 통화, 알림 채널 설정."""

    def __init__(self):
        self._prefs: Dict[str, dict] = {}

    def get(self, user_id: str) -> dict:
        return self._prefs.get(user_id, self._defaults())

    def set_language(self, user_id: str, language: str) -> dict:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"지원하지 않는 언어: {language}. 지원: {SUPPORTED_LANGUAGES}")
        prefs = self._prefs.setdefault(user_id, self._defaults())
        prefs['language'] = language
        return prefs

    def set_currency(self, user_id: str, currency: str) -> dict:
        prefs = self._prefs.setdefault(user_id, self._defaults())
        prefs['currency'] = currency.upper()
        return prefs

    def set_notification_channels(self, user_id: str, channels: List[str]) -> dict:
        invalid = set(channels) - NOTIFICATION_CHANNELS
        if invalid:
            raise ValueError(f"지원하지 않는 알림 채널: {invalid}")
        prefs = self._prefs.setdefault(user_id, self._defaults())
        prefs['notification_channels'] = list(channels)
        return prefs

    def update(self, user_id: str, data: dict) -> dict:
        prefs = self._prefs.setdefault(user_id, self._defaults())
        if 'language' in data:
            if data['language'] not in SUPPORTED_LANGUAGES:
                raise ValueError(f"지원하지 않는 언어: {data['language']}")
            prefs['language'] = data['language']
        if 'currency' in data:
            prefs['currency'] = data['currency'].upper()
        if 'notification_channels' in data:
            invalid = set(data['notification_channels']) - NOTIFICATION_CHANNELS
            if invalid:
                raise ValueError(f"지원하지 않는 알림 채널: {invalid}")
            prefs['notification_channels'] = list(data['notification_channels'])
        return prefs

    @staticmethod
    def _defaults() -> dict:
        return {
            'language': 'ko',
            'currency': 'KRW',
            'notification_channels': ['telegram'],
        }
