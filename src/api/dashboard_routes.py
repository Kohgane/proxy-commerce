"""src/api/dashboard_routes.py — 관리자 대시보드 REST API 엔드포인트.

Flask Blueprint으로 구현된 대시보드 API.

엔드포인트:
  GET /api/dashboard/summary    — 전체 운영 현황 요약
  GET /api/dashboard/orders     — 주문 목록 (status 필터, 페이지네이션)
  GET /api/dashboard/orders/<id> — 주문 상세
  GET /api/dashboard/revenue    — 매출 데이터 (period 파라미터)
  GET /api/dashboard/inventory  — 재고 현황 (low_stock 필터)
  GET /api/dashboard/fx         — 환율 현황 + 변동률
  GET /api/dashboard/health     — 시스템 상태 종합

환경변수:
  DASHBOARD_API_ENABLED  — API 활성화 여부 (기본 "1")
  DASHBOARD_API_KEY      — API 인증 키
  GOOGLE_SHEET_ID        — Google Sheets ID
"""

import datetime
import logging
import os

from flask import Blueprint, jsonify, request

from .auth_middleware import require_api_key
from .serializers import serialize_order, serialize_product, serialize_fx_rate, paginate

logger = logging.getLogger(__name__)

_API_ENABLED = os.getenv("DASHBOARD_API_ENABLED", "1") == "1"
_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/api/dashboard")


def _check_enabled():
    """API가 비활성화된 경우 503 응답을 반환한다."""
    if not _API_ENABLED:
        return jsonify({"error": "Dashboard API is disabled"}), 503
    return None


def _load_orders() -> list:
    """Google Sheets에서 주문 목록을 로드한다."""
    try:
        from ..utils.sheets import open_sheet
        ws = open_sheet(_SHEET_ID, os.getenv("ORDERS_WORKSHEET", "orders"))
        return ws.get_all_records()
    except Exception as exc:
        logger.warning("주문 데이터 로드 실패: %s", exc)
        return []


def _load_catalog() -> list:
    """Google Sheets에서 카탈로그 목록을 로드한다."""
    try:
        from ..utils.sheets import open_sheet
        ws = open_sheet(_SHEET_ID, os.getenv("WORKSHEET", "catalog"))
        return ws.get_all_records()
    except Exception as exc:
        logger.warning("카탈로그 데이터 로드 실패: %s", exc)
        return []


def _get_fx_rates() -> dict:
    """현재 환율을 조회한다."""
    try:
        from ..fx.provider import FXProvider
        fetcher = FXProvider()
        return fetcher.get_rates()
    except Exception as exc:
        logger.warning("환율 데이터 로드 실패: %s", exc)
        return {}


@dashboard_bp.get("/summary")
@require_api_key
def summary():
    """전체 운영 현황 요약을 반환한다."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    orders = _load_orders()
    catalog = _load_catalog()
    fx = _get_fx_rates()

    total_orders = len(orders)
    pending = sum(1 for o in orders if str(o.get("status", "")).lower() in ("paid", "pending"))
    shipped = sum(1 for o in orders if str(o.get("status", "")).lower() == "shipped")
    completed = sum(1 for o in orders if str(o.get("status", "")).lower() == "completed")

    try:
        total_revenue = sum(
            float(o.get("sell_price_krw", 0) or 0)
            for o in orders
            if str(o.get("status", "")).lower() not in ("cancelled", "refunded")
        )
    except (TypeError, ValueError):
        total_revenue = 0.0

    low_stock_count = sum(
        1 for c in catalog
        if int(c.get("stock", 0) or 0) <= int(os.getenv("LOW_STOCK_THRESHOLD", "3"))
    )

    return jsonify({
        "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "orders": {
            "total": total_orders,
            "pending": pending,
            "shipped": shipped,
            "completed": completed,
        },
        "revenue": {
            "total_krw": round(total_revenue, 2),
        },
        "inventory": {
            "total_products": len(catalog),
            "low_stock_count": low_stock_count,
        },
        "fx": {pair: float(rate) for pair, rate in fx.items() if not callable(rate)},
    })


@dashboard_bp.get("/orders")
@require_api_key
def orders_list():
    """주문 목록을 반환한다 (status 필터, 페이지네이션)."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    status_filter = request.args.get("status", "").lower()
    try:
        page = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 20)), 100)
    except (ValueError, TypeError):
        page, per_page = 1, 20

    orders = _load_orders()
    if status_filter:
        orders = [o for o in orders if str(o.get("status", "")).lower() == status_filter]

    serialized = [serialize_order(o) for o in orders]
    result = paginate(serialized, page=page, per_page=per_page)
    return jsonify(result)


