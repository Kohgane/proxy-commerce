"""src/order_matching/fulfillment_checker.py — 이행 가능성 즉시 확인 (Phase 112).

FulfillmentChecker: 소싱처 기준 재고/가격/배송/마진 확인 → 이행 불가 대응
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 이행 불가 사유
REASON_OUT_OF_STOCK = 'out_of_stock'
REASON_PRICE_EXCEEDED = 'price_exceeded'
REASON_SOURCE_INACTIVE = 'source_inactive'
REASON_SHIPPING_UNAVAILABLE = 'shipping_unavailable'
REASON_MARGIN_BELOW_THRESHOLD = 'margin_below_threshold'
REASON_SOURCE_UNRELIABLE = 'source_unreliable'

# 기본 임계값
DEFAULT_MIN_MARGIN_RATE = 0.05  # 최소 마진율 5%
DEFAULT_MAX_PRICE_CHANGE_RATE = 0.20  # 최대 가격 변동률 20%
DEFAULT_MIN_RELIABILITY = 0.5  # 최소 신뢰도


@dataclass
class FulfillmentCheckResult:
    check_id: str
    order_id: str
    product_id: str
    source_id: str
    is_available: bool
    stock_available: bool
    price_valid: bool
    shipping_possible: bool
    estimated_total_cost: float
    estimated_margin: float
    estimated_delivery_days: int
    issues: List[str]
    checked_at: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class FulfillmentChecker:
    """이행 가능성 즉시 확인기."""

    def __init__(
        self,
        min_margin_rate: float = DEFAULT_MIN_MARGIN_RATE,
        max_price_change_rate: float = DEFAULT_MAX_PRICE_CHANGE_RATE,
        min_reliability: float = DEFAULT_MIN_RELIABILITY,
    ) -> None:
        self._min_margin_rate = min_margin_rate
        self._max_price_change_rate = max_price_change_rate
        self._min_reliability = min_reliability
        # source_id → source data dict
        self._sources: Dict[str, dict] = {}
        # order_id → list of product dicts {product_id, quantity, selling_price}
        self._orders: Dict[str, List[dict]] = {}
        # check_id → FulfillmentCheckResult
        self._checks: Dict[str, FulfillmentCheckResult] = {}
        # 이행 불가 대응 이력
        self._unfulfillable_actions: List[dict] = []
        # 생성된 알림 목록
        self._notifications: List[dict] = []

    # ── 등록 ──────────────────────────────────────────────────────────────────

    def register_source(self, source_id: str, source_data: dict) -> None:
        """소싱처 등록."""
        self._sources[source_id] = dict(source_data)

    def register_order(self, order_id: str, items: List[dict]) -> None:
        """주문 등록."""
        self._orders[order_id] = items

    # ── 이행 확인 ─────────────────────────────────────────────────────────────

    def check_fulfillment(
        self, order_id: str, source_id: Optional[str] = None
    ) -> List[FulfillmentCheckResult]:
        """주문 전체 이행 가능성 확인."""
        items = self._orders.get(order_id, [])
        if not items:
            items = [{'product_id': order_id, 'quantity': 1, 'selling_price': 0.0}]

        results = []
        for item in items:
            product_id = item.get('product_id', '')
            quantity = int(item.get('quantity', 1))
            selling_price = float(item.get('selling_price', 0.0))
            sid = source_id or item.get('source_id', '')
            result = self.check_product_fulfillment(
                product_id, quantity, sid, selling_price=selling_price, order_id=order_id
            )
            results.append(result)
        return results

    def check_product_fulfillment(
        self,
        product_id: str,
        quantity: int,
        source_id: Optional[str] = None,
        selling_price: float = 0.0,
        order_id: str = '',
    ) -> FulfillmentCheckResult:
        """단일 상품 이행 확인."""
        issues: List[str] = []
        source = self._sources.get(source_id or '', {}) if source_id else {}

        # 소싱처 비활성 확인
        is_active = source.get('active', True) if source else True
        if not is_active:
            issues.append(REASON_SOURCE_INACTIVE)

        # 재고 확인
        stock = source.get('stock', 999) if source else 999
        stock_available = stock >= quantity
        if not stock_available:
            issues.append(REASON_OUT_OF_STOCK)

        # 배송 가능 확인
        shipping_possible = source.get('shipping_available', True) if source else True
        if not shipping_possible:
            issues.append(REASON_SHIPPING_UNAVAILABLE)

        # 신뢰도 확인
        reliability = source.get('reliability', 1.0) if source else 1.0
        if reliability < self._min_reliability:
            issues.append(REASON_SOURCE_UNRELIABLE)

        # 가격 유효성 확인 (변동률)
        source_price = float(source.get('price', 0.0)) if source else 0.0
        last_price = float(source.get('last_price', source_price)) if source else source_price
        price_valid = True
        if last_price > 0 and source_price > 0:
            change_rate = abs(source_price - last_price) / last_price
            if change_rate > self._max_price_change_rate:
                price_valid = False
                issues.append(REASON_PRICE_EXCEEDED)

        # 마진 확인
        estimated_total_cost = source_price * quantity if source_price > 0 else 0.0
        estimated_margin = 0.0
        if selling_price > 0 and estimated_total_cost > 0:
            estimated_margin = selling_price - estimated_total_cost
            margin_rate = estimated_margin / selling_price
            if margin_rate < self._min_margin_rate:
                issues.append(REASON_MARGIN_BELOW_THRESHOLD)

        is_available = len(issues) == 0
        estimated_delivery_days = int(source.get('shipping_days', 3)) if source else 3

        result = FulfillmentCheckResult(
            check_id=str(uuid.uuid4()),
            order_id=order_id,
            product_id=product_id,
            source_id=source_id or '',
            is_available=is_available,
            stock_available=stock_available,
            price_valid=price_valid,
            shipping_possible=shipping_possible,
            estimated_total_cost=estimated_total_cost,
            estimated_margin=estimated_margin,
            estimated_delivery_days=estimated_delivery_days,
            issues=issues,
            checked_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        self._checks[result.check_id] = result
        logger.info(
            "이행 확인: product=%s, source=%s, available=%s, issues=%s",
            product_id, source_id, is_available, issues,
        )
        return result

    # ── 이행 불가 대응 ─────────────────────────────────────────────────────────

    def handle_unfulfillable(
        self, order_id: str, product_id: str, reason: str
    ) -> dict:
        """이행 불가 시 대응: 대안 소싱처 검색 → 없으면 알림 + 채널 중지."""
        # Phase 108 AlternativeSourceFinder mock
        alt_source = self._find_alternative_source(product_id, reason)

        action: dict = {
            'action_id': str(uuid.uuid4()),
            'order_id': order_id,
            'product_id': product_id,
            'reason': reason,
            'alternative_found': alt_source is not None,
            'alternative_source': alt_source,
            'acted_at': datetime.now(tz=timezone.utc).isoformat(),
        }

        if alt_source:
            action['action_taken'] = 'switched_to_alternative'
            logger.info(
                "대안 소싱처 전환: product=%s → %s", product_id, alt_source
            )
        else:
            # 고객 알림 생성
            notification = self._create_notification(order_id, product_id, reason)
            self._notifications.append(notification)
            # Phase 109 ChannelSyncEngine mock: 판매채널 상품 일시중지
            self._pause_channel_listing(product_id)
            action['action_taken'] = 'notified_and_paused'
            action['notification_id'] = notification['notification_id']
            logger.warning(
                "이행 불가 대응: product=%s, 알림 생성 + 채널 중지", product_id
            )

        self._unfulfillable_actions.append(action)
        return action

    def get_unfulfillable_actions(self) -> List[dict]:
        """이행 불가 대응 이력."""
        return list(self._unfulfillable_actions)

    def get_notifications(self) -> List[dict]:
        """생성된 알림 목록."""
        return list(self._notifications)

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _find_alternative_source(self, product_id: str, reason: str) -> Optional[str]:
        """대안 소싱처 검색 (Phase 108 AlternativeSourceFinder mock)."""
        # 등록된 소싱처 중 활성 상태이고 재고 있는 것 검색
        for source_id, source in self._sources.items():
            if (
                source.get('product_id') == product_id
                and source.get('active', True)
                and source.get('stock', 0) > 0
                and source.get('shipping_available', True)
            ):
                return source_id
        return None

    def _create_notification(self, order_id: str, product_id: str, reason: str) -> dict:
        return {
            'notification_id': str(uuid.uuid4()),
            'type': 'fulfillment_failed',
            'order_id': order_id,
            'product_id': product_id,
            'reason': reason,
            'message': f'주문 {order_id} 상품 {product_id} 이행 불가: {reason}',
            'created_at': datetime.now(tz=timezone.utc).isoformat(),
        }

    def _pause_channel_listing(self, product_id: str) -> None:
        """Phase 109 ChannelSyncEngine mock: 판매채널 상품 일시중지."""
        logger.info("판매채널 상품 일시중지 (mock): product_id=%s", product_id)
