"""src/seller_console/views.py — 셀러 콘솔 Flask Blueprint (Phase 127).

라우트:
  GET  /seller/              → 메인 대시보드 (리다이렉트)
  GET  /seller/dashboard     → 메인 대시보드
  GET  /seller/collect       → 수동 수집기 페이지
  POST /seller/collect/preview → URL → 메타데이터 추출 결과 (JSON)
  POST /seller/collect/upload  → 마켓 업로드 트리거 (JSON)
  GET  /seller/pricing       → 마진 계산기
  POST /seller/pricing/calc  → 단일 마켓 마진 계산 (JSON)
  POST /seller/pricing/compare → 여러 마켓 비교 계산 (JSON)
  GET  /seller/market-status → 마켓 현황 (기존, 리다이렉트)
  GET  /seller/markets       → 마켓 현황 상세 페이지 (Phase 127)
  GET  /seller/markets/status → JSON: 모든 마켓 상태 (Phase 127)
  POST /seller/markets/sync  → 라이브 동기화 트리거 (Phase 127)
  GET  /seller/health        → 셀러 콘솔 헬스체크
  POST /api/v1/pricing/calculate → 공개 API (인증 stub)

인증: 현재 stub 미들웨어만 (다음 PR에서 Phase 24 OAuth 연결 예정).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

logger = logging.getLogger(__name__)

# Blueprint 정의
bp = Blueprint(
    "seller_console",
    __name__,
    url_prefix="/seller",
    template_folder="templates",
    static_folder="static",
    static_url_path="/seller/static",
)

# ---------------------------------------------------------------------------
# 인증 stub — Phase 24 OAuth 연결 전까지 환경변수로 제어
# ---------------------------------------------------------------------------
_AUTH_ENABLED = os.getenv("SELLER_CONSOLE_AUTH", "0") == "1"


def _check_auth() -> bool:
    """인증 확인 stub. SELLER_CONSOLE_AUTH=1 시 추후 실제 인증으로 교체."""
    if not _AUTH_ENABLED:
        return True
    # TODO: Phase 24 OAuth 미들웨어 연결
    return True


# ---------------------------------------------------------------------------
# 헬퍼 — graceful import
# ---------------------------------------------------------------------------

def _get_widgets() -> list:
    """위젯 데이터 목록 조회 (graceful import)."""
    try:
        from .widgets import build_all_widgets
        return build_all_widgets()
    except Exception as exc:
        logger.warning("위젯 로드 실패: %s", exc)
        return []


def _get_collector_service():
    """ManualCollectorService 인스턴스 반환 (graceful import)."""
    try:
        from .manual_collector import ManualCollectorService
        return ManualCollectorService()
    except Exception as exc:
        logger.warning("ManualCollectorService 로드 실패: %s", exc)
        return None


def _get_upload_dispatcher():
    """UploadDispatcher 인스턴스 반환 (graceful import)."""
    try:
        from .upload_dispatcher import UploadDispatcher
        return UploadDispatcher()
    except Exception as exc:
        logger.warning("UploadDispatcher 로드 실패: %s", exc)
        return None


def _get_trust_checker():
    """TaobaoSellerTrustChecker 인스턴스 반환 (graceful import)."""
    try:
        from .seller_trust import TaobaoSellerTrustChecker
        return TaobaoSellerTrustChecker()
    except Exception as exc:
        logger.warning("TaobaoSellerTrustChecker 로드 실패: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 라우트
# ---------------------------------------------------------------------------

@bp.get("/")
def index():
    """루트 → 대시보드 리다이렉트."""
    return redirect(url_for("seller_console.dashboard"))


@bp.get("/dashboard")
def dashboard():
    """메인 셀러 대시보드."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    widgets = _get_widgets()
    return render_template("dashboard.html", widgets=widgets, page="dashboard")


