"""src/seller_report/product_performance.py — ProductPerformanceAnalyzer (Phase 114)."""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ProductGrade(str, Enum):
    star = 'star'           # 상위 10%
    good = 'good'           # 10~30%
    average = 'average'     # 30~70%
    underperform = 'underperform'  # 70~90%
    poor = 'poor'           # 하위 10%


@dataclass
class ProductPerformance:
    product_id: str
    name: str
    channel: str
    revenue: float
    units_sold: int
    margin_rate: float
    return_rate: float
    ranking: int
    grade: ProductGrade
    avg_daily_sales: float
    days_of_stock: int
    sourcing_cost_trend: str  # 'up' / 'down' / 'stable'


class ProductPerformanceAnalyzer:
    """상품별 성과 분석."""

    def __init__(self) -> None:
        self._products = self._generate_sample_products()

    def _generate_sample_products(self) -> List[Dict[str, Any]]:
        channels = ['coupang', 'naver', 'self_mall']
        products = []
        for i in range(1, 201):
            revenue = random.uniform(50_000, 5_000_000)
            units = random.randint(1, 200)
            products.append({
                'product_id': f'PROD_{i:04d}',
                'name': f'상품 {i:04d}',
                'channel': random.choice(channels),
                'revenue': round(revenue),
                'units_sold': units,
                'margin_rate': round(random.uniform(-5, 40), 2),
                'return_rate': round(random.uniform(0, 20), 2),
                'avg_daily_sales': round(units / 30, 2),
                'days_of_stock': random.randint(0, 90),
                'sourcing_cost_trend': random.choice(['up', 'down', 'stable']),
                'last_sale_days_ago': random.randint(0, 60),
            })
        # 정렬 (매출 내림차순)
        products.sort(key=lambda p: p['revenue'], reverse=True)
        for rank, p in enumerate(products, start=1):
            p['ranking'] = rank
            # 등급 부여
            if rank <= len(products) * 0.10:
                p['grade'] = ProductGrade.star
            elif rank <= len(products) * 0.30:
                p['grade'] = ProductGrade.good
            elif rank <= len(products) * 0.70:
                p['grade'] = ProductGrade.average
            elif rank <= len(products) * 0.90:
                p['grade'] = ProductGrade.underperform
            else:
                p['grade'] = ProductGrade.poor
        return products

    def _to_perf(self, p: Dict[str, Any]) -> ProductPerformance:
        return ProductPerformance(
            product_id=p['product_id'],
            name=p['name'],
            channel=p['channel'],
            revenue=p['revenue'],
            units_sold=p['units_sold'],
            margin_rate=p['margin_rate'],
            return_rate=p['return_rate'],
            ranking=p['ranking'],
            grade=p['grade'],
            avg_daily_sales=p['avg_daily_sales'],
            days_of_stock=p['days_of_stock'],
            sourcing_cost_trend=p['sourcing_cost_trend'],
        )

    def analyze_product(self, product_id: str, period: str = 'monthly') -> Optional[ProductPerformance]:
        """상품 성과 분석."""
        for p in self._products:
            if p['product_id'] == product_id:
                return self._to_perf(p)
        return None

    def get_product_ranking(
        self,
        sort_by: str = 'revenue',
        limit: int = 20,
        channel: Optional[str] = None,
    ) -> List[ProductPerformance]:
        """상품 순위."""
        products = self._products
        if channel:
            products = [p for p in products if p['channel'] == channel]
        if sort_by == 'margin_rate':
            products = sorted(products, key=lambda p: p['margin_rate'], reverse=True)
        elif sort_by == 'units_sold':
            products = sorted(products, key=lambda p: p['units_sold'], reverse=True)
        else:
            products = sorted(products, key=lambda p: p['revenue'], reverse=True)
        return [self._to_perf(p) for p in products[:limit]]

    def get_product_grades(self) -> Dict[str, List[ProductPerformance]]:
        """전체 상품 등급 분류."""
        result: Dict[str, List[ProductPerformance]] = {
            grade.value: [] for grade in ProductGrade
        }
        for p in self._products:
            result[p['grade'].value].append(self._to_perf(p))
        return result

    def get_profitability_matrix(self) -> Dict[str, List[ProductPerformance]]:
        """수익성 4사분면 매트릭스."""
        avg_revenue = sum(p['revenue'] for p in self._products) / len(self._products)
        avg_margin = sum(p['margin_rate'] for p in self._products) / len(self._products)

        matrix: Dict[str, List[ProductPerformance]] = {
            'stars': [],       # 고매출+고마진
            'hidden_gems': [],  # 저매출+고마진
            'volume_drivers': [],  # 고매출+저마진
            'dogs': [],        # 저매출+저마진
        }
        for p in self._products:
            high_rev = p['revenue'] >= avg_revenue
            high_margin = p['margin_rate'] >= avg_margin
            if high_rev and high_margin:
                matrix['stars'].append(self._to_perf(p))
            elif not high_rev and high_margin:
                matrix['hidden_gems'].append(self._to_perf(p))
            elif high_rev and not high_margin:
                matrix['volume_drivers'].append(self._to_perf(p))
            else:
                matrix['dogs'].append(self._to_perf(p))
        return matrix

    def get_dead_stock(self, days_threshold: int = 30) -> List[ProductPerformance]:
        """30일 이상 판매 없는 상품."""
        dead = [p for p in self._products if p.get('last_sale_days_ago', 0) >= days_threshold]
        return [self._to_perf(p) for p in dead]

    def get_trending_products(self, limit: int = 10) -> List[ProductPerformance]:
        """판매 급상승 상품 (avg_daily_sales 높은 순)."""
        sorted_products = sorted(self._products, key=lambda p: p['avg_daily_sales'], reverse=True)
        return [self._to_perf(p) for p in sorted_products[:limit]]
