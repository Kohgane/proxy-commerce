"""tests/test_v88_net_profit.py — 콘솔 벤치마크 Q1 #1 순이익 자동계산.

계약: ÷0.618 엔진 재사용(이중 정의 0)·미입력 정직(가짜 수치 0)·complete만 집계.
FX 네트워크 없이(FX_DISABLE_NETWORK) 결정성.
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest

os.environ.setdefault("FX_DISABLE_NETWORK", "1")

from src.seller_console import net_profit as NP
from src.seller_console.margin_calculator import (CostInput, MarketInput, MarginCalculator,
                                                  default_commission_rate)


def _order(**kw):
    base = {"order_id": "O1", "marketplace": "coupang", "total_krw": "50000",
            "shipping_fee_krw": "0", "items": [{"sku": "SKU1", "qty": 1}]}
    base.update(kw)
    return base


def test_net_profit_reuses_margin_engine_no_double_definition():
    # 카탈로그 원가(USD 10) → 엔진이 환율·랜딩·수수료 산출. order_net_profit이 엔진과 동일 결과여야(이중정의 0).
    lookup = lambda sku: {"buy_price": "10", "buy_currency": "USD"} if sku == "SKU1" else None
    r = NP.order_net_profit(_order(total_krw="50000"), lookup_fn=lookup)
    # 엔진 직접 호출 기대치.
    calc = MarginCalculator()
    res = calc.calculate(CostInput(buy_price=Decimal("10"), buy_currency="USD", qty=1),
                         MarketInput(marketplace="coupang", commission_rate=default_commission_rate("coupang")),
                         sell_price=Decimal("50000"))
    assert r["complete"] is True
    assert r["net_krw"] == int(res.actual_margin_krw)          # 동일 공식(÷0.618 엔진)
    assert r["margin_pct"] == float(res.actual_margin_pct)
    assert r["landed_cost_krw"] == int(res.total_landed_cost)


def test_missing_cost_is_honest_not_fake_zero():
    # SKU 미매칭 → 원가 미입력. 순이익 None(가짜 0 금지) + missing에 '원가'.
    r = NP.order_net_profit(_order(), lookup_fn=lambda sku: None)
    assert r["complete"] is False and r["net_krw"] is None and r["margin_pct"] is None
    assert "원가" in r["missing"] and r["cost_source"] is None


def test_missing_sale_price_honest():
    r = NP.order_net_profit(_order(total_krw="0"), lookup_fn=lambda sku: {"buy_price": "10", "buy_currency": "USD"})
    assert r["complete"] is False and "판매가" in r["missing"] and r["net_krw"] is None


def test_order_landed_cost_direct_path():
    # 주문에 landed_cost_krw 확정 → 그걸로 순이익(카탈로그 조회 불필요).
    r = NP.order_net_profit(_order(landed_cost_krw="30000", items=[]), lookup_fn=lambda sku: None)
    assert r["complete"] is True and r["cost_source"] == "order"
    # net = 50000*(1-0.108?) ... 쿠팡 수수료율 단일소스 사용. 엔진 _calc_margin과 동일.
    fee = (default_commission_rate("coupang")) / Decimal("100")
    exp_net, exp_pct = MarginCalculator._calc_margin(Decimal("50000"), Decimal("30000"), fee)
    assert r["net_krw"] == int(exp_net) and r["margin_pct"] == float(exp_pct)


def test_channel_fee_is_single_source():
    # 마켓별 수수료율이 default_commission_rate에서 옴(하드코딩 아님).
    r = NP.order_net_profit(_order(marketplace="kohganemultishop", landed_cost_krw="30000", items=[]),
                            lookup_fn=lambda sku: None)
    # 자체몰은 commission + PG(3.3) 합산 반영.
    assert r["fee_rate_pct"] == float(default_commission_rate("kohganemultishop") + Decimal("3.3"))


def test_summary_aggregates_complete_only():
    lookup = lambda sku: {"buy_price": "10", "buy_currency": "USD"} if sku == "SKU1" else None
    orders = [
        _order(order_id="A", total_krw="50000"),                       # complete
        _order(order_id="B", items=[{"sku": "NOPE", "qty": 1}]),       # 원가 미입력
        _order(order_id="C", total_krw="0"),                           # 판매가 미입력
    ]
    s = NP.net_profit_summary(orders, lookup_fn=lookup)
    assert s["order_count"] == 3 and s["complete_count"] == 1 and s["incomplete_count"] == 2
    # 미완 주문 매출·순이익은 합산 안 됨(가짜 합산 0).
    assert s["total_sales_krw"] == 50000
    assert s["avg_margin_pct"] is not None


def test_summary_empty_no_fake_numbers():
    s = NP.net_profit_summary([])
    assert s["complete_count"] == 0 and s["total_net_krw"] == 0 and s["avg_margin_pct"] is None
