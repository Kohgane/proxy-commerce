"""src/ai_listing/price_suggester.py — AI 상품등록 가격 제안 (Phase 149).

Phase 140 가격 룰 + 마진 계산 연동.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_PRICE_MODE = os.getenv("AI_LISTING_PRICE_MODE", "auto")  # auto | manual

# 마켓별 수수료율 (Phase 143 auto_publish.py와 동기화)
_MARKET_FEE_RATES: Dict[str, float] = {
    "coupang": 0.108,
    "smartstore": 0.07,
    "11st": 0.09,
    "gmarket": 0.10,
    "default": 0.10,
}

# 기본 목표 마진율
_DEFAULT_TARGET_MARGIN_PCT = float(os.getenv("TARGET_MARGIN_PCT", "22"))
_MIN_MARGIN_PCT = float(os.getenv("PRICING_MIN_MARGIN_PCT", "15"))


def suggest_price(
    analysis: Dict[str, Any],
    market: str,
    cost_krw: Optional[int] = None,
    mode: str = _PRICE_MODE,
) -> Dict[str, Any]:
    """마켓별 가격 제안.

    Args:
        analysis:  analyzer 분석 결과 (estimated_price_range 포함)
        market:    대상 마켓
        cost_krw:  매입 원가 (원). None이면 추정 범위 사용
        mode:      auto | manual

    Returns:
        {
          "market": str,
          "suggested_price_krw": int,
          "min_price_krw": int,
          "max_price_krw": int,
          "margin_pct": float,
          "fee_rate": float,
          "mode": str,
        }
    """
    price_range = analysis.get("estimated_price_range", {})
    range_min = int(price_range.get("min") or 10000)
    range_max = int(price_range.get("max") or range_min * 3)

    fee_rate = _MARKET_FEE_RATES.get(market, _MARKET_FEE_RATES["default"])

    if mode == "auto":
        # Phase 140 가격 룰 연동 시도
        try:
            from src.pricing.rules import PricingRuleStore

            store = PricingRuleStore()
            rules = store.list_active_rules()
            if rules:
                # 첫 번째 활성 룰의 마진율 사용
                target_margin = float(rules[0].target_margin_pct or _DEFAULT_TARGET_MARGIN_PCT)
            else:
                target_margin = _DEFAULT_TARGET_MARGIN_PCT
        except Exception as exc:
            logger.debug("가격 룰 조회 실패 (기본값 사용): %s", exc)
            target_margin = _DEFAULT_TARGET_MARGIN_PCT

        if cost_krw and cost_krw > 0:
            # 원가 기반 계산
            target_price = int(cost_krw / (1 - target_margin / 100) / (1 - fee_rate))
            margin_pct = target_margin
        else:
            # 추정 범위 중간값 사용
            mid_price = (range_min + range_max) // 2
            target_price = mid_price
            cost_est = int(target_price * (1 - fee_rate) * (1 - target_margin / 100))
            margin_pct = (
                (target_price * (1 - fee_rate) - cost_est) / max(target_price, 1) * 100
            )
    else:
        # manual 모드: 범위 최솟값
        target_price = range_min
        margin_pct = 0.0

    return {
        "market": market,
        "suggested_price_krw": max(target_price, range_min),
        "min_price_krw": range_min,
        "max_price_krw": range_max,
        "margin_pct": round(margin_pct, 1),
        "fee_rate": fee_rate,
        "mode": mode,
    }


def suggest_prices_for_markets(
    analysis: Dict[str, Any],
    markets: list,
    cost_krw: Optional[int] = None,
    mode: str = _PRICE_MODE,
) -> Dict[str, Dict[str, Any]]:
    """여러 마켓 가격 일괄 제안."""
    return {
        market: suggest_price(analysis, market, cost_krw=cost_krw, mode=mode)
        for market in markets
    }
