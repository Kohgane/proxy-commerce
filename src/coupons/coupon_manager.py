"""src/coupons/coupon_manager.py — Phase 38: 쿠폰 CRUD + 유효성 검증."""
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

COUPON_TYPES = {'percentage', 'fixed_amount', 'free_shipping'}


class CouponManager:
    """쿠폰 관리자.

    타입: percentage (%), fixed_amount (원), free_shipping
    """

    def __init__(self):
        self._coupons: Dict[str, dict] = {}

    def create(self, data: dict) -> dict:
        """쿠폰 생성."""
        coupon_id = data.get('id') or str(uuid.uuid4())[:8]
        coupon_type = data.get('type', 'percentage')
        if coupon_type not in COUPON_TYPES:
            raise ValueError(f"지원하지 않는 쿠폰 타입: {coupon_type}")
        coupon = {
            'id': coupon_id,
            'code': data.get('code', '').upper(),
            'type': coupon_type,
            'value': str(Decimal(str(data.get('value', 0)))),
            'min_order_amount': str(Decimal(str(data.get('min_order_amount', 0)))),
            'max_discount': str(Decimal(str(data.get('max_discount', 0)))),
            'usage_limit': int(data.get('usage_limit', 0)),
            'used_count': 0,
            'active': bool(data.get('active', True)),
            'valid_from': data.get('valid_from', ''),
            'valid_until': data.get('valid_until', ''),
            'applicable_categories': data.get('applicable_categories', []),
            'first_purchase_only': bool(data.get('first_purchase_only', False)),
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        self._coupons[coupon_id] = coupon
        if coupon['code']:
            # 코드 인덱스용 조회 쉽게 하기 위해 id로만 저장, 코드 조회는 별도
            pass
        logger.info("쿠폰 생성: %s (code=%s)", coupon_id, coupon['code'])
        return coupon

    def get(self, coupon_id: str) -> Optional[dict]:
        return self._coupons.get(coupon_id)

    def get_by_code(self, code: str) -> Optional[dict]:
        """코드로 쿠폰 조회."""
        code_upper = code.upper()
        for coupon in self._coupons.values():
            if coupon['code'] == code_upper:
                return coupon
        return None

    def list_all(self, active_only: bool = False) -> List[dict]:
        items = list(self._coupons.values())
        if active_only:
            items = [c for c in items if c['active']]
        return items

    def update(self, coupon_id: str, data: dict) -> Optional[dict]:
        """쿠폰 업데이트."""
        coupon = self._coupons.get(coupon_id)
        if not coupon:
            return None
        for field in ('value', 'min_order_amount', 'max_discount', 'usage_limit',
                      'active', 'valid_from', 'valid_until', 'applicable_categories',
                      'first_purchase_only'):
            if field in data:
                coupon[field] = data[field]
        return coupon

    def deactivate(self, coupon_id: str) -> bool:
        """쿠폰 비활성화."""
        coupon = self._coupons.get(coupon_id)
        if not coupon:
            return False
        coupon['active'] = False
        return True

    def validate(self, code: str, order_amount: Decimal = Decimal('0')) -> dict:
        """쿠폰 유효성 검증.

        Returns:
            {'valid': bool, 'coupon': dict|None, 'reason': str}
        """
        coupon = self.get_by_code(code)
        if not coupon:
            return {'valid': False, 'coupon': None, 'reason': '존재하지 않는 쿠폰 코드'}
        if not coupon['active']:
            return {'valid': False, 'coupon': coupon, 'reason': '비활성화된 쿠폰'}
        if coupon['usage_limit'] > 0 and coupon['used_count'] >= coupon['usage_limit']:
            return {'valid': False, 'coupon': coupon, 'reason': '사용 한도 초과'}
        min_amt = Decimal(coupon['min_order_amount'])
        if order_amount < min_amt:
            return {'valid': False, 'coupon': coupon, 'reason': f'최소 주문 금액 {min_amt}원 미만'}
        now = datetime.now(timezone.utc).isoformat()
        if coupon['valid_from'] and coupon['valid_from'] > now:
            return {'valid': False, 'coupon': coupon, 'reason': '유효 기간 시작 전'}
        if coupon['valid_until'] and coupon['valid_until'] < now:
            return {'valid': False, 'coupon': coupon, 'reason': '유효 기간 만료'}
        return {'valid': True, 'coupon': coupon, 'reason': '유효한 쿠폰'}

    def increment_usage(self, coupon_id: str) -> None:
        """사용 횟수 증가."""
        coupon = self._coupons.get(coupon_id)
        if coupon:
            coupon['used_count'] += 1
