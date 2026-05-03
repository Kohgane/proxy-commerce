"""src/seller_console/data_aggregator.py — 셀러 대시보드 데이터 수집기 (Phase 122).

기존 모듈에서 데이터를 graceful import로 수집.
모듈 미존재 또는 오류 시 mock 데이터 반환.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 환율 네트워크 차단 환경변수 (CD Staging 안정화)
_FX_DISABLE_NETWORK = os.getenv("FX_DISABLE_NETWORK", "0") == "1"


def _safe_import(module_path: str, attr: str = None) -> Optional[Any]:
    """모듈/속성을 안전하게 임포트. 실패 시 None 반환."""
    try:
        import importlib
        mod = importlib.import_module(module_path)
        if attr:
            return getattr(mod, attr, None)
        return mod
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 오늘 KPI 데이터
# ---------------------------------------------------------------------------

def get_today_kpi() -> Dict[str, Any]:
    """오늘 KPI 카드 데이터 반환 (주문수, GMV, 마진, 신규 수집).

    Phase 33/97 (pricing), Phase 114 (seller_report) 모듈 재사용.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    mock_data = {
        "date": today,
        "order_count": 12,
        "gmv_krw": 1_850_000,
        "margin_krw": 340_000,
        "margin_pct": 18.4,
        "new_products_collected": 5,
        "is_mock": True,
    }

    try:
        # Phase 114: seller_report 모듈에서 오늘 요약 조회 시도
        seller_report_mod = _safe_import("src.seller_report")
        if seller_report_mod and hasattr(seller_report_mod, "get_daily_summary"):
            summary = seller_report_mod.get_daily_summary(today)
            if summary:
                mock_data.update(summary)
                mock_data["is_mock"] = False
    except Exception as exc:
        logger.debug("seller_report 데이터 조회 실패 (mock 사용): %s", exc)

    return mock_data


# ---------------------------------------------------------------------------
# 수집 큐 상태
# ---------------------------------------------------------------------------

def get_collect_queue_status() -> Dict[str, Any]:
    """수집 큐 상태 반환 (대기/번역중/검수중/업로드완료).

    Phase 17 (collectors) 모듈 재사용.
    """
    mock_data = {
        "pending": 3,
        "translating": 1,
        "reviewing": 2,
        "uploaded": 8,
        "total": 14,
        "is_mock": True,
    }

    try:
        collectors_mod = _safe_import("src.collectors")
        if collectors_mod and hasattr(collectors_mod, "get_queue_status"):
            status = collectors_mod.get_queue_status()
            if status:
                mock_data.update(status)
                mock_data["is_mock"] = False
    except Exception as exc:
        logger.debug("collectors 큐 상태 조회 실패 (mock 사용): %s", exc)

    return mock_data


# ---------------------------------------------------------------------------
# 마켓별 상품 상태
# ---------------------------------------------------------------------------

def get_market_product_status() -> Dict[str, Any]:
    """마켓별 상품 상태 반환 (쿠팡/스마트스토어/11번가 활성/품절/문제).

    Phase 71 (marketplace_sync), Phase 109 (channel_sync) 모듈 재사용.
    """
    mock_data = {
        "markets": [
            {
                "market": "coupang",
                "label": "쿠팡",
                "active": 45,
                "out_of_stock": 3,
                "error": 1,
                "total": 49,
            },
            {
                "market": "smartstore",
                "label": "스마트스토어",
                "active": 38,
                "out_of_stock": 5,
                "error": 0,
                "total": 43,
            },
            {
                "market": "elevenst",
                "label": "11번가",
                "active": 22,
                "out_of_stock": 2,
                "error": 2,
                "total": 26,
            },
        ],
        "is_mock": True,
    }

    try:
        channel_sync_mod = _safe_import("src.channel_sync")
        if channel_sync_mod and hasattr(channel_sync_mod, "get_market_status"):
            status = channel_sync_mod.get_market_status()
            if status:
                mock_data.update(status)
                mock_data["is_mock"] = False
    except Exception as exc:
        logger.debug("channel_sync 마켓 상태 조회 실패 (mock 사용): %s", exc)

    return mock_data


