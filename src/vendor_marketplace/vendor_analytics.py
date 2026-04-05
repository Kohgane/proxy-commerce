"""src/vendor_marketplace/vendor_analytics.py — 판매자 대시보드 및 분석 (Phase 98)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional


class VendorDashboard:
    """판매자 전용 대시보드 — 매출 요약, 주문 현황, 재고 알림, 정산 예정액."""

    def get_summary(
        self,
        vendor_id: str,
        orders: List[dict],
        settlements: List[dict],
        low_stock_products: List[dict],
    ) -> dict:
        """대시보드 요약 생성."""
        now = datetime.now(timezone.utc)
        today = now.date()
        this_week_start = now - timedelta(days=now.weekday())

        # 매출 요약
        today_sales = sum(
            o.get('amount', 0)
            for o in orders
            if not o.get('is_return', False)
            and _parse_date(o.get('created_at', '')).date() == today
        )
        week_sales = sum(
            o.get('amount', 0)
            for o in orders
            if not o.get('is_return', False)
            and _parse_date(o.get('created_at', '')) >= this_week_start
        )
        total_sales = sum(
            o.get('amount', 0) for o in orders if not o.get('is_return', False)
        )

        # 주문 현황
        pending_orders = [o for o in orders if o.get('status') == 'pending']
        processing_orders = [o for o in orders if o.get('status') == 'processing']

        # 정산 예정액
        pending_settlements = [s for s in settlements if s.get('status') == 'pending']
        expected_payout = sum(s.get('net_amount', 0) for s in pending_settlements)

        return {
            'vendor_id': vendor_id,
            'generated_at': now.isoformat(),
            'sales': {
                'today': round(today_sales, 2),
                'this_week': round(week_sales, 2),
                'total': round(total_sales, 2),
            },
            'orders': {
                'total': len(orders),
                'pending': len(pending_orders),
                'processing': len(processing_orders),
            },
            'inventory': {
                'low_stock_count': len(low_stock_products),
                'low_stock_products': low_stock_products[:5],
            },
            'settlement': {
                'expected_payout': round(expected_payout, 2),
                'pending_count': len(pending_settlements),
            },
        }


class VendorAnalytics:
    """판매자별 매출 분석 및 트렌드."""

    def daily_trend(self, orders: List[dict], days: int = 30) -> List[dict]:
        """일별 매출 트렌드."""
        now = datetime.now(timezone.utc)
        trend = {}
        for i in range(days):
            date = (now - timedelta(days=i)).date().isoformat()
            trend[date] = 0.0

        for order in orders:
            if order.get('is_return', False):
                continue
            date = _parse_date(order.get('created_at', '')).date().isoformat()
            if date in trend:
                trend[date] = round(trend[date] + order.get('amount', 0), 2)

        return [{'date': d, 'sales': v} for d, v in sorted(trend.items())]

    def product_ranking(self, orders: List[dict]) -> List[dict]:
        """상품별 판매 순위."""
        product_sales: Dict[str, float] = {}
        product_count: Dict[str, int] = {}
        for order in orders:
            if order.get('is_return', False):
                continue
            pid = order.get('product_id', 'unknown')
            product_sales[pid] = product_sales.get(pid, 0.0) + order.get('amount', 0)
            product_count[pid] = product_count.get(pid, 0) + 1

        ranked = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)
        return [
            {
                'rank': i + 1,
                'product_id': pid,
                'total_sales': round(sales, 2),
                'order_count': product_count.get(pid, 0),
            }
            for i, (pid, sales) in enumerate(ranked)
        ]

    def return_rate(self, orders: List[dict]) -> float:
        """반품률 (%)."""
        if not orders:
            return 0.0
        returns = sum(1 for o in orders if o.get('is_return', False))
        total = len(orders)
        return round(returns / total * 100, 2)

    def average_rating(self, reviews: List[dict]) -> float:
        """고객 평점 평균."""
        if not reviews:
            return 0.0
        ratings = [r.get('rating', 0) for r in reviews if r.get('rating') is not None]
        if not ratings:
            return 0.0
        return round(sum(ratings) / len(ratings), 2)


class VendorScoring:
    """판매자 평가 점수 (100점 만점)."""

    # 가중치
    W_DELIVERY = 0.30
    W_RETURN = 0.25
    W_RATING = 0.30
    W_CS_RESPONSE = 0.15

    def calculate(
        self,
        delivery_delay_rate: float = 0.0,  # 배송 지연률 (0~1)
        return_rate: float = 0.0,           # 반품률 (0~1)
        avg_rating: float = 5.0,            # 고객 평점 (0~5)
        cs_response_hours: float = 1.0,     # CS 평균 응답 시간 (시간)
    ) -> dict:
        """종합 판매자 점수 계산."""
        # 각 항목 점수 (0~100)
        delivery_score = max(0.0, 100.0 - delivery_delay_rate * 200)
        return_score = max(0.0, 100.0 - return_rate * 200)
        rating_score = (avg_rating / 5.0) * 100.0
        # CS 응답 시간: 1시간 이하 = 100점, 24시간 이상 = 0점
        cs_score = max(0.0, 100.0 - (cs_response_hours - 1) / 23 * 100)

        total = (
            delivery_score * self.W_DELIVERY
            + return_score * self.W_RETURN
            + rating_score * self.W_RATING
            + cs_score * self.W_CS_RESPONSE
        )
        total = round(min(100.0, max(0.0, total)), 2)

        return {
            'total_score': total,
            'delivery_score': round(delivery_score, 2),
            'return_score': round(return_score, 2),
            'rating_score': round(rating_score, 2),
            'cs_score': round(cs_score, 2),
            'grade': self._grade(total),
        }

    def _grade(self, score: float) -> str:
        if score >= 90:
            return 'S'
        if score >= 80:
            return 'A'
        if score >= 70:
            return 'B'
        if score >= 60:
            return 'C'
        return 'D'


class VendorRanking:
    """판매자 순위 — 매출/평점/스코어 기준."""

    BADGE_THRESHOLDS = {
        'top_seller': 90.0,       # 매출 상위
        'high_rated': 4.5,        # 평점 기준
        'excellent_vendor': 85.0, # 종합 스코어 기준
    }

    def rank_by_sales(self, vendor_stats: List[dict]) -> List[dict]:
        """매출 기준 랭킹."""
        ranked = sorted(vendor_stats, key=lambda v: v.get('total_sales', 0), reverse=True)
        for i, v in enumerate(ranked):
            v['sales_rank'] = i + 1
        return ranked

    def rank_by_score(self, vendor_scores: List[dict]) -> List[dict]:
        """스코어 기준 랭킹."""
        ranked = sorted(vendor_scores, key=lambda v: v.get('total_score', 0), reverse=True)
        for i, v in enumerate(ranked):
            v['score_rank'] = i + 1
        return ranked

    def get_badges(self, vendor: dict) -> List[str]:
        """우수 판매자 뱃지 부여."""
        badges = []
        if vendor.get('total_sales', 0) >= self.BADGE_THRESHOLDS['top_seller']:
            badges.append('🏆 TOP_SELLER')
        if vendor.get('avg_rating', 0) >= self.BADGE_THRESHOLDS['high_rated']:
            badges.append('⭐ HIGH_RATED')
        if vendor.get('total_score', 0) >= self.BADGE_THRESHOLDS['excellent_vendor']:
            badges.append('🥇 EXCELLENT_VENDOR')
        return badges

    def build_leaderboard(self, vendor_stats: List[dict]) -> List[dict]:
        """종합 리더보드 생성."""
        for v in vendor_stats:
            v['badges'] = self.get_badges(v)
        ranked = self.rank_by_score(vendor_stats)
        return ranked


def _parse_date(date_str: str) -> datetime:
    """ISO 날짜 문자열 파싱 (실패 시 epoch 반환)."""
    try:
        if date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'
        return datetime.fromisoformat(date_str)
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
