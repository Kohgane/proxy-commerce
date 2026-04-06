"""src/margin_calculator/profitability.py — 수익성 분석 (Phase 110).

ProfitabilityAnalyzer: 상품별 수익성 분석 + 순위
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .calculator import MarginResult, RealTimeMarginCalculator

logger = logging.getLogger(__name__)


class ProfitabilityAnalyzer:
    """상품별 수익성 분석 + 순위."""

    def __init__(self, calculator: Optional[RealTimeMarginCalculator] = None) -> None:
        self._calc = calculator or RealTimeMarginCalculator()

    # ── 순위 ──────────────────────────────────────────────────────────────────

    def get_profitability_ranking(
        self,
        limit: int = 20,
        channel: str = 'internal',
        sort_by: str = 'margin_rate',
        reverse: bool = True,
    ) -> List[Dict[str, Any]]:
        """수익성 순위 (상위/하위).

        sort_by: 'margin_rate' | 'net_profit'
        reverse: True = 내림차순 (상위), False = 오름차순 (하위)
        """
        results = self._calc.calculate_bulk_margins(channel=channel)
        key = sort_by if sort_by in ('margin_rate', 'net_profit') else 'margin_rate'
        sorted_results = sorted(results, key=lambda r: getattr(r, key), reverse=reverse)
        return [
            {**r.to_dict(), 'rank': i + 1}
            for i, r in enumerate(sorted_results[:limit])
        ]

    # ── 필터 조회 ─────────────────────────────────────────────────────────────

    def get_loss_products(self, channel: str = 'internal') -> List[Dict[str, Any]]:
        """적자 상품 목록 (마진율 < 0%)."""
        results = self._calc.calculate_bulk_margins(channel=channel)
        return [r.to_dict() for r in results if r.margin_rate < 0]

    def get_low_margin_products(
        self,
        threshold: float = 5.0,
        channel: str = 'internal',
    ) -> List[Dict[str, Any]]:
        """저마진 상품 목록 (마진율 < threshold%)."""
        results = self._calc.calculate_bulk_margins(channel=channel)
        return [r.to_dict() for r in results if r.margin_rate < threshold]

    # ── 분포/채널 분석 ────────────────────────────────────────────────────────

    def get_profitability_distribution(self, channel: str = 'internal') -> Dict[str, Any]:
        """마진율 분포 (구간별 상품 수).

        Buckets: < 0, 0~5, 5~10, 10~15, 15~20, 20~30, >= 30
        """
        results = self._calc.calculate_bulk_margins(channel=channel)
        buckets: Dict[str, int] = {
            'loss': 0,       # < 0
            '0_5': 0,        # 0 ~ 5
            '5_10': 0,       # 5 ~ 10
            '10_15': 0,      # 10 ~ 15
            '15_20': 0,      # 15 ~ 20
            '20_30': 0,      # 20 ~ 30
            '30_plus': 0,    # >= 30
        }
        for r in results:
            m = r.margin_rate
            if m < 0:
                buckets['loss'] += 1
            elif m < 5:
                buckets['0_5'] += 1
            elif m < 10:
                buckets['5_10'] += 1
            elif m < 15:
                buckets['10_15'] += 1
            elif m < 20:
                buckets['15_20'] += 1
            elif m < 30:
                buckets['20_30'] += 1
            else:
                buckets['30_plus'] += 1

        total = len(results)
        avg_margin = (
            sum(r.margin_rate for r in results) / total if total > 0 else 0.0
        )
        return {
            'channel': channel,
            'total_products': total,
            'average_margin_rate': round(avg_margin, 4),
            'distribution': buckets,
        }

    def get_channel_profitability(self) -> Dict[str, Any]:
        """채널별 평균 마진율 비교."""
        channels = ['coupang', 'naver', 'internal']
        result: Dict[str, Any] = {}
        for ch in channels:
            margins = self._calc.calculate_bulk_margins(channel=ch)
            if not margins:
                result[ch] = {'average_margin_rate': 0.0, 'total_products': 0}
                continue
            avg = sum(r.margin_rate for r in margins) / len(margins)
            loss_count = sum(1 for r in margins if r.margin_rate < 0)
            result[ch] = {
                'channel': ch,
                'total_products': len(margins),
                'average_margin_rate': round(avg, 4),
                'loss_products': loss_count,
                'profitable_products': len(margins) - loss_count,
            }
        return result
