"""가격 알림 관리."""

import logging

logger = logging.getLogger(__name__)


class PriceAlerts:
    """가격 변동 알림."""

    def __init__(self):
        self._alerts: list = []

    def check(self, sku: str, old_price, new_price, threshold_pct: float = 20.0) -> bool:
        """가격 변동이 임계값을 초과하는지 확인.

        Args:
            sku: 상품 SKU
            old_price: 이전 가격
            new_price: 새 가격
            threshold_pct: 알림 임계값 (%)

        Returns:
            임계값 초과 여부
        """
        try:
            old = float(old_price)
            new = float(new_price)
            if old == 0:
                return False
            change_pct = abs((new - old) / old * 100)
            return change_pct >= threshold_pct
        except Exception as exc:
            logger.error("가격 알림 확인 오류: %s", exc)
            return False

    def send_alert(self, sku: str, old_price, new_price) -> None:
        """가격 변동 알림 발송 (mock)."""
        try:
            old = float(old_price)
            new = float(new_price)
            change_pct = (new - old) / old * 100 if old != 0 else 0.0
            alert = {
                'sku': sku,
                'old_price': old,
                'new_price': new,
                'change_pct': round(change_pct, 2),
            }
            self._alerts.append(alert)
            logger.warning("가격 변동 알림: %s %s -> %s (%.1f%%)", sku, old_price, new_price, change_pct)
        except Exception as exc:
            logger.error("가격 알림 발송 오류: %s", exc)

    def get_alerts(self) -> list:
        """알림 이력 반환."""
        return list(self._alerts)
