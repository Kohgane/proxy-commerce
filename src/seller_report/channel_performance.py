"""src/seller_report/channel_performance.py — ChannelPerformanceAnalyzer (Phase 114)."""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CHANNELS = ['coupang', 'naver', 'self_mall']


@dataclass
class ChannelPerformance:
    channel: str
    revenue: float
    orders: int
    avg_order_value: float
    margin_rate: float
    return_rate: float
    fulfillment_rate: float
    top_products: List[str] = field(default_factory=list)
    growth_rate: float = 0.0


class ChannelPerformanceAnalyzer:
    """판매 채널별 성과 분석."""

    def __init__(self) -> None:
        self._channel_data: Dict[str, Any] = self._generate_sample_data()

    def _generate_sample_data(self) -> Dict[str, Any]:
        data = {}
        for ch in CHANNELS:
            revenue = random.uniform(3_000_000, 15_000_000)
            orders = random.randint(50, 400)
            data[ch] = {
                'revenue': round(revenue),
                'orders': orders,
                'avg_order_value': round(revenue / orders),
                'margin_rate': round(random.uniform(10, 25), 2),
                'return_rate': round(random.uniform(2, 15), 2),
                'fulfillment_rate': round(random.uniform(90, 99), 2),
                'top_products': [f'PROD_{random.randint(1000, 9999)}' for _ in range(3)],
                'growth_rate': round(random.uniform(-10, 30), 2),
            }
        return data

    def analyze_channel(self, channel: str, period: str = 'monthly') -> ChannelPerformance:
        """채널별 성과 분석."""
        d = self._channel_data.get(channel, self._channel_data.get('coupang', {}))
        return ChannelPerformance(
            channel=channel,
            revenue=d.get('revenue', 0),
            orders=d.get('orders', 0),
            avg_order_value=d.get('avg_order_value', 0),
            margin_rate=d.get('margin_rate', 0),
            return_rate=d.get('return_rate', 0),
            fulfillment_rate=d.get('fulfillment_rate', 0),
            top_products=d.get('top_products', []),
            growth_rate=d.get('growth_rate', 0),
        )

    def compare_channels(self, period: str = 'monthly') -> List[ChannelPerformance]:
        """채널 간 비교."""
        return [self.analyze_channel(ch, period) for ch in CHANNELS]

    def get_best_channel(self) -> ChannelPerformance:
        """가장 성과 좋은 채널 (매출 기준)."""
        channels = self.compare_channels()
        return max(channels, key=lambda c: c.revenue)

    def get_channel_recommendations(self) -> List[Dict[str, str]]:
        """채널별 개선 제안."""
        recs = []
        for ch_perf in self.compare_channels():
            if ch_perf.return_rate > 10:
                recs.append({
                    'channel': ch_perf.channel,
                    'type': 'return_rate',
                    'message': (
                        f"{ch_perf.channel} 반품률 {ch_perf.return_rate:.1f}%로 높음 "
                        f"→ 상품 설명 보강 필요"
                    ),
                })
            if ch_perf.margin_rate < 12:
                recs.append({
                    'channel': ch_perf.channel,
                    'type': 'low_margin',
                    'message': (
                        f"{ch_perf.channel} 마진율 {ch_perf.margin_rate:.1f}% 낮음 "
                        f"→ 소싱 비용 재검토 필요"
                    ),
                })

        # 채널 간 AOV 비교 제안
        channels = self.compare_channels()
        if len(channels) >= 2:
            best_aov = max(channels, key=lambda c: c.avg_order_value)
            worst_aov = min(channels, key=lambda c: c.avg_order_value)
            if best_aov.avg_order_value > 0 and worst_aov.avg_order_value > 0:
                ratio = best_aov.avg_order_value / worst_aov.avg_order_value
                if ratio >= 1.2:
                    recs.append({
                        'channel': best_aov.channel,
                        'type': 'high_aov',
                        'message': (
                            f"{best_aov.channel} AOV가 {worst_aov.channel} 대비 "
                            f"{ratio:.0%} 높음 → 고가 상품 집중"
                        ),
                    })

        return recs