@bp.get("/collect")
def collect():
    """수동 수집기 페이지 (Phase 128: API 상태 포함)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    try:
        from src.utils.env_catalog import get_api_status
        api_status = get_api_status()
    except Exception as exc:
        logger.warning("API 상태 로드 실패: %s", exc)
        api_status = []

    return render_template("manual_collect.html", page="collect", api_status=api_status)


@bp.post("/collect/preview")
def collect_preview():
    """URL → 메타데이터 추출 결과 (JSON).

    Phase 128: 실 수집기 우선 시도 → 기존 ManualCollectorService 폴백.

    Request body: {"url": "https://..."}
    Response: {"ok": true, "draft": {...}}
    """
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"ok": False, "error": "URL이 필요합니다."}), 400

    # Phase 128: 실 수집기 dispatcher 우선 사용
    try:
        from src.seller_console.collectors.dispatcher import collect as dispatcher_collect
        result = dispatcher_collect(url)
        if result.success:
            # 기존 draft 형식과 호환되도록 변환
            draft_dict = result.to_dict()
            # 하위 호환 필드 추가
            draft_dict.update({
                "title_en": result.title or "",
                "title_ko": result.title or "",
                "price_original": float(result.price) if result.price else 0.0,
                "is_mock": False,
                "adapter_used": result.source,
            })
            return jsonify({
                "ok": True,
                "draft": draft_dict,
                "trust": None,
                "source": result.source,
                "warnings": result.warnings,
            })
    except Exception as exc:
        logger.debug("실 수집기 실패, 기존 수집기로 폴백: %s", exc)

    # 기존 ManualCollectorService 폴백
    collector = _get_collector_service()
    if collector is None:
        return jsonify({"ok": False, "error": "수집기 모듈 준비 중입니다."}), 503

    try:
        draft = collector.extract(url)
        draft_dict = draft.to_dict()

        # 타오바오 URL인 경우 셀러 신뢰도 자동 추가
        trust_info = None
        if draft.seller_id and draft.source in ("taobao", "alibaba"):
            checker = _get_trust_checker()
            if checker and draft.seller_id:
                trust_score = checker.evaluate(draft.seller_id)
                trust_info = trust_score.to_dict()

        return jsonify({
            "ok": True,
            "draft": draft_dict,
            "trust": trust_info,
        })
    except ValueError:
        return jsonify({"ok": False, "error": "URL 형식이 올바르지 않습니다."}), 400
    except Exception as exc:
        logger.warning("수집기 오류: %s", exc)
        return jsonify({"ok": False, "error": "추출 중 오류가 발생했습니다."}), 500


@bp.post("/collect/upload")
def collect_upload():
    """마켓 업로드 트리거 (JSON).

    Request body: {"product": {...}, "markets": ["coupang", "smartstore"]}
    Response: {"ok": true, "result": {...}}
    """
    data = request.get_json(force=True, silent=True) or {}
    product_data = data.get("product") or {}
    markets = data.get("markets") or []

    if not product_data:
        return jsonify({"ok": False, "error": "상품 데이터가 필요합니다."}), 400

    if not markets:
        return jsonify({"ok": False, "error": "업로드 대상 마켓을 선택하세요."}), 400

    dispatcher = _get_upload_dispatcher()
    if dispatcher is None:
        return jsonify({"ok": False, "error": "업로드 디스패처 준비 중입니다."}), 503

    try:
        result = dispatcher.dispatch(product_data, markets)
        return jsonify({"ok": True, "result": result.to_dict()})
    except Exception as exc:
        logger.warning("업로드 디스패처 오류: %s", exc)
        return jsonify({"ok": False, "error": "업로드 중 오류가 발생했습니다."}), 500


@bp.post("/collect/save")
def collect_save():
    """수집 결과를 Sheets catalog 워크시트에 저장 (Phase 128).

    Request body: 수집 결과 dict
    Response: {"ok": true, "saved": true}
    """
    payload = request.get_json(force=True, silent=True) or {}
    if not payload:
        return jsonify({"ok": False, "error": "저장할 데이터가 없습니다."}), 400

    try:
        from .market_status_sheets import MarketStatusSheetsAdapter
        from .market_status import MarketStatusItem
        from datetime import datetime

        adapter = MarketStatusSheetsAdapter()
        item = MarketStatusItem(
            marketplace=payload.get("marketplace", "collected"),
            product_id=payload.get("sku") or payload.get("asin") or f"col_{int(datetime.now().timestamp())}",
            state="active",
            sku=payload.get("sku") or payload.get("asin"),
            title=payload.get("title"),
            price_krw=int(float(payload["price"])) if payload.get("price") else None,
            last_synced_at=datetime.now(),
        )
        saved = adapter.upsert_item(item)
        return jsonify({"ok": True, "saved": saved})
    except Exception as exc:
        logger.warning("collect_save 오류: %s", exc)
        return jsonify({"ok": False, "error": "저장 중 오류가 발생했습니다."}), 500


@bp.get("/catalog")
def catalog():
    """상품 카탈로그 페이지 (Phase 128) — Sheets catalog 워크시트 뷰."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    page_num = request.args.get("page", 1, type=int)
    per_page = 50

    items = []
    total = 0
    source = "mock"
    error_msg = None

    try:
        from .market_status_sheets import MarketStatusSheetsAdapter
        adapter = MarketStatusSheetsAdapter()
        result = adapter.fetch_all()
        all_items = result.items
        source = result.source
        total = len(all_items)
        start = (page_num - 1) * per_page
        items = all_items[start:start + per_page]
    except Exception as exc:
        logger.warning("카탈로그 데이터 로드 실패: %s", exc)
        error_msg = str(exc)

    total_pages = max(1, (total + per_page - 1) // per_page)

    return render_template(
        "catalog.html",
        items=items,
        page="catalog",
        current_page=page_num,
        total_pages=total_pages,
        total=total,
        source=source,
        error_msg=error_msg,
    )


def _get_order_sync_service():
    """OrderSyncService 인스턴스 반환 (graceful import)."""
    try:
        from .orders.sync_service import OrderSyncService
        return OrderSyncService()
    except Exception as exc:
        logger.warning("OrderSyncService 로드 실패: %s", exc)
        return None


@bp.get("/orders")
def orders():
    """주문 관리 페이지 (Phase 129 — 실연동)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    filters = {
        "marketplace": request.args.getlist("marketplace") or None,
        "status": request.args.get("status") or None,
        "search": request.args.get("search") or None,
        "date_from": request.args.get("date_from") or None,
        "date_to": request.args.get("date_to") or None,
    }
    # None 값 제거
    filters = {k: v for k, v in filters.items() if v}

    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    svc = _get_order_sync_service()
    order_list = []
    kpi = {"today_new": 0, "pending_ship": 0, "shipped": 0, "returned_exchanged": 0, "source": "none"}
    if svc:
        order_list = svc.list_orders(filters=filters, limit=limit, offset=offset)
        kpi = svc.kpi_summary()

    from .orders.tracking import COURIER_MAP
    order_dicts = [o.to_dict() for o in order_list]
    return render_template(
        "orders.html",
        page="orders",
        orders=order_dicts,
        kpi=kpi,
        filters=filters,
        limit=limit,
        offset=offset,
        couriers=list(COURIER_MAP.keys()),
    )


@bp.post("/orders/sync")
def orders_sync():
    """주문 동기화 트리거 (Phase 129).

    Response: {"ok": true, "results": {...}}
    """
    svc = _get_order_sync_service()
    if svc is None:
        return jsonify({"ok": False, "error": "OrderSyncService 준비 중입니다."}), 503

    try:
        results = svc.sync_all()
        return jsonify({"ok": True, "results": results})
    except Exception as exc:
        logger.warning("orders_sync 오류: %s", exc)
        return jsonify({"ok": False, "error": "동기화 중 오류가 발생했습니다."}), 500


@bp.get("/orders/<marketplace>/<order_id>")
def order_detail(marketplace: str, order_id: str):
    """주문 상세 조회 (JSON).

    Response: {"ok": true, "order": {...}}
    """
    svc = _get_order_sync_service()
    if svc is None:
        return jsonify({"ok": False, "error": "서비스 준비 중입니다."}), 503

    try:
        orders_list = svc.list_orders(
            filters={"marketplace": marketplace, "search": order_id},
            limit=1,
        )
        matched = [o for o in orders_list if o.order_id == order_id]
        if not matched:
            return jsonify({"ok": False, "error": "주문을 찾을 수 없습니다."}), 404
        return jsonify({"ok": True, "order": matched[0].to_dict()})
    except Exception as exc:
        logger.warning("order_detail 오류: %s", exc)
        return jsonify({"ok": False, "error": "조회 중 오류가 발생했습니다."}), 500


@bp.post("/orders/<marketplace>/<order_id>/tracking")
def order_tracking(marketplace: str, order_id: str):
    """운송장 등록 (Phase 129).

    Request body: {"courier": "CJ대한통운", "tracking_no": "1234567890"}
    Response: {"ok": true}
    """
    data = request.get_json(force=True, silent=True) or {}
    courier = (data.get("courier") or "").strip()
    tracking_no = (data.get("tracking_no") or "").strip()

    if not courier or not tracking_no:
        return jsonify({"ok": False, "error": "택배사와 운송장 번호를 입력하세요."}), 400

    svc = _get_order_sync_service()
    if svc is None:
        return jsonify({"ok": False, "error": "서비스 준비 중입니다."}), 503

    try:
        ok = svc.update_tracking(order_id, marketplace, courier, tracking_no)
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("order_tracking 오류: %s", exc)
        return jsonify({"ok": False, "error": "운송장 등록 중 오류가 발생했습니다."}), 500


@bp.post("/orders/bulk/tracking")
def orders_bulk_tracking():
    """일괄 운송장 등록 (Phase 129).

    Request body: {"items": [{"order_id": "...", "marketplace": "...", "courier": "...", "tracking_no": "..."}]}
    Response: {"ok": true, "results": [...]}
    """
    data = request.get_json(force=True, silent=True) or {}
    items = data.get("items") or []

    if not items:
        return jsonify({"ok": False, "error": "업데이트 항목이 없습니다."}), 400

    svc = _get_order_sync_service()
    if svc is None:
        return jsonify({"ok": False, "error": "서비스 준비 중입니다."}), 503

    results = []
    for item in items:
        try:
            ok = svc.update_tracking(
                item.get("order_id", ""),
                item.get("marketplace", ""),
                item.get("courier", ""),
                item.get("tracking_no", ""),
            )
            results.append({"order_id": item.get("order_id"), "ok": ok})
        except Exception as exc:
            results.append({"order_id": item.get("order_id"), "ok": False, "error": str(exc)})

    return jsonify({"ok": True, "results": results})


@bp.get("/orders/export.csv")
def orders_export_csv():
    """주문 목록 CSV 내보내기 (Phase 129)."""
    import csv
    import io

    svc = _get_order_sync_service()
    orders_list = svc.list_orders(limit=1000) if svc else []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "order_id", "marketplace", "status", "placed_at",
        "buyer_name_masked", "total_krw", "items_count",
        "courier", "tracking_no", "notes",
    ])
    for o in orders_list:
        writer.writerow([
            o.order_id, o.marketplace,
            o.status.value if hasattr(o.status, "value") else o.status,
            o.placed_at.isoformat() if o.placed_at else "",
            o.buyer_name_masked or "",
            str(o.total_krw),
            len(o.items),
            o.courier or "",
            o.tracking_no or "",
            o.notes or "",
        ])

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders.csv"},
    )


@bp.get("/api-status")
def api_status():
    """API 상태 페이지 (Phase 128)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    try:
        from src.utils.env_catalog import get_api_status as _get_api_status
        api_list = _get_api_status()
    except Exception as exc:
        logger.warning("API 상태 로드 실패: %s", exc)
        api_list = []

    return render_template("api_status.html", page="api_status", api_list=api_list)


@bp.get("/api-status/json")
def api_status_json():
    """API 상태 JSON 응답 (Phase 128)."""
    try:
        from src.utils.env_catalog import get_api_status as _get_api_status
        return jsonify({"ok": True, "apis": _get_api_status()})
    except Exception as exc:
        logger.warning("API 상태 JSON 오류: %s", exc)
        # 내부 오류 메시지를 외부에 노출하지 않음
        return jsonify({"ok": False, "error": "API 상태 로드 중 오류가 발생했습니다."}), 500


@bp.get("/pricing")
def pricing():
    """마진 계산기 페이지."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    all_marketplaces = [
        {"id": "coupang", "label": "쿠팡"},
        {"id": "smartstore", "label": "스마트스토어"},
        {"id": "11st", "label": "11번가"},
        {"id": "kohganemultishop", "label": "코가네멀티샵"},
        {"id": "shopify", "label": "Shopify"},
    ]
    return render_template(
        "pricing_console.html",
        page="pricing",
        all_marketplaces=all_marketplaces,
        default_currencies=["KRW", "USD", "JPY", "EUR", "CNY"],
        default_target_margin=22,
    )


@bp.post("/pricing/calc")
def pricing_calc():
    """단일 마켓 마진 계산 (JSON).

    Request body: 계산 파라미터
    Response: {"ok": true, "result": {...}}
    """
    data = request.get_json(force=True, silent=True) or {}

    try:
        buy_price = Decimal(str(data.get("buy_price", 0)))
        currency = str(data.get("currency", "USD")).upper()
        qty = int(data.get("qty", 1))
        forwarder_fee = Decimal(str(data.get("forwarder_fee", 0)))
        international_shipping = Decimal(str(data.get("international_shipping", 0)))
        domestic_shipping = Decimal(str(data.get("domestic_shipping", 0)))
        # 하위 호환: shipping_fee → domestic_shipping 으로 매핑
        if "shipping_fee" in data and not data.get("domestic_shipping"):
            domestic_shipping = Decimal(str(data["shipping_fee"]))
        customs_rate_pct = Decimal(str(data.get("customs_rate", 20)))
        customs_rate = customs_rate_pct / Decimal("100")
        marketplace = str(data.get("marketplace", "coupang"))
        # 하위 호환: market_fee_rate 직접 지정 허용
        if "market_fee_rate" in data:
            commission_rate = Decimal(str(data["market_fee_rate"]))
        else:
            from .margin_calculator import default_commission_rate
            commission_rate = default_commission_rate(marketplace)
        pg_fee_rate = Decimal(str(data.get("pg_fee_rate", 0)))
        target_margin_pct = Decimal(str(data.get("target_margin_pct", 22)))
        sell_price_raw = data.get("sell_price")
        sell_price = Decimal(str(sell_price_raw)) if sell_price_raw else None
        fx_override_raw = data.get("fx_override") or data.get("fx_rate")
        fx_override = Decimal(str(fx_override_raw)) if fx_override_raw else None
    except (TypeError, ValueError, InvalidOperation):
        return jsonify({"ok": False, "error": "입력값 형식이 올바르지 않습니다."}), 400

    if buy_price <= Decimal("0"):
        return jsonify({"ok": False, "error": "매입가를 입력하세요."}), 400

    try:
        from .margin_calculator import CostInput, MarginCalculator, MarketInput
        cost = CostInput(
            buy_price=buy_price,
            buy_currency=currency,
            qty=qty,
            forwarder_fee=forwarder_fee,
            international_shipping=international_shipping,
            domestic_shipping=domestic_shipping,
            customs_rate=customs_rate,
            fx_override=fx_override,
        )
        market = MarketInput(
            marketplace=marketplace,
            commission_rate=commission_rate,
            pg_fee_rate=pg_fee_rate,
            target_margin_pct=target_margin_pct,
        )
        calc = MarginCalculator()
        result = calc.calculate(cost, market, sell_price=sell_price)
        return jsonify({"ok": True, "result": _result_to_dict(result)})
    except Exception as exc:
        logger.warning("마진 계산 오류: %s", exc)
        return jsonify({"ok": False, "error": "계산 중 오류가 발생했습니다."}), 500


@bp.post("/pricing/compare")
def pricing_compare():
    """여러 마켓 동시 비교 (JSON).

    Request body: 계산 파라미터 + marketplaces 목록
    Response: {"ok": true, "results": [...]}
    """
    data = request.get_json(force=True, silent=True) or {}

    try:
        buy_price = Decimal(str(data.get("buy_price", 0)))
        currency = str(data.get("currency", "USD")).upper()
        qty = int(data.get("qty", 1))
        forwarder_fee = Decimal(str(data.get("forwarder_fee", 0)))
        international_shipping = Decimal(str(data.get("international_shipping", 0)))
        domestic_shipping = Decimal(str(data.get("domestic_shipping", 0)))
        if "shipping_fee" in data and not data.get("domestic_shipping"):
            domestic_shipping = Decimal(str(data["shipping_fee"]))
        customs_rate_pct = Decimal(str(data.get("customs_rate", 20)))
        customs_rate = customs_rate_pct / Decimal("100")
        target_margin_pct = Decimal(str(data.get("target_margin_pct", 22)))
        marketplaces = data.get("marketplaces") or ["coupang", "smartstore", "11st", "kohganemultishop"]
        sell_price_raw = data.get("sell_price")
        sell_price = Decimal(str(sell_price_raw)) if sell_price_raw else None
        fx_override_raw = data.get("fx_override") or data.get("fx_rate")
        fx_override = Decimal(str(fx_override_raw)) if fx_override_raw else None
    except (TypeError, ValueError, InvalidOperation):
        return jsonify({"ok": False, "error": "입력값 형식이 올바르지 않습니다."}), 400

    if buy_price <= Decimal("0"):
        return jsonify({"ok": False, "error": "매입가를 입력하세요."}), 400

    try:
        from .margin_calculator import CostInput, MarginCalculator
        cost = CostInput(
            buy_price=buy_price,
            buy_currency=currency,
            qty=qty,
            forwarder_fee=forwarder_fee,
            international_shipping=international_shipping,
            domestic_shipping=domestic_shipping,
            customs_rate=customs_rate,
            fx_override=fx_override,
        )
        cost.customs_threshold_krw = Decimal(str(data.get("customs_threshold_krw", 150000)))
        calc = MarginCalculator()
        results = calc.compare_marketplaces(
            cost,
            marketplaces=marketplaces,
            sell_price=sell_price,
        )
        return jsonify({
            "ok": True,
            "results": [_result_to_dict(r) for r in results],
            "target_margin_pct": str(target_margin_pct),
        })
    except Exception as exc:
        logger.warning("마진 비교 계산 오류: %s", exc)
        return jsonify({"ok": False, "error": "계산 중 오류가 발생했습니다."}), 500


@bp.get("/market-status")
def market_status():
    """마켓 상품 현황 페이지 (기존 URL 유지 — /seller/markets로 리다이렉트)."""
    return redirect(url_for("seller_console.markets_overview"))


@bp.get("/markets")
def markets_overview():
    """마켓 현황 상세 페이지 (Phase 127)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    try:
        from .market_status_service import MarketStatusService
        svc = MarketStatusService()
        result = svc.get_all()
        market_data = result.to_legacy_dict()
        # items도 템플릿에 전달
        items = [
            {
                "marketplace": item.marketplace,
                "marketplace_label": _marketplace_label(item.marketplace),
                "product_id": item.product_id,
                "sku": item.sku or "",
                "title": item.title or "",
                "state": item.state,
                "price_krw": item.price_krw,
                "last_synced_at": item.last_synced_at.isoformat() if item.last_synced_at else "",
                "error_message": item.error_message or "",
            }
            for item in result.items
        ]
    except Exception as exc:
        logger.warning("마켓 현황 데이터 로드 실패: %s", exc)
        from .data_aggregator import get_market_product_status
        market_data = get_market_product_status()
        items = []

    return render_template(
        "markets.html",
        market_data=market_data,
        items=items,
        page="market_status",
    )


@bp.get("/markets/status")
def markets_status():
    """JSON: 모든 마켓 상태 (Phase 127)."""
    try:
        from .market_status_service import MarketStatusService
        svc = MarketStatusService()
        result = svc.get_all()
        return jsonify({
            "summaries": [s.to_dict() for s in result.summaries],
            "fetched_at": result.fetched_at.isoformat(),
            "source": result.source,
        })
    except Exception as exc:
        logger.warning("markets_status API 오류: %s", exc)
        return jsonify({"error": "마켓 상태 조회 중 오류가 발생했습니다."}), 500


@bp.post("/markets/sync")
def markets_sync():
    """라이브 동기화 트리거 (Phase 127 — stub, Phase 130에서 실 API 활성화).

    Request body: {"marketplace": "coupang" | "all"}
    Response: {"coupang": 0, ...}
    """
    data = request.get_json(force=True, silent=True) or {}
    marketplace = str(data.get("marketplace", "all")).strip()

    try:
        from .market_status_service import MarketStatusService
        svc = MarketStatusService()
        if marketplace == "all":
            results = {m: svc.sync_marketplace(m) for m in svc.live_adapters}
        else:
            results = {marketplace: svc.sync_marketplace(marketplace)}
        return jsonify(results)
    except Exception as exc:
        logger.warning("markets_sync API 오류: %s", exc)
        return jsonify({"error": "동기화 중 오류가 발생했습니다."}), 500


@bp.get("/health")
def health():
    """셀러 콘솔 헬스체크."""
    try:
        from src.utils.env_catalog import get_api_status
        api_statuses = get_api_status()
        active_count = sum(1 for a in api_statuses if a["status"] == "active")
        missing_count = sum(1 for a in api_statuses if a["status"] == "missing")
    except Exception:
        api_statuses = []
        active_count = 0
        missing_count = 0

    return jsonify({
        "ok": True,
        "service": "seller_console",
        "phase": 128,
        "auth_enabled": _AUTH_ENABLED,
        "api_keys": {
            "active": active_count,
            "missing": missing_count,
            "total": len(api_statuses),
        },
    })


# ---------------------------------------------------------------------------
# 헬퍼: 마켓 레이블
# ---------------------------------------------------------------------------

_MARKETPLACE_LABELS = {
    "coupang": "쿠팡",
    "smartstore": "스마트스토어",
    "11st": "11번가",
    "kohganemultishop": "코가네멀티샵",
}


def _marketplace_label(marketplace: str) -> str:
    return _MARKETPLACE_LABELS.get(marketplace, marketplace)


# ---------------------------------------------------------------------------
# 헬퍼: MarginResult → dict 직렬화
# ---------------------------------------------------------------------------

def _result_to_dict(result) -> Dict[str, Any]:
    """MarginResult 인스턴스를 JSON 직렬화 가능한 dict로 변환."""
    try:
        from .margin_calculator import MarginCalculator
        labels = MarginCalculator.MARKETPLACE_LABELS
    except Exception:
        labels = {
            "coupang": "쿠팡", "smartstore": "스마트스토어", "11st": "11번가",
            "kohganemultishop": "코가네멀티샵", "shopify": "Shopify",
        }
    return {
        "marketplace": result.marketplace,
        "marketplace_label": labels.get(result.marketplace, result.marketplace),
        "cost_in_krw": int(result.cost_in_krw),
        "customs_in_krw": int(result.customs_in_krw),
        "total_landed_cost": int(result.total_landed_cost),
        "recommended_price": int(result.recommended_price),
        "given_price": int(result.given_price) if result.given_price is not None else None,
        "actual_margin_krw": int(result.actual_margin_krw),
        "actual_margin_pct": float(result.actual_margin_pct),
        "breakeven_price": int(result.breakeven_price),
        "fx_used": result.fx_used,
        "warnings": result.warnings,
        # 하위 호환 필드 (기존 UI가 참조)
        "buy_price_krw": int(result.cost_in_krw),
        "customs_amount_krw": int(result.customs_in_krw),
        "cost_krw": int(result.total_landed_cost),
        "sell_price_krw": int(result.given_price if result.given_price is not None else result.recommended_price),
        "breakeven_krw": int(result.breakeven_price),
    }


# ---------------------------------------------------------------------------
# 공개 API — /api/v1/pricing/calculate
# ---------------------------------------------------------------------------

# 공개 API Blueprint 없이 직접 메인 앱에 붙이기 위해 lazy registration 패턴
def _register_api_routes(app):
    """메인 Flask 앱에 공개 마진 계산 API 라우트 등록."""

    @app.route("/api/v1/pricing/calculate", methods=["POST"])
    def api_pricing_calculate():
        """공개 마진 계산 API.

        Request body: 계산 파라미터 (pricing/calc 와 동일)
        Response: {"ok": true, "result": {...}}
        """
        # 인증 stub — Phase 24/129에서 실제 토큰 검증으로 교체
        data = request.get_json(force=True, silent=True) or {}
        try:
            buy_price = Decimal(str(data.get("buy_price", 0)))
            currency = str(data.get("currency", "USD")).upper()
            marketplace = str(data.get("marketplace", "coupang"))
            customs_rate_pct = Decimal(str(data.get("customs_rate", 20)))
            customs_rate = customs_rate_pct / Decimal("100")
            domestic_shipping = Decimal(str(data.get("domestic_shipping") or data.get("shipping_fee", 0)))
            international_shipping = Decimal(str(data.get("international_shipping", 0)))
            forwarder_fee = Decimal(str(data.get("forwarder_fee", 0)))
            if "market_fee_rate" in data:
                commission_rate = Decimal(str(data["market_fee_rate"]))
            else:
                from .margin_calculator import default_commission_rate
                commission_rate = default_commission_rate(marketplace)
            pg_fee_rate = Decimal(str(data.get("pg_fee_rate", 0)))
            target_margin_pct = Decimal(str(data.get("target_margin_pct", 22)))
            sell_price_raw = data.get("sell_price")
            sell_price = Decimal(str(sell_price_raw)) if sell_price_raw else None
        except (TypeError, ValueError, InvalidOperation):
            return jsonify({"ok": False, "error": "입력값 형식이 올바르지 않습니다."}), 400

        if buy_price <= Decimal("0"):
            return jsonify({"ok": False, "error": "매입가를 입력하세요."}), 400

        try:
            from .margin_calculator import CostInput, MarginCalculator, MarketInput
            cost = CostInput(
                buy_price=buy_price,
                buy_currency=currency,
                forwarder_fee=forwarder_fee,
                international_shipping=international_shipping,
                domestic_shipping=domestic_shipping,
                customs_rate=customs_rate,
            )
            market = MarketInput(
                marketplace=marketplace,
                commission_rate=commission_rate,
                pg_fee_rate=pg_fee_rate,
                target_margin_pct=target_margin_pct,
            )
            calc = MarginCalculator()
            result = calc.calculate(cost, market, sell_price=sell_price)
            return jsonify({"ok": True, "result": _result_to_dict(result)})
        except Exception as exc:
            logger.warning("공개 API 마진 계산 오류: %s", exc)
            return jsonify({"ok": False, "error": "계산 중 오류가 발생했습니다."}), 500
