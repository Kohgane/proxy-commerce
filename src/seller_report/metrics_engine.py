"""src/seller_report/metrics_engine.py — PerformanceMetricsEngine (Phase 114)."""
from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReportPeriod(str, Enum):
    daily = 'daily'
    weekly = 'weekly'
    monthly = 'monthly'
    custom = 'custom'


@dataclass
class PerformanceMetrics:
    period: str
    start_date: date
    end_date: date
    total_revenue: float
    total_cost: float
    gross_profit: float
    net_profit: float
    gross_margin_rate: float
    net_margin_rate: float
    total_orders: int
    avg_order_value: float
    return_rate: float
    cancel_rate: float
    fulfillment_rate: float
    sla_compliance_rate: float
    customer_satisfaction_score: float
    unique_customers: int
    repeat_customer_rate: float
    active_products: int
    out_of_stock_products: int


class PerformanceMetricsEngine:
    """핵심 KPI 수집/계산 엔진."""

    def __init__(self) -> None:
        self._metrics_cache: Dict[str, PerformanceMetrics] = {}
        self._trend_data: Dict[str, List[Dict[str, Any]]] = {}
        self._sample_data = self._generate_sample_data()

    # ── 샘플 데이터 생성 ──────────────────────────────────────────────────────

    def _generate_sample_data(self) -> Dict[str, Any]:
        """데모/테스트용 샘플 데이터 생성."""
        today = date.today()
        data: Dict[str, Any] = {'daily': [], 'weekly': [], 'monthly': []}

        # 일간 데이터 (최근 30일)
        for i in range(30):
            day = today - timedelta(days=i)
            revenue = random.uniform(800_000, 2_000_000)
            cost = revenue * random.uniform(0.60, 0.75)
            orders = random.randint(15, 60)
            data['daily'].append({
                'date': day,
                'revenue': round(revenue),
                'cost': round(cost),
                'orders': orders,
                'returns': random.randint(0, max(1, orders // 10)),
                'cancels': random.randint(0, max(1, orders // 15)),
                'unique_customers': random.randint(10, 50),
            })

        # 주간 데이터 (최근 12주)
        for i in range(12):
            week_start = today - timedelta(weeks=i + 1)
            revenue = random.uniform(5_000_000, 12_000_000)
            cost = revenue * random.uniform(0.60, 0.75)
            orders = random.randint(80, 300)
            data['weekly'].append({
                'week_start': week_start,
                'revenue': round(revenue),
                'cost': round(cost),
                'orders': orders,
            })

        # 월간 데이터 (최근 12개월)
        for i in range(12):
            month_start = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
            revenue = random.uniform(20_000_000, 50_000_000)
            cost = revenue * random.uniform(0.60, 0.75)
            orders = random.randint(300, 1000)
            data['monthly'].append({
                'month_start': month_start,
                'revenue': round(revenue),
                'cost': round(cost),
                'orders': orders,
            })

        return data

    # ── 메트릭 계산 ──────────────────────────────────────────────────────────

    def calculate_metrics(
        self,
        period: str = 'daily',
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> PerformanceMetrics:
        """기간별 메트릭 계산."""
        today = date.today()

        if period == 'daily':
            start_date = start_date or today
            end_date = end_date or today
        elif period == 'weekly':
            end_date = end_date or today
            start_date = start_date or (end_date - timedelta(days=6))
        elif period == 'monthly':
            end_date = end_date or today
            start_date = start_date or end_date.replace(day=1)
        else:
            start_date = start_date or today
            end_date = end_date or today

        # 샘플 기반 집계
        days = max(1, (end_date - start_date).days + 1)
        base_revenue = random.uniform(800_000, 2_000_000) * days
        base_cost = base_revenue * random.uniform(0.62, 0.72)
        base_orders = random.randint(15, 60) * days

        gross_profit = base_revenue - base_cost
        marketing_cost = base_revenue * random.uniform(0.05, 0.10)
        net_profit = gross_profit - marketing_cost

        total_returns = random.randint(0, max(1, base_orders // 10))
        total_cancels = random.randint(0, max(1, base_orders // 15))
        unique_customers = random.randint(int(base_orders * 0.6), base_orders)
        repeat_customers = random.randint(0, unique_customers // 3)

        metrics = PerformanceMetrics(
            period=period,
            start_date=start_date,
            end_date=end_date,
            total_revenue=round(base_revenue),
            total_cost=round(base_cost),
            gross_profit=round(gross_profit),
            net_profit=round(net_profit),
            gross_margin_rate=round(gross_profit / base_revenue * 100, 2) if base_revenue else 0.0,
            net_margin_rate=round(net_profit / base_revenue * 100, 2) if base_revenue else 0.0,
            total_orders=base_orders,
            avg_order_value=round(base_revenue / base_orders, 0) if base_orders else 0.0,
            return_rate=round(total_returns / base_orders * 100, 2) if base_orders else 0.0,
            cancel_rate=round(total_cancels / base_orders * 100, 2) if base_orders else 0.0,
            fulfillment_rate=round(random.uniform(92, 99), 2),
            sla_compliance_rate=round(random.uniform(85, 98), 2),
            customer_satisfaction_score=round(random.uniform(3.8, 4.8), 2),
            unique_customers=unique_customers,
            repeat_customer_rate=round(repeat_customers / unique_customers * 100, 2) if unique_customers else 0.0,
            active_products=random.randint(150, 250),
            out_of_stock_products=random.randint(0, 20),
        )

        cache_key = f"{period}_{start_date}_{end_date}"
        self._metrics_cache[cache_key] = metrics
        return metrics

    def get_kpi_summary(self) -> Dict[str, Any]:
        """핵심 KPI 요약 (전일 대비 변화율 포함)."""
        today_metrics = self.calculate_metrics('daily')
        yesterday = date.today() - timedelta(days=1)
        yesterday_metrics = self.calculate_metrics('daily', start_date=yesterday, end_date=yesterday)

        def _change_rate(current: float, previous: float) -> float:
            if previous == 0:
                return 0.0
            return round((current - previous) / previous * 100, 2)

        return {
            'revenue': {
                'value': today_metrics.total_revenue,
                'change_rate': _change_rate(today_metrics.total_revenue, yesterday_metrics.total_revenue),
            },
            'orders': {
                'value': today_metrics.total_orders,
                'change_rate': _change_rate(today_metrics.total_orders, yesterday_metrics.total_orders),
            },
            'gross_margin_rate': {
                'value': today_metrics.gross_margin_rate,
                'change_rate': _change_rate(today_metrics.gross_margin_rate, yesterday_metrics.gross_margin_rate),
            },
            'avg_order_value': {
                'value': today_metrics.avg_order_value,
                'change_rate': _change_rate(today_metrics.avg_order_value, yesterday_metrics.avg_order_value),
            },
            'return_rate': {
                'value': today_metrics.return_rate,
                'change_rate': _change_rate(today_metrics.return_rate, yesterday_metrics.return_rate),
            },
            'fulfillment_rate': {
                'value': today_metrics.fulfillment_rate,
                'change_rate': _change_rate(today_metrics.fulfillment_rate, yesterday_metrics.fulfillment_rate),
            },
            'sla_compliance_rate': {
                'value': today_metrics.sla_compliance_rate,
                'change_rate': _change_rate(today_metrics.sla_compliance_rate, yesterday_metrics.sla_compliance_rate),
            },
            'period': 'daily',
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }

    def compare_periods(self, period1: str, period2: str) -> Dict[str, Any]:
        """기간 비교 (MoM, WoW, YoY)."""
        m1 = self.calculate_metrics(period1)
        m2 = self.calculate_metrics(period2)

        def _diff(v1: float, v2: float) -> Dict[str, Any]:
            change = round(v1 - v2, 2)
            rate = round((v1 - v2) / v2 * 100, 2) if v2 != 0 else 0.0
            return {'period1': v1, 'period2': v2, 'change': change, 'change_rate': rate}

        return {
            'comparison_type': f'{period1}_vs_{period2}',
            'revenue': _diff(m1.total_revenue, m2.total_revenue),
            'orders': _diff(m1.total_orders, m2.total_orders),
            'gross_margin_rate': _diff(m1.gross_margin_rate, m2.gross_margin_rate),
            'net_margin_rate': _diff(m1.net_margin_rate, m2.net_margin_rate),
            'avg_order_value': _diff(m1.avg_order_value, m2.avg_order_value),
            'return_rate': _diff(m1.return_rate, m2.return_rate),
            'fulfillment_rate': _diff(m1.fulfillment_rate, m2.fulfillment_rate),
        }

    def get_metric_trend(
        self,
        metric_name: str,
        period: str = 'daily',
        interval: int = 7,
    ) -> List[Dict[str, Any]]:
        """특정 메트릭 추이."""
        today = date.today()
        trend = []
        for i in range(interval):
            day = today - timedelta(days=i)
            m = self.calculate_metrics(period, start_date=day, end_date=day)
            value = getattr(m, metric_name, None)
            if value is not None:
                trend.append({'date': day.isoformat(), 'value': value})
        trend.reverse()
        return trend