# ---------------------------------------------------------------------------
# 소싱처 알림
# ---------------------------------------------------------------------------

def get_sourcing_alerts() -> Dict[str, Any]:
    """소싱처 알림 반환 (가격 변동/재고 변동/신상).

    Phase 108 (source_monitor) 모듈 재사용.
    """
    mock_data = {
        "alerts": [
            {
                "type": "price_change",
                "label": "가격 변동",
                "product": "[Mock] Porter Tank — 가격 +12%",
                "source": "porter",
                "severity": "warning",
            },
            {
                "type": "out_of_stock",
                "label": "품절",
                "product": "[Mock] Alo Yoga Legging XS — 재고 없음",
                "source": "alo",
                "severity": "error",
            },
            {
                "type": "new_product",
                "label": "신상품",
                "product": "[Mock] Lululemon 2026 FW 신상 10종 감지",
                "source": "lululemon",
                "severity": "info",
            },
        ],
        "count": 3,
        "is_mock": True,
    }

    try:
        source_monitor_mod = _safe_import("src.source_monitor")
        if source_monitor_mod and hasattr(source_monitor_mod, "get_recent_alerts"):
            alerts = source_monitor_mod.get_recent_alerts(limit=5)
            if alerts:
                mock_data["alerts"] = alerts
                mock_data["count"] = len(alerts)
                mock_data["is_mock"] = False
    except Exception as exc:
        logger.debug("source_monitor 알림 조회 실패 (mock 사용): %s", exc)

    return mock_data


# ---------------------------------------------------------------------------
# 반품/CS 대기
# ---------------------------------------------------------------------------

def get_returns_cs_status() -> Dict[str, Any]:
    """반품/CS 대기 현황 반환.

    Phase 118 (returns_automation) 모듈 재사용.
    """
    mock_data = {
        "pending_returns": 2,
        "pending_cs": 4,
        "escalated": 1,
        "is_mock": True,
    }

    try:
        returns_mod = _safe_import("src.returns_automation")
        if returns_mod and hasattr(returns_mod, "get_pending_summary"):
            summary = returns_mod.get_pending_summary()
            if summary:
                mock_data.update(summary)
                mock_data["is_mock"] = False
    except Exception as exc:
        logger.debug("returns_automation 상태 조회 실패 (mock 사용): %s", exc)

    return mock_data


# ---------------------------------------------------------------------------
# 자동 구매 큐
# ---------------------------------------------------------------------------

def get_auto_purchase_queue() -> Dict[str, Any]:
    """자동 구매 큐 반환.

    Phase 96/101 (auto_purchase) 모듈 재사용.
    """
    mock_data = {
        "waiting": 3,
        "processing": 1,
        "completed_today": 7,
        "failed": 0,
        "is_mock": True,
    }

    try:
        auto_purchase_mod = _safe_import("src.auto_purchase")
        if auto_purchase_mod and hasattr(auto_purchase_mod, "get_queue_summary"):
            summary = auto_purchase_mod.get_queue_summary()
            if summary:
                mock_data.update(summary)
                mock_data["is_mock"] = False
    except Exception as exc:
        logger.debug("auto_purchase 큐 조회 실패 (mock 사용): %s", exc)

    return mock_data


# ---------------------------------------------------------------------------
# 환율 데이터
# ---------------------------------------------------------------------------

