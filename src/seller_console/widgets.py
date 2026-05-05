"""src/seller_console/widgets.py — 셀러 대시보드 위젯 데이터 빌더 (Phase 122).

각 위젯에 필요한 데이터를 data_aggregator에서 수집해 프론트엔드용 딕셔너리로 변환.
모든 위젯은 graceful fallback: 오류 시 "준비 중" 반환.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from .data_aggregator import (
    get_auto_purchase_queue,
    get_collect_queue_status,
    get_fx_rates,
    get_market_product_status,
    get_returns_cs_status,
    get_sourcing_alerts,
    get_today_kpi,
)

logger = logging.getLogger(__name__)

_NOT_READY = {"status": "준비 중", "is_mock": True}


def _safe_call(func, *args, **kwargs) -> Dict[str, Any]:
    """함수 호출 시 예외 발생 시 _NOT_READY 반환."""
    try:
        result = func(*args, **kwargs)
        return result if isinstance(result, dict) else _NOT_READY
    except Exception as exc:
        logger.warning("위젯 데이터 로드 실패 (%s): %s", func.__name__, exc)
        return dict(_NOT_READY)


def build_kpi_widget() -> Dict[str, Any]:
    """오늘 KPI 카드 위젯 데이터."""
    data = _safe_call(get_today_kpi)
    return {
        "title": "오늘 KPI",
        "type": "kpi",
        "data": data,
    }


def build_collect_queue_widget() -> Dict[str, Any]:
    """수집 큐 상태 위젯 데이터."""
    data = _safe_call(get_collect_queue_status)
    return {
        "title": "수집 큐",
        "type": "queue",
        "data": data,
    }


def build_market_status_widget() -> Dict[str, Any]:
    """마켓별 상품 상태 위젯 데이터.

    MarketStatusService (Sheets 어댑터 우선)에서 데이터를 가져온다.
    서비스 로드 실패 시 data_aggregator mock으로 graceful 폴백.
    """
    try:
        from .market_status_service import MarketStatusService
        svc = MarketStatusService()
        result = svc.get_all()
        data = result.to_legacy_dict()
    except Exception as exc:
        logger.warning("MarketStatusService 로드 실패 (mock 폴백): %s", exc)
        data = _safe_call(get_market_product_status)
    return {
        "title": "마켓 상품 현황",
        "type": "market_status",
        "data": data,
    }


def build_sourcing_alerts_widget() -> Dict[str, Any]:
    """소싱처 알림 위젯 데이터."""
    data = _safe_call(get_sourcing_alerts)
    return {
        "title": "소싱처 알림",
        "type": "alerts",
        "data": data,
    }


def build_returns_cs_widget() -> Dict[str, Any]:
    """반품/CS 대기 위젯 데이터."""
    data = _safe_call(get_returns_cs_status)
    return {
        "title": "반품/CS 대기",
        "type": "returns_cs",
        "data": data,
    }


def build_auto_purchase_widget() -> Dict[str, Any]:
    """자동 구매 큐 위젯 데이터."""
    data = _safe_call(get_auto_purchase_queue)
    return {
        "title": "자동 구매 큐",
        "type": "auto_purchase",
        "data": data,
    }


def build_fx_widget() -> Dict[str, Any]:
    """환율 위젯 데이터.

    실시간 환율 사용 가능 시 is_mock=False + source 표시.
    """
    data = _safe_call(get_fx_rates)
    # 실제 데이터인 경우에만 mock 라벨 제거
    is_live = not data.get("is_mock", True)
    return {
        "title": "환율",
        "type": "fx",
        "data": data,
        "live": is_live,
    }


def build_orders_kpi_widget() -> Dict[str, Any]:
    """주문 KPI 위젯 데이터."""
    try:
        from .orders.sync_service import OrderSyncService
        svc = OrderSyncService()
        data = svc.kpi_summary()
        # 위젯 공통 is_mock 플래그 추가
        data.setdefault("is_mock", data.get("source") != "sheets")
    except Exception as exc:
        logger.warning("orders KPI 위젯 로드 실패: %s", exc)
        data = dict(_NOT_READY)
    return {
        "title": "주문 현황",
        "type": "orders_kpi",
        "data": data,
    }


def build_all_widgets() -> List[Dict[str, Any]]:
    """모든 대시보드 위젯 데이터 목록 반환."""
    return [
        build_kpi_widget(),
        build_collect_queue_widget(),
        build_market_status_widget(),
        build_sourcing_alerts_widget(),
        build_returns_cs_widget(),
        build_auto_purchase_widget(),
        build_fx_widget(),
        build_orders_kpi_widget(),
    ]
