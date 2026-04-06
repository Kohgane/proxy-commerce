"""src/autonomous_ops/revenue_model.py — 수익 추적 및 분석 (Phase 106)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional


class RevenueStream(str, Enum):
    proxy_buy = 'proxy_buy'
    import_ = 'import_'
    export = 'export'
    commission = 'commission'
    service_fee = 'service_fee'


@dataclass
class RevenueRecord:
    record_id: str
    stream: RevenueStream
    amount: float
    cost: float
    currency: str
    timestamp: str
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'record_id': self.record_id,
            'stream': self.stream.value,
            'amount': self.amount,
            'cost': self.cost,
            'currency': self.currency,
            'timestamp': self.timestamp,
            'metadata': self.metadata,
        }


@dataclass
class CostBreakdown:
    product_cost: float = 0.0
    shipping: float = 0.0
    customs: float = 0.0
    commission: float = 0.0
    operation: float = 0.0
    fx_loss: float = 0.0

    @property
    def total(self) -> float:
        return self.product_cost + self.shipping + self.customs + self.commission + self.operation + self.fx_loss

    def to_dict(self) -> Dict:
        return {
            'product_cost': self.product_cost,
            'shipping': self.shipping,
            'customs': self.customs,
            'commission': self.commission,
            'operation': self.operation,
            'fx_loss': self.fx_loss,
            'total': self.total,
        }


class RevenueTracker:
    """실시간 수익 추적."""

    def __init__(self) -> None:
        self._records: List[RevenueRecord] = []

    def add_record(
        self,
        stream: RevenueStream,
        amount: float,
        cost: float,
        currency: str = 'KRW',
        metadata: Optional[Dict] = None,
    ) -> RevenueRecord:
        record = RevenueRecord(
            record_id=f'rev_{uuid.uuid4().hex[:10]}',
            stream=stream,
            amount=amount,
            cost=cost,
            currency=currency,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )
        self._records.append(record)
        return record

    def get_daily_revenue(self, date_str: Optional[str] = None) -> Dict:
        if date_str is None:
            date_str = datetime.now(timezone.utc).date().isoformat()
        result: Dict[str, float] = {s.value: 0.0 for s in RevenueStream}
        for r in self._records:
            if r.timestamp.startswith(date_str):
                result[r.stream.value] = result.get(r.stream.value, 0.0) + r.amount
        return result

    def get_weekly_summary(self) -> Dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        total = sum(r.amount for r in self._records if r.timestamp >= cutoff)
        cost = sum(r.cost for r in self._records if r.timestamp >= cutoff)
        return {'total_revenue': total, 'total_cost': cost, 'net': total - cost, 'period_days': 7}

    def get_monthly_summary(self) -> Dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        total = sum(r.amount for r in self._records if r.timestamp >= cutoff)
        cost = sum(r.cost for r in self._records if r.timestamp >= cutoff)
        return {'total_revenue': total, 'total_cost': cost, 'net': total - cost, 'period_days': 30}

    def list_records(self, limit: int = 100) -> List[Dict]:
        return [r.to_dict() for r in self._records[-limit:]]


class ProfitCalculator:
    """순이익 계산."""

    def calculate(self, revenue: float, cost_breakdown: CostBreakdown) -> Dict:
        net_profit = revenue - cost_breakdown.total
        margin_rate = self.calculate_margin(revenue, cost_breakdown.total)
        return {
            'revenue': revenue,
            'total_cost': cost_breakdown.total,
            'net_profit': net_profit,
            'margin_rate': margin_rate,
            'cost_breakdown': cost_breakdown.to_dict(),
        }

    def calculate_margin(self, revenue: float, cost: float) -> float:
        if revenue == 0:
            return 0.0
        return (revenue - cost) / revenue


class MarginAnalyzer:
    """마진율 분석."""

    def analyze_by_stream(self, records: List[RevenueRecord]) -> Dict:
        data: Dict[str, Dict] = {}
        for r in records:
            key = r.stream.value
            if key not in data:
                data[key] = {'revenue': 0.0, 'cost': 0.0}
            data[key]['revenue'] += r.amount
            data[key]['cost'] += r.cost
        result = {}
        for key, vals in data.items():
            rev = vals['revenue']
            cost = vals['cost']
            margin_rate = (rev - cost) / rev if rev else 0.0
            result[key] = {'revenue': rev, 'cost': cost, 'margin_rate': margin_rate}
        return result

    def analyze_by_channel(self, records: List[RevenueRecord], channel_fn=None) -> Dict:
        if channel_fn is None:
            channel_fn = lambda r: r.metadata.get('channel', 'unknown')
        data: Dict[str, Dict] = {}
        for r in records:
            key = channel_fn(r)
            if key not in data:
                data[key] = {'revenue': 0.0, 'cost': 0.0}
            data[key]['revenue'] += r.amount
            data[key]['cost'] += r.cost
        result = {}
        for key, vals in data.items():
            rev = vals['revenue']
            cost = vals['cost']
            margin_rate = (rev - cost) / rev if rev else 0.0
            result[key] = {'revenue': rev, 'cost': cost, 'margin_rate': margin_rate}
        return result


class RevenueForecaster:
    """이동평균 기반 수익 예측."""

    def forecast_next_period(self, daily_revenues: List[float], periods: int = 7) -> List[float]:
        if not daily_revenues:
            return [0.0] * periods
        window = min(len(daily_revenues), 7)
        avg = sum(daily_revenues[-window:]) / window
        return [avg] * periods
