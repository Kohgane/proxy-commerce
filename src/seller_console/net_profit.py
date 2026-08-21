"""src/seller_console/net_profit.py — 주문별 순이익 자동계산 (콘솔 벤치마크 Q1 #1).

오너 지시(2026-08-21): 판매가·원가·수수료(채널별)·배송비·환율 반영 **실마진**.
  - 가짜 수치 금지 — 데이터 없는 필드는 **"미입력"** 정직 표기(원가 미연결 주문은 순이익 None).
  - 마진 공식은 기존 **÷0.618 체계**(`MarginCalculator._calc_margin` = 판매가·(1-수수료) - 랜딩코스트)와
    **정합 유지 · 이중 정의 금지** → 이 모듈은 새 공식을 만들지 않고 `MarginCalculator`를 그대로 호출한다.
  - 채널 수수료율도 단일 소스(`default_commission_rate`) 재사용(percenty MARKET_PRICE_POLICY + 자체몰 기본).

읽기 전용 read-model: 주문 dict + (SKU→카탈로그 원가) 조인으로 원가를 자동 해석(있으면), 없으면 미입력.
전부 주입 가능(lookup_fn/calc)해 오프라인 계약 검증(FX·시트·네트워크 없이).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional


def _dec(v) -> Optional[Decimal]:
    """숫자화(미상은 None — 가짜 0 금지)."""
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d


def _default_lookup_fn():
    """기본 원가 해석기: 카탈로그 SKU 역참조(있으면). import 실패/미연동은 None 반환(정직)."""
    try:
        from src.orders.catalog_lookup import CatalogLookup
        cl = CatalogLookup()
    except Exception:
        return lambda sku: None

    def _lk(sku):
        try:
            return cl.lookup_by_sku(sku)
        except Exception:
            return None
    return _lk


def resolve_order_cost(order: dict, *, lookup_fn=None) -> dict:
    """주문 원가(매입가·통화·수량) 해석. 우선순위: ① 주문에 기록된 landed_cost_krw → ② SKU→카탈로그 매입가.

    반환: {found, source, landed_cost_krw?, buy_price?, buy_currency?, qty, sku, reason?}.
    못 찾으면 found=False + 사유(원가 미연결 = "미입력"). **가짜 원가 0 금지.**
    """
    landed = _dec(order.get("landed_cost_krw"))
    if landed is not None and landed > 0:
        return {"found": True, "source": "order", "landed_cost_krw": landed, "qty": 1, "sku": ""}
    items = order.get("items") or []
    lookup_fn = lookup_fn or _default_lookup_fn()
    for it in items:
        sku = str((it or {}).get("sku") or "").strip()
        if not sku:
            continue
        row = lookup_fn(sku) or None
        if not row:
            continue
        bp = _dec(row.get("buy_price"))
        cur = str(row.get("buy_currency") or "").strip().upper()
        if bp is not None and bp > 0 and cur:
            qty = 1
            try:
                qty = max(1, int((it or {}).get("qty") or 1))
            except (TypeError, ValueError):
                qty = 1
            return {"found": True, "source": "catalog", "buy_price": bp, "buy_currency": cur,
                    "qty": qty, "sku": sku}
    return {"found": False, "source": None, "qty": 1, "sku": "",
            "reason": "원가 미연결(수집 원본 SKU 미매칭 또는 매입가 미상)"}


def order_net_profit(order: dict, *, calc=None, lookup_fn=None, target_margin_pct: Decimal = Decimal("22")) -> dict:
    """단일 주문 순이익 = 판매가·(1-수수료) - 랜딩코스트(원가+관부가세+배송+환율). **엔진 재사용, 새 공식 0.**

    complete=False면 순이익 None + missing[](미입력 필드) — 정직. 판매가/원가 미상은 집계 제외 대상.
    """
    from .margin_calculator import (CostInput, MarketInput, MarginCalculator,
                                     default_commission_rate, _DEFAULT_PG_FEE)
    mp = str(order.get("marketplace") or "").strip()
    sale = _dec(order.get("total_krw"))
    fee_rate = default_commission_rate(mp)                       # 단일 소스(채널 수수료)
    pg = _DEFAULT_PG_FEE if mp in ("kohganemultishop", "shopify") else Decimal("0")
    shipping = _dec(order.get("shipping_fee_krw")) or Decimal("0")
    cost = resolve_order_cost(order, lookup_fn=lookup_fn)

    missing = []
    if sale is None or sale <= 0:
        missing.append("판매가")
    if not cost.get("found"):
        missing.append("원가")
    base = {"order_id": order.get("order_id"), "marketplace": mp,
            "sale_krw": (int(sale) if sale is not None else None),
            "fee_rate_pct": float(fee_rate + pg),
            "shipping_fee_krw": int(shipping),
            "cost_source": cost.get("source")}
    if missing:
        return {**base, "complete": False, "net_krw": None, "margin_pct": None,
                "landed_cost_krw": None, "missing": missing,
                "reason": cost.get("reason") if "원가" in missing else "판매가 미상"}

    calc = calc or MarginCalculator()
    if cost["source"] == "order":                               # 이미 원화 랜딩코스트 확정
        landed = cost["landed_cost_krw"] + shipping
        net_krw, margin_pct = MarginCalculator._calc_margin(sale, landed, (fee_rate + pg) / Decimal("100"))
        fx_source = "order-landed"
    else:                                                        # 매입가+통화 → 엔진이 환율·관부가세·랜딩 산출
        ci = CostInput(buy_price=cost["buy_price"], buy_currency=cost["buy_currency"], qty=cost["qty"],
                       domestic_shipping=shipping)
        mi = MarketInput(marketplace=mp, commission_rate=fee_rate, pg_fee_rate=pg,
                         target_margin_pct=target_margin_pct)
        res = calc.calculate(ci, mi, sell_price=sale)
        net_krw, margin_pct, landed = res.actual_margin_krw, res.actual_margin_pct, res.total_landed_cost
        fx_source = (res.fx_used or {}).get("source", "default")
    return {**base, "complete": True, "net_krw": int(net_krw), "margin_pct": float(margin_pct),
            "landed_cost_krw": int(landed), "fx_source": fx_source, "missing": []}


def net_profit_summary(orders, *, calc=None, lookup_fn=None) -> dict:
    """주문 목록 → 순이익 요약. 집계는 **complete 주문만**(미입력은 별도 카운트·행 표기, 가짜 합산 0)."""
    calc = calc or None
    rows = [order_net_profit(o, calc=calc, lookup_fn=lookup_fn) for o in (orders or [])]
    complete = [r for r in rows if r["complete"]]
    total_sales = sum(r["sale_krw"] for r in complete) if complete else 0
    total_net = sum(r["net_krw"] for r in complete) if complete else 0
    avg_margin = (round(sum(r["margin_pct"] for r in complete) / len(complete), 2) if complete else None)
    return {
        "rows": rows,
        "order_count": len(rows),
        "complete_count": len(complete),
        "incomplete_count": len(rows) - len(complete),
        "total_sales_krw": total_sales,
        "total_net_krw": total_net,
        "avg_margin_pct": avg_margin,          # complete 없으면 None(미입력 — 가짜 0 아님)
    }