@dashboard_bp.get("/orders/<order_id>")
@require_api_key
def order_detail(order_id: str):
    """주문 상세 정보를 반환한다."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    orders = _load_orders()
    for o in orders:
        if str(o.get("order_id", "")) == order_id or str(o.get("order_number", "")) == order_id:
            return jsonify(serialize_order(o))

    return jsonify({"error": "Order not found", "order_id": order_id}), 404


@dashboard_bp.get("/revenue")
@require_api_key
def revenue():
    """매출 데이터를 반환한다 (period: daily/weekly/monthly)."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    period = request.args.get("period", "daily").lower()
    if period not in ("daily", "weekly", "monthly"):
        period = "daily"

    orders = _load_orders()
    now = datetime.datetime.now(tz=datetime.timezone.utc)

    if period == "daily":
        cutoff = now - datetime.timedelta(days=1)
    elif period == "weekly":
        cutoff = now - datetime.timedelta(weeks=1)
    else:
        cutoff = now - datetime.timedelta(days=30)

    revenue_data = []
    for o in orders:
        order_date_str = str(o.get("order_date", ""))
        try:
            order_date = datetime.datetime.fromisoformat(order_date_str.replace("Z", "+00:00"))
            if order_date >= cutoff and str(o.get("status", "")).lower() not in ("cancelled", "refunded"):
                revenue_data.append({
                    "order_id": o.get("order_id", ""),
                    "order_date": order_date_str,
                    "sell_price_krw": float(o.get("sell_price_krw", 0) or 0),
                    "margin_pct": float(o.get("margin_pct", 0) or 0),
                    "vendor": o.get("vendor", ""),
                })
        except (ValueError, TypeError):
            continue

    total_revenue = sum(r["sell_price_krw"] for r in revenue_data)
    avg_margin = (
        round(sum(r["margin_pct"] for r in revenue_data) / len(revenue_data), 2)
        if revenue_data else 0.0
    )

    return jsonify({
        "period": period,
        "from": cutoff.isoformat(),
        "to": now.isoformat(),
        "total_revenue_krw": round(total_revenue, 2),
        "order_count": len(revenue_data),
        "avg_margin_pct": avg_margin,
        "orders": revenue_data,
    })


@dashboard_bp.get("/inventory")
@require_api_key
def inventory():
    """재고 현황을 반환한다 (low_stock 필터)."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    low_stock_only = request.args.get("low_stock", "").lower() in ("1", "true", "yes")
    threshold = int(os.getenv("LOW_STOCK_THRESHOLD", "3"))

    try:
        page = int(request.args.get("page", 1))
        per_page = min(int(request.args.get("per_page", 20)), 100)
    except (ValueError, TypeError):
        page, per_page = 1, 20

    catalog = _load_catalog()
    if low_stock_only:
        catalog = [c for c in catalog if int(c.get("stock", 0) or 0) <= threshold]

    serialized = [serialize_product(c) for c in catalog]
    result = paginate(serialized, page=page, per_page=per_page)
    result["low_stock_threshold"] = threshold
    return jsonify(result)


@dashboard_bp.get("/fx")
@require_api_key
def fx_status():
    """환율 현황과 변동률을 반환한다."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    fx = _get_fx_rates()
    rates = []
    for pair, rate in fx.items():
        if not callable(rate):
            rates.append(serialize_fx_rate(pair, rate))

    return jsonify({
        "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "rates": rates,
        "count": len(rates),
    })


@dashboard_bp.get("/health")
@require_api_key
def api_health():
    """시스템 상태를 종합하여 반환한다."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    checks = {}

    # Google Sheets 연결 확인
    try:
        from ..utils.sheets import open_sheet
        if _SHEET_ID:
            open_sheet(_SHEET_ID, os.getenv("WORKSHEET", "catalog"))
            checks["google_sheets"] = True
        else:
            checks["google_sheets"] = False
    except Exception:
        checks["google_sheets"] = False

    # 환율 서비스 확인
    try:
        from ..fx.provider import FXProvider
        FXProvider().get_rates()
        checks["fx_service"] = True
    except Exception:
        checks["fx_service"] = False

    all_ok = all(checks.values())
    return jsonify({
        "status": "ok" if all_ok else "degraded",
        "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "checks": checks,
    }), 200 if all_ok else 503
