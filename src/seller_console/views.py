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

import json
import logging
import os
from typing import Any, Dict

from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

logger = logging.getLogger(__name__)
_CS_FAQ_SUPPORTED_LOCALES = {"ko", "ja", "en", "zh-CN"}

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


@bp.app_context_processor
def inject_seller_template_flags():
    return {
        "diagnostic_reveal_enabled": os.getenv("DIAGNOSTIC_REVEAL", "0") == "1",
    }


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
        _api_data = get_api_status()
        api_status = _api_data.get("apis", []) if isinstance(_api_data, dict) else _api_data
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
            logger.warning("orders_bulk_tracking 항목 오류 %s: %s", item.get("order_id"), exc)
            results.append({"order_id": item.get("order_id"), "ok": False, "error": "운송장 등록 중 오류가 발생했습니다."})

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
    """API 상태 페이지 (Phase 130: 카테고리 그루핑)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    try:
        from src.utils.env_catalog import get_api_status as _get_api_status
        api_data = _get_api_status()
        # api_data 는 dict (categories, apis, summary, render_env_note)
        api_list = api_data.get("apis", [])
        summary = api_data.get("summary", {})
        categories = api_data.get("categories", [])
        render_env_note = api_data.get("render_env_note", "")
    except Exception as exc:
        logger.warning("API 상태 로드 실패: %s", exc)
        api_list = []
        summary = {}
        categories = []
        render_env_note = ""

    return render_template(
        "api_status.html",
        page="api_status",
        api_list=api_list,
        summary=summary,
        categories=categories,
        render_env_note=render_env_note,
    )


@bp.get("/api-status/json")
def api_status_json():
    """API 상태 JSON 응답 (Phase 130: 구조화된 응답)."""
    try:
        from src.utils.env_catalog import get_api_status as _get_api_status
        data = _get_api_status()
        return jsonify({"ok": True, **data})
    except Exception as exc:
        logger.warning("API 상태 JSON 오류: %s", exc)
        # 내부 오류 메시지를 외부에 노출하지 않음
        return jsonify({"ok": False, "error": "API 상태 로드 중 오류가 발생했습니다."}), 500


@bp.get("/notifications")
def notifications():
    """알림 설정 페이지 (Phase 133)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    from src.utils.env_catalog import is_active as _is_active
    telegram_active = _is_active("telegram")
    resend_active = _is_active("resend")
    return render_template(
        "notifications.html",
        page="notifications",
        telegram_active=telegram_active,
        resend_active=resend_active,
    )


@bp.post("/notifications/test")
def notifications_test():
    """텔레그램 테스트 메시지 전송 (Phase 130)."""
    try:
        from src.notifications.telegram import send_telegram
        ok = send_telegram("✅ proxy-commerce 알림 테스트 메시지입니다.", urgency="info")
        if ok:
            return jsonify({"ok": True, "message": "텔레그램 메시지 전송 성공"})
        return jsonify({"ok": False, "message": "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 미설정 — 알림 비활성"}), 200
    except Exception as exc:
        logger.warning("텔레그램 테스트 오류: %s", exc)
        return jsonify({"ok": False, "error": "메시지 전송 중 오류가 발생했습니다."}), 500


# ---------------------------------------------------------------------------
# 마이페이지 (Phase 133)
# ---------------------------------------------------------------------------

@bp.get("/me")
def my_page():
    """셀러 마이페이지 (Phase 133)."""
    from flask import session as _session
    user_id = _session.get("user_id")
    user = None
    if user_id:
        try:
            from src.auth.user_store import get_store
            user = get_store().find_by_id(user_id)
        except Exception as exc:
            logger.warning("마이페이지 사용자 조회 실패: %s", exc)

    return render_template(
        "me.html",
        page="me",
        user=user,
        telegram_active=bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        resend_active=bool(os.getenv("RESEND_API_KEY")),
    )


