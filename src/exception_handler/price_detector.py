"""src/exception_handler/price_detector.py — 가격 변동 감지 (Phase 105)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PriceAlertType(str, Enum):
    price_drop = 'price_drop'
    price_surge = 'price_surge'
    out_of_budget = 'out_of_budget'
    better_deal_found = 'better_deal_found'


@dataclass
class PriceAlert:
    alert_id: str
    product_id: str
    old_price: float
    new_price: float
    change_percent: float
    alert_type: PriceAlertType
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    budget: Optional[float] = None
    alternative: Optional[Dict] = None
    acknowledged: bool = False

    def to_dict(self) -> Dict:
        return {
            'alert_id': self.alert_id,
            'product_id': self.product_id,
            'old_price': self.old_price,
            'new_price': self.new_price,
            'change_percent': self.change_percent,
            'alert_type': self.alert_type.value,
            'timestamp': self.timestamp,
            'budget': self.budget,
            'alternative': self.alternative,
            'acknowledged': self.acknowledged,
        }


class PriceChangeDetector:
    """실시간 가격 변동 모니터링."""

    def __init__(
        self,
        drop_threshold_pct: float = -10.0,
        surge_threshold_pct: float = 10.0,
    ) -> None:
        self.drop_threshold_pct = drop_threshold_pct
        self.surge_threshold_pct = surge_threshold_pct
        self._price_history: Dict[str, List[Tuple[str, float]]] = {}  # product_id → [(ts, price)]
        self._alerts: Dict[str, PriceAlert] = {}
        self._budgets: Dict[str, float] = {}  # product_id → budget

    def set_budget(self, product_id: str, budget: float) -> None:
        self._budgets[product_id] = budget

    def record_price(self, product_id: str, price: float) -> Optional[PriceAlert]:
        """가격 기록 및 변동 감지. 알림이 발생하면 PriceAlert 반환."""
        ts = datetime.now(timezone.utc).isoformat()
        history = self._price_history.setdefault(product_id, [])

        alert: Optional[PriceAlert] = None

        if history:
            old_price = history[-1][1]
            if old_price > 0:
                change_pct = (price - old_price) / old_price * 100
                alert = self._evaluate_change(product_id, old_price, price, change_pct)

        history.append((ts, price))
        return alert

    def _evaluate_change(
        self,
        product_id: str,
        old_price: float,
        new_price: float,
        change_pct: float,
    ) -> Optional[PriceAlert]:
        alert_type: Optional[PriceAlertType] = None

        budget = self._budgets.get(product_id)
        if budget and new_price > budget:
            alert_type = PriceAlertType.out_of_budget
        elif change_pct <= self.drop_threshold_pct:
            alert_type = PriceAlertType.price_drop
        elif change_pct >= self.surge_threshold_pct:
            alert_type = PriceAlertType.price_surge

        if alert_type is None:
            return None

        alert_id = f'pa_{uuid.uuid4().hex[:10]}'
        alert = PriceAlert(
            alert_id=alert_id,
            product_id=product_id,
            old_price=old_price,
            new_price=new_price,
            change_percent=round(change_pct, 2),
            alert_type=alert_type,
            budget=budget,
        )
        self._alerts[alert_id] = alert
        logger.info(
            "가격 알림 생성: %s (product=%s, %.1f%%)",
            alert_id, product_id, change_pct,
        )
        return alert

    def check_price(
        self,
        product_id: str,
        current_price: float,
        budget: Optional[float] = None,
    ) -> Optional[PriceAlert]:
        """현재 가격을 이력과 비교하여 알림 생성."""
        if budget:
            self._budgets[product_id] = budget
        return self.record_price(product_id, current_price)

    def suggest_alternative(self, alert_id: str, alternative: Dict) -> PriceAlert:
        """더 나은 대안 제안을 알림에 추가."""
        alert = self._get_or_raise(alert_id)
        alert.alternative = alternative
        if not alert.alert_type == PriceAlertType.better_deal_found:
            # 새 알림으로 기록
            new_id = f'pa_{uuid.uuid4().hex[:10]}'
            new_alert = PriceAlert(
                alert_id=new_id,
                product_id=alert.product_id,
                old_price=alert.new_price,
                new_price=alternative.get('price', alert.new_price),
                change_percent=0.0,
                alert_type=PriceAlertType.better_deal_found,
                alternative=alternative,
            )
            self._alerts[new_id] = new_alert
            return new_alert
        return alert

    def get_price_history(self, product_id: str) -> List[Dict]:
        history = self._price_history.get(product_id, [])
        return [{'timestamp': ts, 'price': price} for ts, price in history]

    def get_trend(self, product_id: str) -> str:
        """가격 추세 분석: 'rising' | 'falling' | 'stable'."""
        history = self._price_history.get(product_id, [])
        if len(history) < 2:
            return 'stable'
        prices = [p for _, p in history[-5:]]
        if prices[-1] > prices[0]:
            return 'rising'
        if prices[-1] < prices[0]:
            return 'falling'
        return 'stable'

    def acknowledge(self, alert_id: str) -> PriceAlert:
        alert = self._get_or_raise(alert_id)
        alert.acknowledged = True
        return alert

    def get_alert(self, alert_id: str) -> Optional[PriceAlert]:
        return self._alerts.get(alert_id)

    def list_alerts(
        self,
        product_id: Optional[str] = None,
        alert_type: Optional[PriceAlertType] = None,
        acknowledged: Optional[bool] = None,
    ) -> List[PriceAlert]:
        alerts = list(self._alerts.values())
        if product_id:
            alerts = [a for a in alerts if a.product_id == product_id]
        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]
        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]
        return alerts

    def configure(self, drop_threshold_pct: float, surge_threshold_pct: float) -> None:
        self.drop_threshold_pct = drop_threshold_pct
        self.surge_threshold_pct = surge_threshold_pct

    def _get_or_raise(self, alert_id: str) -> PriceAlert:
        alert = self._alerts.get(alert_id)
        if alert is None:
            raise KeyError(f'가격 알림을 찾을 수 없습니다: {alert_id}')
        return alert
