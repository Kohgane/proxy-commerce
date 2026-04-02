"""src/users/user_manager.py — Phase 47: 사용자 프로필 CRUD."""
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 등급별 누적 구매 금액 기준 (KRW)
GRADE_THRESHOLDS = {
    'bronze': Decimal('0'),
    'silver': Decimal('100000'),
    'gold': Decimal('500000'),
    'vip': Decimal('2000000'),
}

GRADE_BENEFITS = {
    'bronze': {'discount_pct': 0, 'free_shipping_threshold': 50000, 'point_rate': 1},
    'silver': {'discount_pct': 2, 'free_shipping_threshold': 30000, 'point_rate': 2},
    'gold': {'discount_pct': 5, 'free_shipping_threshold': 20000, 'point_rate': 3},
    'vip': {'discount_pct': 10, 'free_shipping_threshold': 0, 'point_rate': 5},
}


class UserManager:
    """사용자 프로필 CRUD (이름, 이메일, 전화번호, 등급)."""

    def __init__(self):
        self._users: Dict[str, dict] = {}

    def create(self, data: dict) -> dict:
        """사용자 생성."""
        user_id = data.get('id') or str(uuid.uuid4())[:8]
        if 'email' not in data or not data['email']:
            raise ValueError("이메일은 필수입니다")
        user = {
            'id': user_id,
            'name': data.get('name', ''),
            'email': data['email'],
            'phone': data.get('phone', ''),
            'grade': 'bronze',
            'total_purchase_amount': '0',
            'active': True,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._users[user_id] = user
        return user

    def get(self, user_id: str) -> Optional[dict]:
        return self._users.get(user_id)

    def get_by_email(self, email: str) -> Optional[dict]:
        for user in self._users.values():
            if user['email'] == email:
                return user
        return None

    def list_all(self, active_only: bool = False) -> List[dict]:
        users = list(self._users.values())
        if active_only:
            users = [u for u in users if u['active']]
        return users

    def update(self, user_id: str, data: dict) -> dict:
        user = self._users.get(user_id)
        if user is None:
            raise KeyError(f"사용자 없음: {user_id}")
        for key in ('name', 'phone', 'email'):
            if key in data:
                user[key] = data[key]
        return user

    def add_purchase_amount(self, user_id: str, amount: float) -> dict:
        """누적 구매 금액 추가 + 등급 자동 갱신."""
        user = self._users.get(user_id)
        if user is None:
            raise KeyError(f"사용자 없음: {user_id}")
        total = Decimal(user['total_purchase_amount']) + Decimal(str(amount))
        user['total_purchase_amount'] = str(total)
        user['grade'] = self._calculate_grade(total)
        return user

    def get_benefits(self, user_id: str) -> dict:
        user = self._users.get(user_id)
        if user is None:
            raise KeyError(f"사용자 없음: {user_id}")
        return dict(GRADE_BENEFITS.get(user['grade'], GRADE_BENEFITS['bronze']))

    def deactivate(self, user_id: str) -> bool:
        user = self._users.get(user_id)
        if user is None:
            return False
        user['active'] = False
        return True

    @staticmethod
    def _calculate_grade(total: Decimal) -> str:
        if total >= GRADE_THRESHOLDS['vip']:
            return 'vip'
        if total >= GRADE_THRESHOLDS['gold']:
            return 'gold'
        if total >= GRADE_THRESHOLDS['silver']:
            return 'silver'
        return 'bronze'
