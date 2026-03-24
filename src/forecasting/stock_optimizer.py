"""src/forecasting/stock_optimizer.py — 재고 최적화.

안전 재고, EOQ, 재고 소진 예상일 계산.
stdlib math만 사용 (외부 라이브러리 불필요).

환경변수:
  STOCK_SAFETY_FACTOR   — 안전 재고 안전 계수 (기본 1.5)
  STOCK_LEAD_TIME_DAYS  — 리드 타임 일수 (기본 7)
"""

import logging
import math
import os

logger = logging.getLogger(__name__)

_SAFETY_FACTOR = float(os.getenv('STOCK_SAFETY_FACTOR', '1.5'))
_LEAD_TIME_DAYS = int(os.getenv('STOCK_LEAD_TIME_DAYS', '7'))


class StockOptimizer:
    """재고 최적화 엔진."""

    def __init__(self):
        self._predictor = None
        self._catalog_cache = None

    def _get_predictor(self):
        if self._predictor is None:
            from .demand_predictor import DemandPredictor
            self._predictor = DemandPredictor()
        return self._predictor

    def _get_catalog(self) -> list:
        if self._catalog_cache is None:
            try:
                from ..utils.sheets import open_sheet
                sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
                catalog_sheet = os.getenv('CATALOG_SHEET_NAME', 'catalog')
                ws = open_sheet(sheet_id, catalog_sheet)
                self._catalog_cache = ws.get_all_records()
            except Exception as exc:
                logger.warning("카탈로그 조회 실패: %s", exc)
                self._catalog_cache = []
        return self._catalog_cache

    def calc_safety_stock(self, avg_daily_demand: float,
                          lead_time_days: int = None,
                          safety_factor: float = None) -> int:
        """안전 재고 계산.

        safety_stock = avg_daily_demand × lead_time_days × safety_factor

        Args:
            avg_daily_demand: 일 평균 수요량
            lead_time_days: 리드 타임 (기본 STOCK_LEAD_TIME_DAYS)
            safety_factor: 안전 계수 (기본 STOCK_SAFETY_FACTOR)

        Returns:
            안전 재고 수량 (정수, 올림)
        """
        if lead_time_days is None:
            lead_time_days = _LEAD_TIME_DAYS
        if safety_factor is None:
            safety_factor = _SAFETY_FACTOR
        return math.ceil(avg_daily_demand * lead_time_days * safety_factor)

    def calc_eoq(self, annual_demand: float,
                 order_cost: float,
                 holding_cost_per_unit: float) -> int:
        """경제적 주문량(EOQ) 계산.

        EOQ = sqrt(2 × annual_demand × order_cost / holding_cost_per_unit)

        Args:
            annual_demand: 연간 수요량
            order_cost: 주문당 비용 (KRW)
            holding_cost_per_unit: 단위당 보관 비용 (연간, KRW)

        Returns:
            최적 발주량 (정수)
        """
        if holding_cost_per_unit <= 0 or annual_demand <= 0:
            return 1
        eoq = math.sqrt(2 * annual_demand * order_cost / holding_cost_per_unit)
        return max(1, math.ceil(eoq))

    def calc_days_of_stock(self, current_stock: int,
                           avg_daily_demand: float) -> float:
        """재고 소진 예상일 계산.

        days_of_stock = current_stock / avg_daily_demand

        Args:
            current_stock: 현재 재고 수량
            avg_daily_demand: 일 평균 수요량

        Returns:
            소진 예상일 (float, 수요가 0이면 inf 반환)
        """
        if avg_daily_demand <= 0:
            return float('inf')
        return current_stock / avg_daily_demand

    def optimize_stock_levels(self) -> list:
        """모든 SKU의 권장 재고량 및 발주 시점 계산.

        Returns:
            SKU별 재고 최적화 권장 사항 리스트
        """
        catalog = self._get_catalog()
        predictor = self._get_predictor()
        results = []

        for row in catalog:
            sku = str(row.get('sku', ''))
            if not sku:
                continue

            current_stock = int(row.get('stock', 0) or 0)
            price_krw = float(row.get('price_krw') or row.get('sell_price_krw') or 0)

            try:
                forecast = predictor.predict_demand(sku, days_ahead=30)
            except Exception:
                forecast = {'avg_daily_demand': 0.0, 'confidence': 'low'}

            avg_daily = float(forecast.get('avg_daily_demand', 0.0))
            safety_stock = self.calc_safety_stock(avg_daily)
            days_left = self.calc_days_of_stock(current_stock, avg_daily)

            # EOQ (기본 주문 비용 5000원, 보관 비용 = 가격의 20%/365)
            order_cost = 5000.0
            holding_cost = (price_krw * 0.20 / 365) if price_krw > 0 else 1.0
            annual_demand = avg_daily * 365
            eoq = self.calc_eoq(annual_demand, order_cost, holding_cost)

            status = 'ok'
            if current_stock == 0:
                status = 'out_of_stock'
            elif current_stock < safety_stock:
                status = 'low_stock'
            elif days_left > 180:
                status = 'excess_stock'

            results.append({
                'sku': sku,
                'title': str(row.get('title', '')),
                'current_stock': current_stock,
                'avg_daily_demand': round(avg_daily, 4),
                'safety_stock': safety_stock,
                'eoq': eoq,
                'days_of_stock': round(days_left, 1) if days_left != float('inf') else None,
                'reorder_needed': current_stock <= safety_stock and avg_daily > 0,
                'status': status,
                'confidence': forecast.get('confidence', 'low'),
            })

        return results

    def get_stockout_risk(self, days_horizon: int = 14) -> list:
        """지정 기간 내 재고 소진 위험 상품 반환.

        Args:
            days_horizon: 위험 판단 기간 (일)

        Returns:
            소진 위험 상품 리스트 (소진 예상일 오름차순 정렬)
        """
        levels = self.optimize_stock_levels()
        at_risk = []

        for item in levels:
            days_left = item.get('days_of_stock')
            if days_left is not None and days_left <= days_horizon:
                at_risk.append(item)

        return sorted(at_risk, key=lambda x: (x['days_of_stock'] or 0))