@bp.post("/me/deactivate")
def deactivate_account():
    """계정 비활성화 (soft delete, Phase 133)."""
    from flask import session as _session
    user_id = _session.get("user_id")
    if not user_id:
        return jsonify({"ok": False, "error": "로그인이 필요합니다."}), 401
    try:
        from src.auth.user_store import get_store
        store = get_store()
        user = store.find_by_id(user_id)
        if user:
            user.active = False
            store.update(user)
        _session.clear()
        return jsonify({"ok": True, "message": "계정이 비활성화되었습니다."})
    except Exception as exc:
        logger.warning("계정 비활성화 오류: %s", exc)
        return jsonify({"ok": False, "error": "계정 비활성화 중 오류가 발생했습니다."}), 500


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


# ---------------------------------------------------------------------------
# Phase 134: AI 카피라이터 엔드포인트
# ---------------------------------------------------------------------------

@bp.post("/collect/ai-copy")
def collect_ai_copy():
    """AI 카피 생성 (Phase 134).

    Request body: {
        "title": str,
        "description": str,
        "brand": str,
        "marketplace": str,
        "source_lang": str,
        "variants": int,
        "price_krw": int,
    }
    Response: {"ok": true, "results": [...]}
    """
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "상품명이 필요합니다."}), 400

    from src.ai.budget import BudgetExceededError
    try:
        from src.ai.copywriter import AICopywriter, CopyRequest

        req = CopyRequest(
            title=title,
            description=data.get("description", ""),
            brand=data.get("brand"),
            marketplace=data.get("marketplace"),
            source_lang=data.get("source_lang", "en"),
            price_krw=int(data["price_krw"]) if data.get("price_krw") else None,
            variants=max(1, min(int(data.get("variants", 1)), 5)),
        )
        writer = AICopywriter()
        results = writer.generate(req)
        return jsonify({"ok": True, "results": [r.to_dict() for r in results]})
    except BudgetExceededError as exc:
        return jsonify({"ok": False, "error": "AI 월 예산을 초과했습니다.", "budget": exc.summary}), 402
    except Exception as exc:
        logger.warning("AI 카피 생성 오류: %s", exc)
        return jsonify({"ok": False, "error": "AI 카피 생성 중 오류가 발생했습니다."}), 500


@bp.get("/ai-budget")
def ai_budget():
    """AI 예산 현황 JSON (Phase 134)."""
    try:
        from src.ai.budget import BudgetGuard
        guard = BudgetGuard()
        return jsonify({"ok": True, "budget": guard.summary()})
    except Exception as exc:
        logger.warning("AI 예산 조회 오류: %s", exc)
        return jsonify({"ok": False, "error": "예산 조회 중 오류가 발생했습니다."}), 500


# ---------------------------------------------------------------------------
# Phase 134: 다채널 메시징 엔드포인트
# ---------------------------------------------------------------------------

