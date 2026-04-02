"""src/users/address_book.py — Phase 47: 배송지 주소록 관리."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_ADDRESSES_PER_USER = 5
REQUIRED_ADDRESS_FIELDS = ('recipient_name', 'phone', 'address1', 'city', 'postal_code', 'country')


class AddressBook:
    """배송지 CRUD (최대 5개), 기본 배송지 설정, 주소 유효성 검증."""

    def __init__(self):
        self._addresses: Dict[str, dict] = {}
        self._default: Dict[str, str] = {}   # user_id → address_id

    def add(self, user_id: str, data: dict) -> dict:
        """배송지 추가."""
        missing = [f for f in REQUIRED_ADDRESS_FIELDS if not data.get(f)]
        if missing:
            raise ValueError(f"필수 필드 누락: {missing}")
        user_addresses = [a for a in self._addresses.values() if a['user_id'] == user_id]
        if len(user_addresses) >= MAX_ADDRESSES_PER_USER:
            raise ValueError(f"배송지 최대 개수 초과: {MAX_ADDRESSES_PER_USER}")
        addr_id = str(uuid.uuid4())[:8]
        address = {
            'id': addr_id,
            'user_id': user_id,
            'recipient_name': data['recipient_name'],
            'phone': data['phone'],
            'address1': data['address1'],
            'address2': data.get('address2', ''),
            'city': data['city'],
            'postal_code': data['postal_code'],
            'country': data['country'],
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._addresses[addr_id] = address
        if not self._default.get(user_id):
            self._default[user_id] = addr_id
        return address

    def get(self, address_id: str) -> Optional[dict]:
        return self._addresses.get(address_id)

    def list_by_user(self, user_id: str) -> List[dict]:
        return [a for a in self._addresses.values() if a['user_id'] == user_id]

    def update(self, address_id: str, data: dict) -> dict:
        address = self._addresses.get(address_id)
        if address is None:
            raise KeyError(f"배송지 없음: {address_id}")
        for key in ('recipient_name', 'phone', 'address1', 'address2',
                    'city', 'postal_code', 'country'):
            if key in data:
                address[key] = data[key]
        return address

    def delete(self, address_id: str) -> bool:
        if address_id not in self._addresses:
            return False
        user_id = self._addresses[address_id]['user_id']
        del self._addresses[address_id]
        # 기본 배송지가 삭제된 경우 재설정
        if self._default.get(user_id) == address_id:
            remaining = self.list_by_user(user_id)
            self._default[user_id] = remaining[0]['id'] if remaining else None
        return True

    def set_default(self, user_id: str, address_id: str):
        """기본 배송지 설정."""
        address = self._addresses.get(address_id)
        if address is None or address['user_id'] != user_id:
            raise ValueError(f"배송지 없음 또는 사용자 불일치: {address_id}")
        self._default[user_id] = address_id

    def get_default(self, user_id: str) -> Optional[dict]:
        addr_id = self._default.get(user_id)
        if addr_id is None:
            return None
        return self._addresses.get(addr_id)
