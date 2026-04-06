"""src/margin_calculator/margin_trend.py — 마진율 추이 분석 (Phase 110).

MarginTrendAnalyzer: 마진율 추이 분석 + 하락 감지
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .calculator import RealTimeMarginCalculator

logger = logging.getLogger(__name__)


@dataclass
class TrendPoint:
    """마진 추이 데이터 포인트."""
    timestamp: str
    product_id: Optional[str]
    channel: str
    margin_rate: float
    net_profit: float
    selling_price: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'product_id': self.product_id,
            'channel': self.channel,
            'margin_rate': self.margin_rate,
            'net_profit': self.net_profit,
            'selling_price': self.selling_price,
        }


class MarginTrendAnalyzer:
    """마진율 추이 분석."""

    def __init__(self, calculator: Optional[RealTimeMarginCalculator] = None) -> None:
        self._calc = calculator or RealTimeMarginCalculator()
        # 시계열 포인트: {product_id: [TrendPoint, ...]}
        self._points: Dict[str, List[TrendPoint]] = {}
        # 전체 평균 포인트
        self._overall: List[TrendPoint] = []

    # ── 데이터 기록 ───────────────────────────────────────────────────────────

    def record(
        self,
        product_id: str,
        channel: str = 'internal',
        product_data: Optional[Dict[str, Any]] = None,
    ) -> TrendPoint:
        """현재 시점 마진 기록."""
        result = self._calc.calculate_margin(
            product_id, channel, product_data=product_data
        )
        point = TrendPoint(
            timestamp=datetime.now(timezone.utc).isoformat(),
            product_id=product_id,
            channel=channel,
            margin_rate=result.margin_rate,
            net_profit=result.net_profit,
            selling_price=result.selling_price,
        )
        if product_id not in self._points:
            self._points[product_id] = []
        self._points[product_id].append(point)
        return point

    def seed_history(self, points: List[Dict[str, Any]]) -> None:
        """테스트/초기화 시 이력 데이터 주입."""
        for p in points:
            pid = p.get('product_id', '_overall')
            pt = TrendPoint(
                timestamp=p.get('timestamp', datetime.now(timezone.utc).isoformat()),
                product_id=p.get('product_id'),
                channel=p.get('channel', 'internal'),
                margin_rate=float(p.get('margin_rate', 0.0)),
                net_profit=float(p.get('net_profit', 0.0)),
                selling_price=float(p.get('selling_price', 0.0)),
            )
            if pid not in self._points:
                self._points[pid] = []
            self._points[pid].append(pt)
            if p.get('overall'):
                self._overall.append(pt)

    # ── 추이 조회 ─────────────────────────────────────────────────────────────

    def get_product_trend(
        self,
        product_id: str,
        period: str = 'monthly',
        interval: str = 'day',
        limit: int = 100,
    ) -> Dict[str, Any]:
        """상품별 마진 추이."""
        points = self._points.get(product_id, [])[-limit:]
        return {
            'product_id': product_id,
            'period': period,
            'interval': interval,
            'total': len(points),
            'data': [p.to_dict() for p in points],
        }

    def get_overall_trend(
        self,
        period: str = 'monthly',
        interval: str = 'day',
        limit: int = 100,
        channel: str = 'internal',
    ) -> Dict[str, Any]:
        """전체 평균 마진 추이 (calculator 이력 기반)."""
        history_raw = self._calc.get_history(channel=channel, limit=limit)
        return {
            'period': period,
            'interval': interval,
            'channel': channel,
            'total': len(history_raw),
            'data': history_raw,
        }

    def get_channel_trend(
        self,
        channel: str,
        period: str = 'monthly',
        interval: str = 'day',
        limit: int = 100,
    ) -> Dict[str, Any]:
        """채널별 마진 추이."""
        history = self._calc.get_history(channel=channel, limit=limit)
        return {
            'channel': channel,
            'period': period,
            'interval': interval,
            'total': len(history),
            'data': history,
        }

    # ── 하락 감지 ─────────────────────────────────────────────────────────────

    def detect_margin_decline(
        self,
        threshold: float = 2.0,
        min_points: int = 2,
    ) -> List[Dict[str, Any]]:
        """마진율 하락 중인 상품 감지.

        최근 2개 포인트 비교 — 하락폭 >= threshold% 인 상품 반환.
        """
        declining = []
        for pid, points in self._points.items():
            if len(points) < min_points:
                continue
            latest = points[-1]
            prev = points[-2]
            drop = prev.margin_rate - latest.margin_rate
            if drop >= threshold:
                declining.append({
                    'product_id': pid,
                    'channel': latest.channel,
                    'current_margin_rate': latest.margin_rate,
                    'previous_margin_rate': prev.margin_rate,
                    'decline': round(drop, 4),
                })
        return declining

    def get_trend_summary(self) -> Dict[str, Any]:
        """추이 요약 (상승/하락/안정 상품 수)."""
        rising = declining = stable = 0
        for points in self._points.values():
            if len(points) < 2:
                stable += 1
                continue
            diff = points[-1].margin_rate - points[-2].margin_rate
            if diff > 0.5:
                rising += 1
            elif diff < -0.5:
                declining += 1
            else:
                stable += 1

        return {
            'rising': rising,
            'declining': declining,
            'stable': stable,
            'total': rising + declining + stable,
        }
