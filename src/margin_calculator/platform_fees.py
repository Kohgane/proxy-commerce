"""src/margin_calculator/platform_fees.py — 플랫폼 수수료 계산기 (Phase 110).

PlatformFeeCalculator: 쿠팡/네이버/자체몰 수수료 자동 계산
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── 쿠팡 카테고리별 수수료율 (%) ──────────────────────────────────────────────
COUPANG_CATEGORY_FEES: Dict[str, float] = {
    'fashion': 10.8,
    'clothing': 10.8,
    'electronics': 8.0,
    'food': 6.5,
    'beauty': 9.5,
    'home': 9.0,
    'sports': 9.0,
    'baby': 8.5,
    'books': 10.0,
    'toys': 10.0,
    'automotive': 7.5,
    'health': 9.0,
    'default': 9.0,
}
COUPANG_ROCKET_FEE_RATE: float = 2.0   # 로켓배송 추가 수수료 (%)

# ── 네이버 수수료율 (%) ───────────────────────────────────────────────────────
NAVER_BASE_FEE_RATE: float = 2.0        # 기본 판매 수수료
NAVER_SALES_LINKED_FEE_RATE: float = 2.0  # 매출연동 수수료
NAVER_PAYMENT_FEE_RATE: float = 3.74   # 네이버페이 결제 수수료

# ── 자체몰 PG 수수료율 (%) ────────────────────────────────────────────────────
INTERNAL_PG_FEES: Dict[str, float] = {
    'toss': 3.2,
    'kakao': 3.3,
    'default': 3.2,
}


class PlatformFeeCalculator:
    """플랫폼별 수수료 자동 계산."""

    def __init__(self) -> None:
        self._coupang_fees: Dict[str, float] = dict(COUPANG_CATEGORY_FEES)
        self._naver_fees: Dict[str, float] = {
            'base': NAVER_BASE_FEE_RATE,
            'sales_linked': NAVER_SALES_LINKED_FEE_RATE,
            'payment': NAVER_PAYMENT_FEE_RATE,
        }
        self._internal_fees: Dict[str, float] = dict(INTERNAL_PG_FEES)

    # ── 수수료 계산 ───────────────────────────────────────────────────────────

    def get_platform_fee(
        self,
        channel: str,
        selling_price: float,
        category: Optional[str] = None,
        *,
        rocket_delivery: bool = False,
        pg_method: str = 'default',
    ) -> float:
        """채널별 수수료 금액 반환."""
        channel = channel.lower()
        if channel == 'coupang':
            return self._calc_coupang_fee(selling_price, category, rocket_delivery)
        if channel == 'naver':
            return self._calc_naver_fee(selling_price)
        if channel == 'internal':
            return self._calc_internal_fee(selling_price, pg_method)
        logger.warning("알 수 없는 채널: %s", channel)
        return 0.0

    def get_platform_fee_rate(
        self,
        channel: str,
        category: Optional[str] = None,
        *,
        rocket_delivery: bool = False,
        pg_method: str = 'default',
    ) -> float:
        """채널별 총 수수료율 (%) 반환."""
        channel = channel.lower()
        if channel == 'coupang':
            rate = self._coupang_fees.get(category or 'default', self._coupang_fees['default'])
            if rocket_delivery:
                rate += COUPANG_ROCKET_FEE_RATE
            return rate
        if channel == 'naver':
            return (
                self._naver_fees['base']
                + self._naver_fees['sales_linked']
                + self._naver_fees['payment']
            )
        if channel == 'internal':
            return self._internal_fees.get(pg_method, self._internal_fees['default'])
        return 0.0

    def get_fee_structure(self, channel: str) -> Dict[str, Any]:
        """채널별 수수료 구조 설명."""
        channel = channel.lower()
        if channel == 'coupang':
            return {
                'channel': 'coupang',
                'type': '카테고리별 수수료',
                'categories': dict(self._coupang_fees),
                'rocket_delivery_extra': COUPANG_ROCKET_FEE_RATE,
                'description': '카테고리별 차등 수수료 + 로켓배송 추가 수수료',
            }
        if channel == 'naver':
            return {
                'channel': 'naver',
                'type': '복합 수수료',
                'base_fee': self._naver_fees['base'],
                'sales_linked_fee': self._naver_fees['sales_linked'],
                'payment_fee': self._naver_fees['payment'],
                'total': sum(self._naver_fees.values()),
                'description': '기본 수수료 + 매출연동 수수료 + 네이버페이 결제 수수료',
            }
        if channel == 'internal':
            return {
                'channel': 'internal',
                'type': 'PG 수수료만',
                'pg_methods': dict(self._internal_fees),
                'description': '자체몰 — PG 수수료만 부과 (토스/카카오페이)',
            }
        return {'channel': channel, 'error': '알 수 없는 채널'}

    def get_all_fee_structures(self) -> Dict[str, Dict[str, Any]]:
        """전체 채널 수수료 구조."""
        return {
            ch: self.get_fee_structure(ch)
            for ch in ('coupang', 'naver', 'internal')
        }

    # ── 수수료율 관리 ─────────────────────────────────────────────────────────

    def update_coupang_category_fee(self, category: str, rate: float) -> None:
        """쿠팡 카테고리 수수료율 수정."""
        self._coupang_fees[category] = rate

    def update_naver_fee(self, fee_type: str, rate: float) -> None:
        """네이버 수수료율 수정."""
        if fee_type in self._naver_fees:
            self._naver_fees[fee_type] = rate

    def update_internal_pg_fee(self, pg_method: str, rate: float) -> None:
        """자체몰 PG 수수료율 수정."""
        self._internal_fees[pg_method] = rate

    # ── 내부 계산 ─────────────────────────────────────────────────────────────

    def _calc_coupang_fee(
        self,
        selling_price: float,
        category: Optional[str],
        rocket_delivery: bool,
    ) -> float:
        rate = self._coupang_fees.get(category or 'default', self._coupang_fees['default'])
        if rocket_delivery:
            rate += COUPANG_ROCKET_FEE_RATE
        return selling_price * rate / 100.0

    def _calc_naver_fee(self, selling_price: float) -> float:
        total_rate = sum(self._naver_fees.values())
        return selling_price * total_rate / 100.0

    def _calc_internal_fee(self, selling_price: float, pg_method: str) -> float:
        rate = self._internal_fees.get(pg_method, self._internal_fees['default'])
        return selling_price * rate / 100.0