@bp.get("/messaging")
def messaging():
    """다채널 메시징 페이지 (Phase 134)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    try:
        from src.messaging.router import MessageRouter
        router = MessageRouter()
        channels_status = router.channels_status()
        log = router._log.recent(50)
    except Exception as exc:
        logger.warning("메시징 상태 로드 실패: %s", exc)
        channels_status = []
        log = []

    events = [
        "order_received", "payment_confirmed", "order_shipped",
        "order_delivered", "refund_requested", "refund_completed",
        "out_of_stock", "cs_auto_reply",
    ]
    locales = ["ko", "ja", "en", "zh-CN"]

    return render_template(
        "messaging.html",
        page="messaging",
        channels_status=channels_status,
        log=log,
        events=events,
        locales=locales,
    )


@bp.get("/cs/inbox")
def cs_inbox():
    if not _check_auth():
        return redirect(url_for("seller_console.index"))
    from src.cs_bot.service import CsAutoReplyService

    sample_message = request.args.get("q", "배송 문의가 많아요")
    suggestions = CsAutoReplyService().suggest(sample_message)
    return render_template(
        "cs_inbox.html",
        page="cs_bot",
        sample_message=sample_message,
        suggestions=suggestions,
    )


@bp.route("/cs/faq", methods=["GET", "POST"])
def cs_faq():
    if not _check_auth():
        return redirect(url_for("seller_console.index"))
    from src.cs_bot.store import CsFaqStore

    store = CsFaqStore()
    if request.method == "POST":
        keyword = (request.form.get("keyword") or "").strip()
        answer = (request.form.get("answer") or "").strip()
        locale = (request.form.get("locale") or "ko").strip()
        if locale not in _CS_FAQ_SUPPORTED_LOCALES:
            locale = "ko"
        if keyword and answer:
            store.add_item(keyword=keyword, answer=answer, locale=locale)
    return render_template(
        "cs_faq.html",
        page="cs_bot",
        faq_items=store.list_items(),
        worksheet=store.worksheet_name,
        locales=sorted(_CS_FAQ_SUPPORTED_LOCALES),
    )


@bp.post("/messaging/test")
def messaging_test():
    """테스트 메시지 발송 (Phase 134).

    Request body: {"channel": str, "locale": str, "event": str}
    Response: {"ok": true, "result": {...}}
    """
    data = request.get_json(force=True, silent=True) or {}
    channel = (data.get("channel") or "").strip()
    locale = (data.get("locale") or "ko").strip()
    event = (data.get("event") or "order_received").strip()

    try:
        from src.messaging.router import MessageRouter
        router = MessageRouter()
        result = router.test_send(channel, locale, event, {})
        # Sanitize result: only expose safe fields to external response
        safe_result = {
            "sent": result.get("sent", False),
            "channel": result.get("channel", ""),
            "fallback": result.get("fallback"),
        }
        return jsonify({"ok": True, "result": safe_result})
    except Exception as exc:
        logger.warning("테스트 메시지 오류: %s", exc)
        return jsonify({"ok": False, "error": "테스트 메시지 발송 중 오류가 발생했습니다."}), 500


@bp.get("/messaging/log")
def messaging_log():
    """메시지 발송 로그 JSON (Phase 134)."""
    n = request.args.get("n", 50, type=int)
    try:
        from src.messaging.router import MessageLog
        log = MessageLog()
        rows = log.recent(n)
        return jsonify({"ok": True, "log": rows})
    except Exception as exc:
        logger.warning("메시지 로그 조회 오류: %s", exc)
        return jsonify({"ok": False, "error": "로그 조회 중 오류가 발생했습니다."}), 500


@bp.get("/health")
def health():
    """셀러 콘솔 헬스체크."""
    try:
        from src.utils.env_catalog import get_api_status
        _api_data = get_api_status()
        api_statuses = _api_data.get("apis", []) if isinstance(_api_data, dict) else _api_data
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


# ---------------------------------------------------------------------------
# Phase 135: Personal Access Token 관리
# ---------------------------------------------------------------------------

@bp.get("/me/tokens")
def personal_tokens():
    """Personal Access Token 관리 페이지 (Phase 135)."""
    from flask import session as _session
    user_id = _session.get("user_id", "dev")

    tokens = []
    try:
        from src.auth.personal_tokens import list_tokens
        tokens = list_tokens(user_id)
    except Exception as exc:
        logger.warning("토큰 목록 조회 실패: %s", exc)

    return render_template(
        "personal_tokens.html",
        page="me",
        tokens=tokens,
        valid_scopes=["collect.write", "catalog.read", "markets.write"],
    )


@bp.post("/me/tokens/generate")
def personal_tokens_generate():
    """새 Personal Access Token 발급 (Phase 135).

    Request body: {"scopes": ["collect.write", ...], "expires_days": 365}
    Response: {"ok": true, "raw_token": "tok_...", "expires_at": "..."}
    주의: raw_token은 1회만 반환됨.
    """
    from flask import session as _session
    user_id = _session.get("user_id", "dev")

    data = request.get_json(force=True, silent=True) or {}
    scopes = data.get("scopes") or ["collect.write"]
    expires_days = int(data.get("expires_days", 365))

    try:
        from src.auth.personal_tokens import generate_token
        result = generate_token(user_id=user_id, scopes=scopes, expires_days=expires_days)
        return jsonify({"ok": True, **result})
    except Exception as exc:
        logger.warning("토큰 발급 실패: %s", exc)
        return jsonify({"ok": False, "error": "토큰 발급 중 오류가 발생했습니다."}), 500


@bp.post("/me/tokens/revoke")
def personal_tokens_revoke():
    """Personal Access Token 회수 (Phase 135).

    Request body: {"token_hash": "..."}
    Response: {"ok": true}
    """
    from flask import session as _session
    user_id = _session.get("user_id", "dev")

    data = request.get_json(force=True, silent=True) or {}
    token_hash = (data.get("token_hash") or "").strip()
    if not token_hash:
        return jsonify({"ok": False, "error": "token_hash가 필요합니다."}), 400

    try:
        from src.auth.personal_tokens import revoke_token
        ok = revoke_token(token_hash=token_hash, user_id=user_id)
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("토큰 회수 실패: %s", exc)
        return jsonify({"ok": False, "error": "토큰 회수 중 오류가 발생했습니다."}), 500


# ---------------------------------------------------------------------------
# Phase 135: 북마클릿
# ---------------------------------------------------------------------------

@bp.get("/bookmarklet")
def bookmarklet():
    """북마클릿 설치 페이지 (Phase 135)."""
    from flask import session as _session
    server_url = os.getenv("APP_BASE_URL", "https://kohganepercentiii.com")

    # 사용자 토큰 힌트
    user_id = _session.get("user_id", "dev")

    return render_template(
        "bookmarklet.html",
        page="bookmarklet",
        server_url=server_url,
        user_id=user_id,
    )


# ---------------------------------------------------------------------------
# Phase 135: Discovery 봇
# ---------------------------------------------------------------------------

@bp.get("/discovery")
def discovery():
    """Discovery 후보 목록 페이지 (Phase 135)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    try:
        from src.discovery.scout import DiscoveryScout
        scout = DiscoveryScout()
        candidates = scout.get_candidates(status=request.args.get("status") or "pending")
    except Exception as exc:
        logger.warning("Discovery 후보 조회 실패: %s", exc)
        candidates = []

    return render_template(
        "discovery.html",
        page="discovery",
        candidates=candidates,
        status_filter=request.args.get("status", "pending"),
    )


