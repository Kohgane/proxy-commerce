"""src/auto_purchase/purchase_monitor.py — 구매 상태 실시간 모니터링 (Phase 96)."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Dict, List, Optional

from .purchase_models import PurchaseMetrics, PurchaseOrder, PurchaseStatus

logger = logging.getLogger(__name__)

# 이상 감지 임계값
_PRICE_CHANGE_THRESHOLD = 0.20   # ±20%
_DELIVERY_DELAY_DAYS = 3         # 예상 대비 3일 초과 시 경고


class PriceAnomalyDetector:
    """비정상 가격 감지."""

    def __init__(self, threshold: float = _PRICE_CHANGE_THRESHOLD) -> None:
        self._threshold = threshold
        self._price_history: Dict[str, float] = {}   # product_id → last_known_price

    def record_price(self, product_id: str, price: float) -> None:
        self._price_history[product_id] = price

    def is_anomalous(self, product_id: str, current_price: float) -> Optional[str]:
        """이상 가격이면 경고 메시지를 반환한다."""
        last = self._price_history.get(product_id)
        if last is None or last == 0:
            self.record_price(product_id, current_price)
            return None
        change_rate = abs(current_price - last) / last
        if change_rate > self._threshold:
            direction = '상승' if current_price > last else '하락'
            return (
                f'가격 이상 감지: {product_id} — '
                f'{last:.2f} → {current_price:.2f} ({change_rate:.1%} {direction})'
            )
        return None


class PurchaseMonitor:
    """구매 상태 실시간 모니터링.

    - 구매 주문 추적
    - 이상 감지: 비정상 가격, 재고 급변, 배송 지연
    - 메트릭 집계
    - 알림 발송 (텔레그램/모바일 푸시)
    """

    def __init__(self) -> None:
        self._orders: Dict[str, PurchaseOrder] = {}
        self._metrics = PurchaseMetrics()
        self._price_detector = PriceAnomalyDetector()
        self._alerts: List[Dict] = []
        self._purchase_times: List[float] = []   # 구매 소요 시간 (초)

    # ── 주문 등록/업데이트 ─────────────────────────────────

    def register_order(self, order: PurchaseOrder) -> None:
        """모니터링 대상 주문을 등록한다."""
        self._orders[order.order_id] = order
        self._metrics.pending_orders += 1
        logger.debug('Monitor: order registered %s', order.order_id)

    def update_order(self, order: PurchaseOrder) -> None:
        """주문 상태를 업데이트한다."""
        self._orders[order.order_id] = order
        if order.status == PurchaseStatus.CONFIRMED:
            self._on_order_confirmed(order)
        elif order.status == PurchaseStatus.FAILED:
            self._on_order_failed(order)

    def _on_order_confirmed(self, order: PurchaseOrder) -> None:
        self._metrics.successful_orders += 1
        self._metrics.pending_orders = max(0, self._metrics.pending_orders - 1)
        self._metrics.total_spend += order.total_price
        self._metrics.recalculate()
        # 일일 통계
        today = date.today().isoformat()
        daily = self._metrics.daily_stats.setdefault(today, {'count': 0, 'spend': 0.0})
        daily['count'] += 1
        daily['spend'] += order.total_price
        # 마켓플레이스별 통계
        mp = order.source_marketplace
        mp_stats = self._metrics.marketplace_breakdown.setdefault(mp, {'count': 0, 'spend': 0.0})
        mp_stats['count'] += 1
        mp_stats['spend'] += order.total_price

    def _on_order_failed(self, order: PurchaseOrder) -> None:
        self._metrics.failed_orders += 1
        self._metrics.pending_orders = max(0, self._metrics.pending_orders - 1)
        self._metrics.recalculate()
        self._raise_alert('order_failed', f'주문 실패: {order.order_id} — {order.error_message}', order.order_id)

    # ── 이상 감지 ──────────────────────────────────────────

    def check_price_anomaly(self, product_id: str, current_price: float) -> Optional[str]:
        """가격 이상 여부를 확인한다."""
        warning = self._price_detector.is_anomalous(product_id, current_price)
        if warning:
            self._raise_alert('price_anomaly', warning, product_id)
            self._send_telegram(f'⚠️ {warning}')
        self._price_detector.record_price(product_id, current_price)
        return warning

    def check_delivery_delay(self, order_id: str, current_date: datetime = None) -> Optional[str]:
        """배송 지연 여부를 확인한다."""
        order = self._orders.get(order_id)
        if not order:
            return None
        now = current_date or datetime.now(timezone.utc)
        expected_meta = order.metadata.get('estimated_delivery')
        if not expected_meta:
            return None
        if isinstance(expected_meta, str):
            try:
                expected = datetime.fromisoformat(expected_meta)
            except ValueError:
                return None
        else:
            expected = expected_meta

        # timezone 통일
        if expected.tzinfo is None:
            from datetime import timezone as tz
            expected = expected.replace(tzinfo=tz.utc)

        delay_days = (now - expected).days
        if delay_days > _DELIVERY_DELAY_DAYS:
            msg = f'배송 지연: {order_id} — {delay_days}일 초과'
            self._raise_alert('delivery_delay', msg, order_id)
            self._send_telegram(f'📦 {msg}')
            return msg
        return None

    def _raise_alert(self, alert_type: str, message: str, ref_id: str = '') -> None:
        self._alerts.append({
            'type': alert_type,
            'message': message,
            'ref_id': ref_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })
        logger.warning('Alert [%s]: %s', alert_type, message)

    def _send_telegram(self, message: str) -> None:
        """텔레그램 알림 발송 (notifications 모듈 연동)."""
        try:
            from ..notifications.hub import NotificationHub
            hub = NotificationHub()
            hub.send('order', message)
        except Exception as exc:
            logger.debug('Telegram send skipped: %s', exc)

    # ── 메트릭/조회 ────────────────────────────────────────

    def get_metrics(self) -> Dict:
        """대시보드 메트릭을 반환한다."""
        self._metrics.recalculate()
        return {
            'total_orders': self._metrics.total_orders,
            'successful_orders': self._metrics.successful_orders,
            'failed_orders': self._metrics.failed_orders,
            'pending_orders': self._metrics.pending_orders,
            'success_rate': round(self._metrics.success_rate, 4),
            'avg_purchase_time_seconds': round(self._metrics.avg_purchase_time_seconds, 2),
            'total_spend': round(self._metrics.total_spend, 2),
            'currency': self._metrics.currency,
            'daily_stats': self._metrics.daily_stats,
            'marketplace_breakdown': self._metrics.marketplace_breakdown,
        }

    def get_alerts(self, limit: int = 50) -> List[Dict]:
        """최근 알림 목록을 반환한다."""
        return self._alerts[-limit:]

    def get_order(self, order_id: str) -> Optional[PurchaseOrder]:
        return self._orders.get(order_id)

    def list_orders(self, status: str = '') -> List[PurchaseOrder]:
        orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o.status.value == status]
        return orders
