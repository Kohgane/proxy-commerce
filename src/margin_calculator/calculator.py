"""src/margin_calculator/calculator.py — 실시간 마진 계산 엔진 (Phase 110).

RealTimeMarginCalculator: 상품별 실시간 마진 계산
MarginResult: 마진 계산 결과 dataclass
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .margin_config import MarginConfig
from .platform_fees import PlatformFeeCalculator

logger = logging.getLogger(__name__)

# 캐시 TTL (초)
CACHE_TTL_SECONDS = 300  # 5분


@dataclass
class MarginResult:
    """마진 계산 결과."""
    product_id: str
    channel: str
    # 가격
    selling_price: float
    source_cost: float          # 원가 (외화)
    source_cost_krw: float      # 원가 (원화)
    currency: str               # 원가 통화
    exchange_rate: float        # 환율
    # 비용
    international_shipping: float
    customs_duty: float
    vat: float
    domestic_shipping: float
    platform_fee: float
    payment_fee: float
    exchange_loss: float
    packaging_cost: float
    labeling_cost: float
    return_reserve: float
    misc_costs: float
    # 결과
    total_cost: float
    net_profit: float
    margin_rate: float          # 마진율 (%)
    calculated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'result_id': self.result_id,
            'product_id': self.product_id,
            'channel': self.channel,
            'selling_price': self.selling_price,
            'source_cost': self.source_cost,
            'source_cost_krw': self.source_cost_krw,
            'currency': self.currency,
            'exchange_rate': self.exchange_rate,
            'international_shipping': self.international_shipping,
            'customs_duty': self.customs_duty,
            'vat': self.vat,
            'domestic_shipping': self.domestic_shipping,
            'platform_fee': self.platform_fee,
            'payment_fee': self.payment_fee,
            'exchange_loss': self.exchange_loss,
            'packaging_cost': self.packaging_cost,
            'labeling_cost': self.labeling_cost,
            'return_reserve': self.return_reserve,
            'misc_costs': self.misc_costs,
            'total_cost': self.total_cost,
            'net_profit': self.net_profit,
            'margin_rate': self.margin_rate,
            'calculated_at': self.calculated_at,
        }


@dataclass
class _CacheEntry:
    result: MarginResult
    cached_at: float  # time.time()


class RealTimeMarginCalculator:
    """상품별 실시간 마진 계산 엔진."""

    def __init__(
        self,
        config: Optional[MarginConfig] = None,
        fee_calculator: Optional[PlatformFeeCalculator] = None,
    ) -> None:
        self._config = config or MarginConfig()
        self._fee_calc = fee_calculator or PlatformFeeCalculator()
        # 상품 데이터 저장소 (인메모리)
        self._products: Dict[str, Dict[str, Any]] = {}
        # 캐시: {(product_id, channel): _CacheEntry}
        self._cache: Dict[tuple, _CacheEntry] = {}
        # 계산 이력 (시계열)
        self._history: List[MarginResult] = []

    # ── 상품 등록/조회 ────────────────────────────────────────────────────────

    def register_product(self, product_id: str, product_data: Dict[str, Any]) -> None:
        """상품 데이터 등록."""
        self._products[product_id] = dict(product_data)
        self._invalidate_cache(product_id)

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        """상품 데이터 조회."""
        return self._products.get(product_id)

    def update_product(self, product_id: str, updates: Dict[str, Any]) -> None:
        """상품 데이터 업데이트 + 캐시 무효화."""
        if product_id in self._products:
            self._products[product_id].update(updates)
        else:
            self._products[product_id] = dict(updates)
        self._invalidate_cache(product_id)

    # ── 마진 계산 ─────────────────────────────────────────────────────────────

    def calculate_margin(
        self,
        product_id: str,
        channel: str = 'internal',
        *,
        use_cache: bool = True,
        product_data: Optional[Dict[str, Any]] = None,
    ) -> MarginResult:
        """단일 상품 마진 계산."""
        import time

        cache_key = (product_id, channel)

        if use_cache and cache_key in self._cache:
            entry = self._cache[cache_key]
            if time.time() - entry.cached_at < CACHE_TTL_SECONDS:
                return entry.result

        data = product_data or self._products.get(product_id, {})
        result = self._compute(product_id, channel, data)

        if use_cache:
            self._cache[cache_key] = _CacheEntry(result=result, cached_at=time.time())

        self._history.append(result)
        if len(self._history) > 10000:
            self._history = self._history[-10000:]

        return result

    def calculate_bulk_margins(
        self,
        product_ids: Optional[List[str]] = None,
        channel: str = 'internal',
    ) -> List[MarginResult]:
        """일괄 마진 계산."""
        ids = product_ids if product_ids is not None else list(self._products.keys())
        results = []
        for pid in ids:
            try:
                results.append(self.calculate_margin(pid, channel))
            except Exception as exc:
                logger.error("마진 계산 오류 [%s]: %s", pid, exc)
        return results

    def recalculate_all(self, channel: Optional[str] = None) -> Dict[str, Any]:
        """전체 상품 마진 재계산 (캐시 무효화 후)."""
        self._cache.clear()
        channels = [channel] if channel else ['coupang', 'naver', 'internal']
        total = 0
        errors = 0
        for ch in channels:
            for pid in list(self._products.keys()):
                try:
                    self.calculate_margin(pid, ch, use_cache=False)
                    total += 1
                except Exception as exc:
                    logger.error("재계산 오류 [%s][%s]: %s", pid, ch, exc)
                    errors += 1
        return {'total': total, 'errors': errors, 'channels': channels}

    # ── 이력 조회 ─────────────────────────────────────────────────────────────

    def get_history(
        self,
        product_id: Optional[str] = None,
        channel: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """마진 계산 이력 조회."""
        items = self._history
        if product_id:
            items = [h for h in items if h.product_id == product_id]
        if channel:
            items = [h for h in items if h.channel == channel]
        return [h.to_dict() for h in items[-limit:]]

    # ── 캐시 관리 ─────────────────────────────────────────────────────────────

    def invalidate_cache(self, product_id: Optional[str] = None) -> None:
        """캐시 무효화 (공개 인터페이스)."""
        self._invalidate_cache(product_id)

    def _invalidate_cache(self, product_id: Optional[str] = None) -> None:
        if product_id is None:
            self._cache.clear()
        else:
            keys_to_del = [k for k in self._cache if k[0] == product_id]
            for k in keys_to_del:
                del self._cache[k]

    # ── 마진 계산 핵심 로직 ───────────────────────────────────────────────────

    def _compute(
        self,
        product_id: str,
        channel: str,
        data: Dict[str, Any],
    ) -> MarginResult:
        """마진 계산 공식 적용."""
        cfg = self._config.get_config(
            product_id=product_id,
            category=data.get('category'),
        )

        selling_price: float = float(data.get('selling_price', 0.0))
        source_cost: float = float(data.get('source_cost', 0.0))
        currency: str = data.get('currency', 'KRW')
        exchange_rate: float = float(data.get('exchange_rate', 1.0))

        # 원화 환산
        source_cost_krw = source_cost * exchange_rate

        # 환율 스프레드 손실 (원가 × 환율스프레드%)
        exchange_loss = source_cost_krw * cfg['exchange_spread_rate'] / 100.0

        # 해외 배송비
        international_shipping = float(data.get('international_shipping', 0.0))

        # 과세 가격 = 원화 원가 + 해외 배송비
        taxable_price = source_cost_krw + international_shipping

        # 관세 (과세가격 × 관세율)
        customs_duty_rate = float(data.get('customs_duty_rate', 0.0))
        customs_duty = taxable_price * customs_duty_rate / 100.0

        # 부가세 ((과세가격 + 관세) × 10%)
        vat = (taxable_price + customs_duty) * cfg['vat_rate'] / 100.0

        # 국내 배송비
        domestic_shipping = float(data.get('domestic_shipping', 0.0))

        # 플랫폼 수수료
        category = data.get('category')
        platform_fee = self._fee_calc.get_platform_fee(
            channel, selling_price, category,
            rocket_delivery=data.get('rocket_delivery', False),
        )

        # 결제 수수료 (판매가 × 결제수수료율)
        payment_fee_rate = float(data.get('payment_fee_rate', 0.0))
        payment_fee = selling_price * payment_fee_rate / 100.0

        # 포장비 / 라벨링비
        packaging_cost = float(data.get('packaging_cost', cfg['default_packaging_cost']))
        labeling_cost = float(data.get('labeling_cost', cfg['default_labeling_cost']))

        # 반품 충당금 (판매가 × 예상반품률)
        return_reserve_rate = float(data.get('return_reserve_rate', cfg['return_reserve_rate']))
        return_reserve = selling_price * return_reserve_rate / 100.0

        # 기타 비용
        misc_costs = float(data.get('misc_costs', 0.0))

        # 총 비용
        total_cost = (
            source_cost_krw
            + international_shipping
            + customs_duty
            + vat
            + domestic_shipping
            + platform_fee
            + payment_fee
            + exchange_loss
            + packaging_cost
            + labeling_cost
            + return_reserve
            + misc_costs
        )

        net_profit = selling_price - total_cost
        margin_rate = (net_profit / selling_price * 100.0) if selling_price > 0 else 0.0

        return MarginResult(
            product_id=product_id,
            channel=channel,
            selling_price=selling_price,
            source_cost=source_cost,
            source_cost_krw=source_cost_krw,
            currency=currency,
            exchange_rate=exchange_rate,
            international_shipping=international_shipping,
            customs_duty=customs_duty,
            vat=vat,
            domestic_shipping=domestic_shipping,
            platform_fee=platform_fee,
            payment_fee=payment_fee,
            exchange_loss=exchange_loss,
            packaging_cost=packaging_cost,
            labeling_cost=labeling_cost,
            return_reserve=return_reserve,
            misc_costs=misc_costs,
            total_cost=total_cost,
            net_profit=net_profit,
            margin_rate=round(margin_rate, 4),
        )
