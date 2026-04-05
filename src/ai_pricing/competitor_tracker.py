"""src/ai_pricing/competitor_tracker.py — 경쟁사 가격 추적기 (Phase 97)."""
from __future__ import annotations

import logging
import random
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

from .pricing_models import CompetitorPrice

logger = logging.getLogger(__name__)

# 경쟁사 정의 (mock)
_COMPETITORS = {
    'amazon_us': {'currency': 'USD', 'fx_to_krw': 1340.0},
    'amazon_jp': {'currency': 'JPY', 'fx_to_krw': 9.0},
    'coupang': {'currency': 'KRW', 'fx_to_krw': 1.0},
    'naver': {'currency': 'KRW', 'fx_to_krw': 1.0},
    '11st': {'currency': 'KRW', 'fx_to_krw': 1.0},
}

# 가격 변동 감지 임계값
_ALERT_THRESHOLD_PCT = 0.10  # 10%


class CompetitorPriceTracker:
    """경쟁사 가격 수집 및 변동 감지.

    경쟁사별 가격 이력을 시계열로 저장하고
    급등/급락(±10%) 감지 시 알림을 생성한다.
    """

    def __init__(self) -> None:
        # sku → list[CompetitorPrice]
        self._history: Dict[str, List[CompetitorPrice]] = defaultdict(list)
        # 경쟁사별 최신 가격 캐시: sku → {competitor_id: CompetitorPrice}
        self._latest: Dict[str, Dict[str, CompetitorPrice]] = defaultdict(dict)
        # 감지된 알림 목록
        self._alerts: List[Dict] = []

    # ── 가격 수집 (mock 시뮬레이션) ───────────────────────────────────────

    def collect_prices(self, sku: str, base_price_krw: float) -> List[CompetitorPrice]:
        """경쟁사 가격을 수집한다 (mock 시뮬레이션).

        Args:
            sku: 상품 SKU
            base_price_krw: 기준가 (KRW) — mock 가격 생성 기준

        Returns:
            수집된 경쟁사 가격 목록
        """
        collected: List[CompetitorPrice] = []

        for comp_id, info in _COMPETITORS.items():
            # mock: 기준가 ±20% 범위에서 랜덤 생성
            variation = random.uniform(-0.20, 0.20)
            local_price = base_price_krw * (1 + variation) / info['fx_to_krw']
            local_price = round(local_price, 2)

            cp = CompetitorPrice(
                competitor_id=comp_id,
                sku=sku,
                price=local_price,
                currency=info['currency'],
                source_url=f'https://{comp_id}.mock/products/{sku}',
            )
            collected.append(cp)

            # 변동 감지
            prev = self._latest[sku].get(comp_id)
            if prev:
                self._detect_change(prev, cp)

            self._latest[sku][comp_id] = cp
            self._history[sku].append(cp)

        logger.debug('경쟁사 가격 수집 완료: sku=%s, count=%d', sku, len(collected))
        return collected

    def collect_prices_raw(self, sku: str, prices: Dict[str, float]) -> List[CompetitorPrice]:
        """실제 수집된 가격 데이터를 직접 등록한다.

        Args:
            sku: 상품 SKU
            prices: {competitor_id: price_krw} 매핑

        Returns:
            등록된 CompetitorPrice 목록
        """
        collected: List[CompetitorPrice] = []
        for comp_id, price in prices.items():
            info = _COMPETITORS.get(comp_id, {'currency': 'KRW', 'fx_to_krw': 1.0})
            cp = CompetitorPrice(
                competitor_id=comp_id,
                sku=sku,
                price=price,
                currency=info['currency'],
                source_url=f'https://{comp_id}.mock/products/{sku}',
            )
            collected.append(cp)
            prev = self._latest[sku].get(comp_id)
            if prev:
                self._detect_change(prev, cp)
            self._latest[sku][comp_id] = cp
            self._history[sku].append(cp)
        return collected

    # ── 포지셔닝 분석 ─────────────────────────────────────────────────────

    def get_positioning(self, sku: str) -> Dict:
        """경쟁사 대비 포지셔닝 분석 결과를 반환한다.

        Returns:
            min_price, max_price, avg_price, count, prices_by_competitor
        """
        latest = self._latest.get(sku, {})
        if not latest:
            return {}

        prices_krw = {
            cid: cp.price * _COMPETITORS.get(cp.competitor_id, {}).get('fx_to_krw', 1.0)
            for cid, cp in latest.items()
        }

        values = list(prices_krw.values())
        return {
            'sku': sku,
            'min_price': round(min(values), 2),
            'max_price': round(max(values), 2),
            'avg_price': round(sum(values) / len(values), 2),
            'count': len(values),
            'prices_by_competitor': {
                cid: round(p, 2) for cid, p in prices_krw.items()
            },
        }

    def get_price_gap(self, sku: str, our_price: float) -> Dict:
        """우리 가격과 경쟁사 가격의 갭을 분석한다.

        Args:
            sku: 상품 SKU
            our_price: 우리 판매가 (KRW)

        Returns:
            vs_min, vs_avg, vs_max — 경쟁사 대비 % 차이 (양수=비쌈, 음수=저렴)
        """
        pos = self.get_positioning(sku)
        if not pos:
            return {}

        def pct_diff(other: float) -> float:
            if other == 0:
                return 0.0
            return round((our_price - other) / other * 100, 2)

        return {
            'sku': sku,
            'our_price': our_price,
            'vs_min': pct_diff(pos['min_price']),
            'vs_avg': pct_diff(pos['avg_price']),
            'vs_max': pct_diff(pos['max_price']),
            'advantage_count': sum(
                1 for p in pos['prices_by_competitor'].values() if our_price < p
            ),
            'total_competitors': pos['count'],
        }

    def get_history(self, sku: str, competitor_id: str = None) -> List[CompetitorPrice]:
        """경쟁사 가격 이력을 반환한다."""
        history = self._history.get(sku, [])
        if competitor_id:
            return [h for h in history if h.competitor_id == competitor_id]
        return history

    def get_latest(self, sku: str) -> Dict[str, CompetitorPrice]:
        """SKU별 최신 경쟁사 가격 캐시를 반환한다."""
        return dict(self._latest.get(sku, {}))

    def get_alerts(self, clear: bool = False) -> List[Dict]:
        """감지된 가격 변동 알림을 반환한다."""
        alerts = list(self._alerts)
        if clear:
            self._alerts.clear()
        return alerts

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────

    def _detect_change(self, prev: CompetitorPrice, curr: CompetitorPrice) -> None:
        """이전/현재 가격을 비교하여 급변 감지 시 알림을 추가한다."""
        if prev.price == 0:
            return
        change = (curr.price - prev.price) / prev.price
        if abs(change) >= _ALERT_THRESHOLD_PCT:
            direction = '급등' if change > 0 else '급락'
            alert = {
                'type': f'competitor_price_{direction}',
                'competitor_id': curr.competitor_id,
                'sku': curr.sku,
                'prev_price': prev.price,
                'curr_price': curr.price,
                'change_pct': round(change * 100, 2),
                'currency': curr.currency,
                'detected_at': datetime.now(timezone.utc).isoformat(),
            }
            self._alerts.append(alert)
            logger.info(
                '경쟁사 가격 %s 감지: %s/%s %.1f%%',
                direction,
                curr.competitor_id,
                curr.sku,
                change * 100,
            )
