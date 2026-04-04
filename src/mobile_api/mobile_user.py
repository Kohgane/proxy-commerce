"""src/mobile_api/mobile_user.py — 모바일 사용자 서비스."""
from __future__ import annotations

import time
import uuid
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MobileUserService:
    """모바일 사용자 프로필/주소/위시리스트/알림 서비스."""

    def __init__(self):
        self._profiles: dict[str, dict] = {}
        self._addresses: dict[str, list[dict]] = {}
        self._wishlists: dict[str, list[dict]] = {}
        self._notification_settings: dict[str, dict] = {}

    def _get_profile(self, user_id: str) -> dict:
        if user_id not in self._profiles:
            self._profiles[user_id] = {
                'user_id': user_id,
                'name': '',
                'email': '',
                'phone': '',
                'avatar_url': '',
                'grade': 'bronze',
                'points': 0,
                'created_at': time.time(),
            }
        return self._profiles[user_id]

    def get_profile(self, user_id: str) -> dict:
        return self._get_profile(user_id)

    def update_profile(self, user_id: str, **kwargs) -> dict:
        profile = self._get_profile(user_id)
        allowed = {'name', 'email', 'phone', 'avatar_url'}
        for k, v in kwargs.items():
            if k in allowed:
                profile[k] = v
        return profile

    def list_addresses(self, user_id: str) -> list[dict]:
        return self._addresses.get(user_id, [])

    def add_address(self, user_id: str, address_data: dict) -> dict:
        addr = dict(address_data)
        addr['address_id'] = str(uuid.uuid4())
        addr['created_at'] = time.time()
        addr.setdefault('is_default', False)
        addresses = self._addresses.setdefault(user_id, [])
        if not addresses:
            addr['is_default'] = True
        addresses.append(addr)
        return addr

    def set_default_address(self, user_id: str, address_id: str) -> bool:
        addresses = self._addresses.get(user_id, [])
        found = False
        for addr in addresses:
            if addr['address_id'] == address_id:
                addr['is_default'] = True
                found = True
            else:
                addr['is_default'] = False
        return found

    def delete_address(self, user_id: str, address_id: str) -> bool:
        addresses = self._addresses.get(user_id, [])
        for addr in addresses:
            if addr['address_id'] == address_id:
                addresses.remove(addr)
                return True
        return False

    def get_wishlist(self, user_id: str) -> list[dict]:
        return list(self._wishlists.get(user_id, []))

    def add_to_wishlist(self, user_id: str, sku: str) -> bool:
        wl = self._wishlists.setdefault(user_id, [])
        if not any(item['sku'] == sku for item in wl):
            wl.append({'sku': sku, 'added_at': time.time()})
        return True

    def remove_from_wishlist(self, user_id: str, sku: str) -> bool:
        wl = self._wishlists.get(user_id, [])
        for i, item in enumerate(wl):
            if item['sku'] == sku:
                del wl[i]
                return True
        return False

    def get_notification_settings(self, user_id: str) -> dict:
        if user_id not in self._notification_settings:
            self._notification_settings[user_id] = {
                'push': True, 'email': True, 'telegram': False,
            }
        return self._notification_settings[user_id]

    def update_notification_settings(self, user_id: str, **kwargs) -> dict:
        settings = self.get_notification_settings(user_id)
        allowed = {'push', 'email', 'telegram'}
        for k, v in kwargs.items():
            if k in allowed:
                settings[k] = bool(v)
        return settings

    def get_order_history(self, user_id: str) -> list[dict]:
        try:
            from .mobile_order import MobileOrderService
            svc = MobileOrderService()
            result = svc.list_orders(user_id)
            return result.get('items', [])
        except Exception as exc:
            logger.debug("order history error: %s", exc)
            return []

    def get_points(self, user_id: str) -> dict:
        profile = self._get_profile(user_id)
        return {
            'balance': profile.get('points', 0),
            'grade': profile.get('grade', 'bronze'),
            'history': [],
        }