def get_fx_rates() -> Dict[str, Any]:
    """환율 데이터 반환.

    Phase 19 (fx) 모듈 재사용. FX_DISABLE_NETWORK 가드 적용.
    실시간 환율 사용 가능 시 source='realtime', 아니면 'env' 또는 'default'.
    """
    mock_data = {
        "USD": 1370.5,
        "JPY": 9.12,
        "CNY": 188.4,
        "EUR": 1485.0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "is_mock": True,
        "source": "default",
    }

    if _FX_DISABLE_NETWORK:
        logger.debug("FX_DISABLE_NETWORK 활성화 — mock 환율 사용")
        return mock_data

    try:
        from src.fx.provider import FXProvider  # type: ignore
        provider = FXProvider()
        rates = provider.get_rates()
        if rates:
            result = dict(mock_data)
            if "USDKRW" in rates:
                result["USD"] = float(rates["USDKRW"])
            if "JPYKRW" in rates:
                result["JPY"] = float(rates["JPYKRW"])
            if "EURKRW" in rates:
                result["EUR"] = float(rates["EURKRW"])
            if "CNYKRW" in rates:
                result["CNY"] = float(rates["CNYKRW"])
            result["updated_at"] = rates.get("fetched_at", datetime.now(timezone.utc).isoformat())
            result["source"] = rates.get("provider", "realtime")
            result["is_mock"] = False
            return result
    except Exception as exc:
        logger.debug("FXProvider 환율 조회 실패 (mock 사용): %s", exc)

    # 환경변수 폴백
    env_usd = os.getenv("FX_USDKRW")
    env_jpy = os.getenv("FX_JPYKRW")
    env_eur = os.getenv("FX_EURKRW")
    env_cny = os.getenv("FX_CNYKRW")
    if any([env_usd, env_jpy, env_eur, env_cny]):
        result = dict(mock_data)
        if env_usd:
            result["USD"] = float(env_usd)
        if env_jpy:
            result["JPY"] = float(env_jpy)
        if env_eur:
            result["EUR"] = float(env_eur)
        if env_cny:
            result["CNY"] = float(env_cny)
        result["source"] = "env"
        result["is_mock"] = False
        return result

    return mock_data


# ---------------------------------------------------------------------------
# 마진 계산
# ---------------------------------------------------------------------------

def calculate_margin(
    buy_price: float,
    currency: str,
    shipping_fee: float = 0.0,
    customs_rate: float = 0.0,
    market_fee_rate: float = 0.0,
    pg_fee_rate: float = 0.0,
    target_margin_pct: float = 30.0,
    fx_rates: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """마진 계산.

    Args:
        buy_price: 매입가 (원래 통화)
        currency: 매입 통화 코드 (USD/JPY/CNY/EUR)
        shipping_fee: 배송비 (KRW)
        customs_rate: 관세율 (%)
        market_fee_rate: 마켓 수수료율 (%)
        pg_fee_rate: PG 수수료율 (%)
        target_margin_pct: 목표 마진율 (%)
        fx_rates: 환율 딕셔너리 (None이면 get_fx_rates() 사용)

    Returns:
        계산 결과 딕셔너리
    """
    if fx_rates is None:
        fx_rates = get_fx_rates()

    rate = fx_rates.get(currency, 1.0)
    buy_price_krw = buy_price * rate

    # 원가 계산
    customs_amount = buy_price_krw * (customs_rate / 100)
    cost_krw = buy_price_krw + customs_amount + shipping_fee

    # 목표 마진 기준 판매가 계산
    # cost = sell * (1 - market_fee - pg_fee) * (1 - margin)
    # sell = cost / ((1 - market_fee_rate/100 - pg_fee_rate/100) * (1 - target_margin_pct/100))
    denominator = (1 - market_fee_rate / 100 - pg_fee_rate / 100) * (1 - target_margin_pct / 100)
    if denominator <= 0:
        denominator = 0.01  # 0 나누기 방지

    sell_price_krw = cost_krw / denominator

    # 실제 마진 계산
    actual_revenue = sell_price_krw * (1 - market_fee_rate / 100 - pg_fee_rate / 100)
    actual_margin_krw = actual_revenue - cost_krw
    actual_margin_pct = (actual_margin_krw / sell_price_krw * 100) if sell_price_krw > 0 else 0

    # 손익분기점
    breakeven_krw = cost_krw / (1 - market_fee_rate / 100 - pg_fee_rate / 100)

    return {
        "buy_price": buy_price,
        "currency": currency,
        "buy_price_krw": round(buy_price_krw),
        "customs_amount_krw": round(customs_amount),
        "shipping_fee_krw": round(shipping_fee),
        "cost_krw": round(cost_krw),
        "sell_price_krw": round(sell_price_krw),
        "actual_margin_krw": round(actual_margin_krw),
        "actual_margin_pct": round(actual_margin_pct, 2),
        "breakeven_krw": round(breakeven_krw),
        "target_margin_pct": target_margin_pct,
        "fx_rate_used": rate,
    }
