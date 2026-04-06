"""src/virtual_inventory/stock_analytics.py — 가상 재고 분석 (Phase 113)."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class VirtualStockAnalytics:
    """가상 재고 분석 엔진."""

    def __init__(self) -> None:
        self._stock_pool = None

    def set_stock_pool(self, pool) -> None:
        self._stock_pool = pool

    # ── 요약 ──────────────────────────────────────────────────────────────────

    def get_stock_summary(self) -> dict:
        if self._stock_pool is None:
            return {}
        stocks = self._stock_pool.get_all_virtual_stocks()
        total_skus = len(stocks)
        total_virtual_stock = sum(vs.total_available for vs in stocks)
        avg_sources = (
            sum(len(vs.sources) for vs in stocks) / total_skus if total_skus else 0
        )
        out_of_stock = sum(1 for vs in stocks if vs.sellable == 0)
        low_stock = sum(1 for vs in stocks if 0 < vs.sellable <= 3)
        return {
            'total_skus': total_skus,
            'total_virtual_stock': total_virtual_stock,
            'avg_sources_per_sku': round(avg_sources, 2),
            'out_of_stock_count': out_of_stock,
            'low_stock_count': low_stock,
        }

    def get_source_distribution(self) -> Dict[str, dict]:
        if self._stock_pool is None:
            return {}
        stocks = self._stock_pool.get_all_virtual_stocks()
        distribution: Dict[str, dict] = {}
        for vs in stocks:
            for src in vs.sources:
                if src.source_id not in distribution:
                    distribution[src.source_id] = {
                        'total_qty': 0,
                        'product_count': 0,
                        'avg_price': 0.0,
                        '_prices': [],
                    }
                distribution[src.source_id]['total_qty'] += src.available_qty
                distribution[src.source_id]['product_count'] += 1
                distribution[src.source_id]['_prices'].append(src.price)
        for sid, data in distribution.items():
            prices = data.pop('_prices')
            data['avg_price'] = round(sum(prices) / len(prices), 2) if prices else 0.0
        return distribution

    def get_stock_health(self) -> dict:
        if self._stock_pool is None:
            return {}
        stocks = self._stock_pool.get_all_virtual_stocks()
        total = len(stocks)
        if total == 0:
            return {
                'healthy_pct': 0, 'low_stock_pct': 0,
                'out_of_stock_pct': 0, 'overstock_pct': 0,
                'counts': {'healthy': 0, 'low_stock': 0, 'out_of_stock': 0, 'overstock': 0},
            }
        out_of_stock = [vs for vs in stocks if vs.sellable == 0]
        low_stock = [vs for vs in stocks if 0 < vs.sellable <= 3]
        overstock = [vs for vs in stocks if vs.sellable > 30]
        healthy_count = total - len(out_of_stock) - len(low_stock) - len(overstock)
        healthy_count = max(0, healthy_count)

        def pct(n):
            return round(n / total * 100, 1)

        return {
            'healthy_pct': pct(healthy_count),
            'low_stock_pct': pct(len(low_stock)),
            'out_of_stock_pct': pct(len(out_of_stock)),
            'overstock_pct': pct(len(overstock)),
            'counts': {
                'healthy': healthy_count,
                'low_stock': len(low_stock),
                'out_of_stock': len(out_of_stock),
                'overstock': len(overstock),
            },
        }

    def get_turnover_analysis(self, product_id: Optional[str] = None) -> dict:
        """mock: turnover_rate = sellable / max(1, total_available)."""
        if self._stock_pool is None:
            return {}
        if product_id is not None:
            stocks = [self._stock_pool.get_virtual_stock(product_id)]
            stocks = [s for s in stocks if s is not None]
        else:
            stocks = self._stock_pool.get_all_virtual_stocks()

        result = {}
        for vs in stocks:
            result[vs.product_id] = {
                'product_id': vs.product_id,
                'sellable': vs.sellable,
                'total_available': vs.total_available,
                'turnover_rate': round(vs.sellable / max(1, vs.total_available), 4),
            }
        return result

    def get_single_source_products(self) -> List[str]:
        """활성 소싱처가 1개뿐인 상품 목록."""
        if self._stock_pool is None:
            return []
        result = []
        for vs in self._stock_pool.get_all_virtual_stocks():
            active_count = sum(1 for s in vs.sources if s.is_active)
            if active_count == 1:
                result.append(vs.product_id)
        return result

    def get_stock_value(self, product_id: Optional[str] = None, currency: str = 'KRW') -> dict:  # noqa: ARG002
        """재고 가치 계산. price * available_qty 합산."""
        if self._stock_pool is None:
            return {'total_value': 0, 'by_product': {}}

        if product_id is not None:
            stocks = [self._stock_pool.get_virtual_stock(product_id)]
            stocks = [s for s in stocks if s is not None]
        else:
            stocks = self._stock_pool.get_all_virtual_stocks()

        by_product = {}
        for vs in stocks:
            value = sum(s.price * s.available_qty for s in vs.sources)
            by_product[vs.product_id] = round(value, 2)

        return {
            'total_value': round(sum(by_product.values()), 2),
            'by_product': by_product,
        }