@bp.post("/discovery/approve")
def discovery_approve():
    """Discovery 후보 도메인 승인 (Phase 135).

    Request body: {"domain": "example.com"}
    Response: {"ok": true}
    """
    data = request.get_json(force=True, silent=True) or {}
    domain = (data.get("domain") or "").strip().lower()
    if not domain:
        return jsonify({"ok": False, "error": "domain이 필요합니다."}), 400

    try:
        from src.discovery.scout import DiscoveryScout
        ok = DiscoveryScout().approve(domain)
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("Discovery 승인 실패: %s", exc)
        return jsonify({"ok": False, "error": "승인 중 오류가 발생했습니다."}), 500


@bp.post("/discovery/reject")
def discovery_reject():
    """Discovery 후보 도메인 거부 (Phase 135).

    Request body: {"domain": "example.com"}
    Response: {"ok": true}
    """
    data = request.get_json(force=True, silent=True) or {}
    domain = (data.get("domain") or "").strip().lower()
    if not domain:
        return jsonify({"ok": False, "error": "domain이 필요합니다."}), 400

    try:
        from src.discovery.scout import DiscoveryScout
        ok = DiscoveryScout().reject(domain)
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("Discovery 거부 실패: %s", exc)
        return jsonify({"ok": False, "error": "거부 중 오류가 발생했습니다."}), 500


