"""안전 재고 계산기."""

import logging
import math

logger = logging.getLogger(__name__)


class SafetyStockCalculator:
    """안전 재고 및 재주문 포인트 계산."""

    def __init__(self):
        self._sku_data: dict = {}

    def calculate(self, avg_daily_sales: float, lead_time_days: int, safety_factor: float = 1.5) -> int:
        """안전 재고 계산.

        Args:
            avg_daily_sales: 일평균 판매량
            lead_time_days: 리드타임 (일)
            safety_factor: 안전 계수 (기본 1.5)

        Returns:
            안전 재고 수량
        """
        safety_stock = math.ceil(avg_daily_sales * lead_time_days * safety_factor)
        logger.debug("안전 재고 계산: avg_daily=%f, lead_time=%d, factor=%f -> %d",
                     avg_daily_sales, lead_time_days, safety_factor, safety_stock)
        return safety_stock

    def get_reorder_point(self, sku: str) -> int:
        """SKU의 재주문 포인트 반환."""
        data = self._sku_data.get(sku, {})
        avg_daily = data.get('avg_daily_sales', 0.0)
        lead_time = data.get('lead_time_days', 7)
        safety = self.calculate(avg_daily, lead_time)
        reorder_point = math.ceil(avg_daily * lead_time) + safety
        return reorder_point

    def check_reorder_needed(self, sku: str, current_stock: int) -> bool:
        """재주문이 필요한지 확인."""
        reorder_point = self.get_reorder_point(sku)
        needed = current_stock <= reorder_point
        if needed:
            logger.warning("재주문 필요: %s (현재:%d, 재주문포인트:%d)", sku, current_stock, reorder_point)
        return needed

    def set_sku_data(self, sku: str, avg_daily_sales: float, lead_time_days: int) -> None:
        """SKU 데이터 설정."""
        self._sku_data[sku] = {
            'avg_daily_sales': avg_daily_sales,
            'lead_time_days': lead_time_days,
        }