@bp.get("/discovery/keywords")
def discovery_keywords():
    """Discovery 키워드 관리 페이지 (Phase 135)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    try:
        from src.discovery.scout import DiscoveryScout
        keywords = DiscoveryScout().get_keywords()
    except Exception as exc:
        logger.warning("키워드 목록 조회 실패: %s", exc)
        keywords = []

    return render_template(
        "discovery_keywords.html",
        page="discovery",
        keywords=keywords,
    )


@bp.post("/discovery/keywords/add")
def discovery_keywords_add():
    """키워드 추가 (Phase 135).

    Request body: {"keyword": "yoga wear brand"}
    Response: {"ok": true}
    """
    data = request.get_json(force=True, silent=True) or {}
    keyword = (data.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"ok": False, "error": "keyword가 필요합니다."}), 400

    try:
        from src.discovery.scout import DiscoveryScout
        ok = DiscoveryScout().add_keyword(keyword)
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("키워드 추가 실패: %s", exc)
        return jsonify({"ok": False, "error": "키워드 추가 중 오류가 발생했습니다."}), 500


@bp.post("/discovery/keywords/remove")
def discovery_keywords_remove():
    """키워드 삭제 (Phase 135).

    Request body: {"keyword": "yoga wear brand"}
    Response: {"ok": true}
    """
    data = request.get_json(force=True, silent=True) or {}
    keyword = (data.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"ok": False, "error": "keyword가 필요합니다."}), 400

    try:
        from src.discovery.scout import DiscoveryScout
        ok = DiscoveryScout().remove_keyword(keyword)
        return jsonify({"ok": ok})
    except Exception as exc:
        logger.warning("키워드 삭제 실패: %s", exc)
        return jsonify({"ok": False, "error": "키워드 삭제 중 오류가 발생했습니다."}), 500


# ---------------------------------------------------------------------------
# Phase 135.2: /seller/collect/history + /seller/collect/preview/<id>
# ---------------------------------------------------------------------------

@bp.get("/collect/history")
def collect_history():
    """수집 이력 페이지 (Phase 135.2)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    domain = request.args.get("domain", "").strip()
    source = request.args.get("source", "").strip()
    days = int(request.args.get("days", "30"))

    items = []
    summ = {"total": 0, "today": 0, "domains": 0, "by_source": {"extension": 0, "bookmarklet": 0, "manual": 0, "bulk": 0}}
    domains = []
    try:
        from .collect_history_store import list_items, summary, distinct_domains
        items = list_items(domain=domain, source=source, days=days)
        summ = summary(days=days)
        domains = distinct_domains()
    except Exception as exc:
        logger.warning("수집 이력 조회 실패: %s", exc)

    return render_template(
        "collect_history.html",
        page="collect_history",
        items=items,
        summary=summ,
        domains=domains,
        filters={"domain": domain, "source": source, "days": days},
    )


@bp.get("/collect/preview/<item_id>")
def collect_preview_by_id(item_id: str):
    """수집된 상품 미리보기 (Phase 135.2)."""
    from flask import abort
    item = None
    try:
        from .collect_history_store import get as history_get
        item = history_get(item_id)
    except Exception as exc:
        logger.warning("미리보기 조회 실패: %s", exc)

    if not item:
        abort(404)

    extra = {}
    try:
        extra = json.loads(item.get("extra_json") or "{}")
    except Exception:
        pass

    return render_template(
        "collect_preview.html",
        page="collect_history",
        item=item,
        extra=extra,
    )


# ---------------------------------------------------------------------------
# Phase 136: 자동 가격 조정 룰 관리 + 이력 + cron
# ---------------------------------------------------------------------------

def _get_pricing_rule_store():
    try:
        from src.pricing.rule import PricingRuleStore
        return PricingRuleStore()
    except Exception as exc:
        logger.warning("PricingRuleStore 로드 실패: %s", exc)
        return None


@bp.get("/pricing/rules")
def pricing_rules():
    """가격 정책 룰 관리 페이지 (Phase 136)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    store = _get_pricing_rule_store()
    rules = []
    if store:
        try:
            rules = [r.to_dict() for r in store.list_all()]
        except Exception as exc:
            logger.warning("룰 목록 로드 실패: %s", exc)

    dry_run_active = os.getenv("PRICING_DRY_RUN", "1") == "1"

    return render_template(
        "pricing_rules.html",
        page="pricing_rules",
        rules=rules,
        dry_run_active=dry_run_active,
    )


@bp.post("/pricing/rules")
def pricing_rules_create():
    """가격 룰 신규 생성 (Phase 136).

    Request body: 룰 파라미터 (JSON)
    Response: {"ok": true, "rule": {...}}
    """
    if not session.get("user_id"):
        return jsonify({"ok": False, "error": "로그인이 필요합니다.", "login_url": "/auth/login"}), 401
    if session.get("user_role") not in ("seller", "admin"):
        return jsonify({"ok": False, "error": "권한이 없습니다."}), 403

    data = request.get_json(force=True, silent=True) or {}
    if not data.get("name"):
        return jsonify({"ok": False, "error": "룰 이름이 필요합니다."}), 400

    store = _get_pricing_rule_store()
    if store is None:
        return jsonify({"ok": False, "error": "가격 엔진 준비 중입니다."}), 503

    try:
        from src.pricing.rule import PricingRule
        rule = PricingRule.from_dict(data)
        rule = store.create(rule)
        return jsonify({"ok": True, "rule": rule.to_dict()}), 201
    except Exception as exc:
        logger.warning("룰 생성 실패: %s", exc)
        return jsonify({"ok": False, "error": "룰 생성 중 오류가 발생했습니다."}), 500


@bp.post("/pricing/rules/<rule_id>/edit")
def pricing_rules_edit(rule_id: str):
    """가격 룰 수정 (Phase 136)."""
    data = request.get_json(force=True, silent=True) or {}
    store = _get_pricing_rule_store()
    if store is None:
        return jsonify({"ok": False, "error": "가격 엔진 준비 중입니다."}), 503

    rule = store.get(rule_id)
    if not rule:
        return jsonify({"ok": False, "error": "룰을 찾을 수 없습니다."}), 404

    try:
        from src.pricing.rule import PricingRule
        data["rule_id"] = rule_id
        updated_rule = PricingRule.from_dict({**rule.to_dict(), **data})
        ok = store.update(updated_rule)
        return jsonify({"ok": ok, "rule": updated_rule.to_dict()})
    except Exception as exc:
        logger.warning("룰 수정 실패: %s", exc)
        return jsonify({"ok": False, "error": "룰 수정 중 오류가 발생했습니다."}), 500


@bp.post("/pricing/rules/<rule_id>/delete")
def pricing_rules_delete(rule_id: str):
    """가격 룰 삭제 (Phase 136)."""
    store = _get_pricing_rule_store()
    if store is None:
        return jsonify({"ok": False, "error": "가격 엔진 준비 중입니다."}), 503

    ok = store.delete(rule_id)
    if not ok:
        return jsonify({"ok": False, "error": "룰을 찾을 수 없습니다."}), 404
    return jsonify({"ok": True})


@bp.post("/pricing/rules/<rule_id>/toggle")
def pricing_rules_toggle(rule_id: str):
    """가격 룰 활성/비활성 토글 (Phase 136)."""
    store = _get_pricing_rule_store()
    if store is None:
        return jsonify({"ok": False, "error": "가격 엔진 준비 중입니다."}), 503

    new_state = store.toggle(rule_id)
    if new_state is None:
        return jsonify({"ok": False, "error": "룰을 찾을 수 없습니다."}), 404
    return jsonify({"ok": True, "enabled": new_state})


@bp.post("/pricing/rules/reorder")
def pricing_rules_reorder():
    """룰 우선순위 재정렬 (Phase 136).

    Request body: {"ordered_ids": ["rule_id_1", "rule_id_2", ...]}
    """
    data = request.get_json(force=True, silent=True) or {}
    ordered_ids = data.get("ordered_ids") or []
    if not ordered_ids:
        return jsonify({"ok": False, "error": "ordered_ids가 필요합니다."}), 400

    store = _get_pricing_rule_store()
    if store is None:
        return jsonify({"ok": False, "error": "가격 엔진 준비 중입니다."}), 503

    try:
        store.reorder(ordered_ids)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.warning("룰 재정렬 실패: %s", exc)
        return jsonify({"ok": False, "error": "재정렬 중 오류가 발생했습니다."}), 500


@bp.post("/pricing/simulate")
def pricing_simulate():
    """가격 시뮬레이션 (dry_run=True) — 영향 SKU 미리보기 (Phase 136).

    Response: {"ok": true, "results": {...}}
    """
    try:
        from src.pricing.engine import PricingEngine
        engine = PricingEngine()
        results = engine.evaluate(dry_run=True)
        return jsonify({"ok": True, "results": results})
    except Exception as exc:
        logger.warning("가격 시뮬레이션 오류: %s", exc)
        return jsonify({"ok": False, "error": "시뮬레이션 중 오류가 발생했습니다."}), 500


@bp.post("/pricing/run-now")
def pricing_run_now():
    """가격 즉시 실행 (Phase 136).

    Request body: {"dry_run": true|false}
    Response: {"ok": true, "results": {...}}
    """
    data = request.get_json(force=True, silent=True) or {}
    dry_run = data.get("dry_run", True)

    try:
        from src.pricing.engine import PricingEngine
        engine = PricingEngine()
        results = engine.evaluate(dry_run=bool(dry_run))
        return jsonify({"ok": True, "results": results})
    except Exception as exc:
        logger.warning("가격 즉시 실행 오류: %s", exc)
        return jsonify({"ok": False, "error": "실행 중 오류가 발생했습니다."}), 500


@bp.get("/pricing/history")
def pricing_history():
    """가격 변동 이력 페이지 (Phase 136)."""
    if not _check_auth():
        return redirect(url_for("seller_console.index"))

    sku = request.args.get("sku", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    items = []
    try:
        from src.pricing.history_store import PriceHistoryStore
        store = PriceHistoryStore()
        items = store.list_history(
            sku=sku or None,
            date_from=date_from or None,
            date_to=date_to or None,
        )
    except Exception as exc:
        logger.warning("가격 이력 조회 실패: %s", exc)

    return render_template(
        "pricing_history.html",
        page="pricing_rules",
        items=items,
        filters={"sku": sku, "date_from": date_from, "date_to": date_to},
    )


@bp.post("/pricing/history/<history_id>/rollback")
def pricing_history_rollback(history_id: str):
    """가격 롤백 (Phase 136) — 이전 가격으로 복원.

    Response: {"ok": true, "new_history": {...}}
    """
    from flask import session as _session
    applied_by = _session.get("user_email") or _session.get("user_id") or "manual"

    try:
        from src.pricing.history_store import PriceHistoryStore
        store = PriceHistoryStore()
        new_item = store.rollback(history_id, applied_by=applied_by)
        if not new_item:
            return jsonify({"ok": False, "error": "이력을 찾을 수 없습니다."}), 404
        return jsonify({"ok": True, "new_history": new_item})
    except Exception as exc:
        logger.warning("가격 롤백 오류: %s", exc)
        return jsonify({"ok": False, "error": "롤백 중 오류가 발생했습니다."}), 500
