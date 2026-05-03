"""src/dashboard/admin_views.py — 관리자 패널 Blueprint.

Phase 25: Frontend Admin Panel

엔드포인트:
  GET /admin/           — 메인 대시보드 (주문 요약, 매출 요약, 재고 경고, 환율)
  GET /admin/products   — 상품 목록 (수집 상품, 필터, 업로드 상태)
  GET /admin/orders     — 주문 목록 (상태 필터, 주문 상세)
  GET /admin/inventory  — 재고 현황 (재고 부족 경고, 재주문 필요)
"""

from __future__ import annotations

import logging

from flask import Blueprint, render_template_string, request

MAX_DISPLAY_ITEMS = 200

logger = logging.getLogger(__name__)

admin_panel_bp = Blueprint("admin_panel", __name__, url_prefix="/admin")

# ---------------------------------------------------------------------------
# HTML 템플릿
# ---------------------------------------------------------------------------

_BOOTSTRAP_CDN = (
    '<link rel="stylesheet" '
    'href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">'
    '<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js">'
    "</script>"
)

_BASE_HTML = (
    "<!DOCTYPE html>"
    '<html lang="ko">'
    "<head>"
    '<meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1">'
    "<title>{{ title }} — Admin</title>"
    + _BOOTSTRAP_CDN
    + "<style>"
    "body{background:#f8f9fa;}"
    ".sidebar{min-height:100vh;background:#212529;}"
    ".sidebar .nav-link{color:#adb5bd;}"
    ".sidebar .nav-link:hover,.sidebar .nav-link.active{color:#fff;background:rgba(255,255,255,.1);border-radius:6px;}"
    ".card-stat .card-body{padding:1.25rem;}"
    ".badge-warn{background:#ffc107;color:#000;}"
    "</style>"
    "</head>"
    "<body>"
    '<div class="container-fluid">'
    '<div class="row">'
    '<nav class="col-md-2 sidebar p-3">'
    '<h5 class="text-white mb-3">🛒 Admin</h5>'
    '<ul class="nav flex-column">'
    '<li class="nav-item"><a class="nav-link" href="/admin/">대시보드</a></li>'
    '<li class="nav-item"><a class="nav-link" href="/admin/products">상품 목록</a></li>'
    '<li class="nav-item"><a class="nav-link" href="/admin/orders">주문 목록</a></li>'
    '<li class="nav-item"><a class="nav-link" href="/admin/inventory">재고 현황</a></li>'
    "</ul>"
    "</nav>"
    '<main class="col-md-10 p-4">'
    "{{ body }}"
    "</main>"
    "</div>"
    "</div>"
    "</body>"
    "</html>"
)


def _render(title: str, body: str) -> str:
    # body는 뷰에서 직접 조합한 신뢰할 수 있는 HTML 문자열이므로 Markup으로 전달
    from markupsafe import Markup
    return render_template_string(_BASE_HTML, title=title, body=Markup(body))


# ---------------------------------------------------------------------------
# 데이터 로드 헬퍼 (실패해도 빈 값 반환)
# ---------------------------------------------------------------------------

def _load_order_summary() -> dict:
    try:
        from src.dashboard.order_status import OrderStatusTracker  # type: ignore
        tracker = OrderStatusTracker()
        records = tracker.get_all_orders() if hasattr(tracker, "get_all_orders") else []
        total = len(records)
        pending = sum(1 for r in records if str(r.get("status", "")).lower() in ("pending", "대기"))
        return {"total": total, "pending": pending, "records": records}
    except Exception as exc:
        logger.debug("order summary load failed: %s", exc)
        return {"total": 0, "pending": 0, "records": []}


def _load_revenue_summary() -> dict:
    try:
        from src.dashboard.revenue_report import RevenueReporter  # type: ignore
        reporter = RevenueReporter()
        if hasattr(reporter, "get_summary"):
            return reporter.get_summary()
    except Exception as exc:
        logger.debug("revenue summary load failed: %s", exc)
    return {"total_revenue": 0, "total_margin": 0, "currency": "KRW"}


def _load_fx_rate() -> dict:
    try:
        from src.fx_rate import FxRateClient  # type: ignore
        client = FxRateClient()
        rate = client.get_rate("USD", "KRW") if hasattr(client, "get_rate") else None
        if rate:
            return {"USD_KRW": rate}
    except Exception as exc:
        logger.debug("fx rate load failed: %s", exc)
    return {"USD_KRW": "N/A"}


def _load_products() -> list:
    try:
        from src.dashboard.web_ui import _load_products as load_products_from_web_ui  # type: ignore
        return load_products_from_web_ui()
    except Exception:
        pass
    try:
        from src.product_collector import ProductCollector  # type: ignore
        collector = ProductCollector()
        return collector.get_all() if hasattr(collector, "get_all") else []
    except Exception as exc:
        logger.debug("products load failed: %s", exc)
        return []


def _load_inventory() -> list:
    try:
        from src.inventory_manager import InventoryManager  # type: ignore
        mgr = InventoryManager()
        return mgr.get_all() if hasattr(mgr, "get_all") else []
    except Exception as exc:
        logger.debug("inventory load failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# 뷰
# ---------------------------------------------------------------------------

@admin_panel_bp.route("/")
def admin_dashboard():
    """메인 대시보드 — 주문 요약, 매출 요약, 재고 경고, 환율."""
    orders = _load_order_summary()
    revenue = _load_revenue_summary()
    fx = _load_fx_rate()

    body = (
        "<h4 class='mb-4'>📊 대시보드</h4>"
        "<div class='row g-3 mb-4'>"
        f"<div class='col-md-3'><div class='card card-stat'><div class='card-body'>"
        f"<div class='text-muted small'>전체 주문</div>"
        f"<div class='fs-3 fw-bold'>{orders['total']}</div></div></div></div>"
        f"<div class='col-md-3'><div class='card card-stat'><div class='card-body'>"
        f"<div class='text-muted small'>대기 주문</div>"
        f"<div class='fs-3 fw-bold text-warning'>{orders['pending']}</div></div></div></div>"
        f"<div class='col-md-3'><div class='card card-stat'><div class='card-body'>"
        f"<div class='text-muted small'>총 매출</div>"
        f"<div class='fs-3 fw-bold'>{revenue.get('total_revenue', 0):,}</div></div></div></div>"
        f"<div class='col-md-3'><div class='card card-stat'><div class='card-body'>"
        f"<div class='text-muted small'>USD/KRW</div>"
        f"<div class='fs-3 fw-bold'>{fx.get('USD_KRW', 'N/A')}</div></div></div></div>"
        "</div>"
        "<div class='alert alert-info'>관리자 패널에 오신 것을 환영합니다.</div>"
    )
    return _render("대시보드", body)


@admin_panel_bp.route("/products")
def admin_products():
    """상품 목록 — 수집 상품, 필터, 업로드 상태."""
    source_filter = request.args.get("source", "")
    status_filter = request.args.get("status", "")

    products = _load_products()

    if source_filter:
        products = [p for p in products if str(p.get("source", "")) == source_filter]
    if status_filter:
        products = [p for p in products if str(p.get("upload_status", "")) == status_filter]

    rows = ""
    for p in products[:MAX_DISPLAY_ITEMS]:
        name = str(p.get("name", p.get("title", "—")))[:60]
        source = p.get("source", "—")
        status = p.get("upload_status", p.get("status", "—"))
        badge = "success" if str(status).lower() == "uploaded" else "secondary"
        rows += (
            f"<tr><td>{name}</td><td>{source}</td>"
            f"<td><span class='badge bg-{badge}'>{status}</span></td></tr>"
        )

    if not rows:
        rows = "<tr><td colspan='3' class='text-center text-muted'>데이터 없음</td></tr>"

    body = (
        "<h4 class='mb-4'>📦 상품 목록</h4>"
        "<form class='row g-2 mb-3'>"
        "<div class='col-auto'><input class='form-control form-control-sm' name='source' "
        f"placeholder='소스 필터' value='{source_filter}'></div>"
        "<div class='col-auto'><input class='form-control form-control-sm' name='status' "
        f"placeholder='상태 필터' value='{status_filter}'></div>"
        "<div class='col-auto'><button class='btn btn-sm btn-primary'>검색</button></div>"
        "</form>"
        "<table class='table table-hover table-sm'>"
        "<thead><tr><th>상품명</th><th>소스</th><th>업로드 상태</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )
    return _render("상품 목록", body)


@admin_panel_bp.route("/orders")
def admin_orders():
    """주문 목록 — 상태 필터, 주문 상세."""
    status_filter = request.args.get("status", "")

    data = _load_order_summary()
    records = data.get("records", [])

    if status_filter:
        records = [r for r in records if str(r.get("status", "")).lower() == status_filter.lower()]

    rows = ""
    for r in records[:MAX_DISPLAY_ITEMS]:
        order_id = r.get("order_id", r.get("id", "—"))
        status = r.get("status", "—")
        amount = r.get("amount", r.get("total", "—"))
        created = r.get("created_at", r.get("date", "—"))
        badge_cls = {"pending": "warning", "completed": "success", "cancelled": "danger"}.get(
            str(status).lower(), "secondary"
        )
        rows += (
            f"<tr><td>{order_id}</td>"
            f"<td><span class='badge bg-{badge_cls}'>{status}</span></td>"
            f"<td>{amount}</td><td>{created}</td></tr>"
        )

    if not rows:
        rows = "<tr><td colspan='4' class='text-center text-muted'>데이터 없음</td></tr>"

    statuses = ["", "pending", "completed", "cancelled"]
    opts = "".join(
        f"<option value='{s}' {'selected' if s == status_filter else ''}>{s or '전체'}</option>"
        for s in statuses
    )

    body = (
        "<h4 class='mb-4'>🛒 주문 목록</h4>"
        "<form class='row g-2 mb-3'>"
        f"<div class='col-auto'><select class='form-select form-select-sm' name='status'>{opts}</select></div>"
        "<div class='col-auto'><button class='btn btn-sm btn-primary'>검색</button></div>"
        "</form>"
        "<table class='table table-hover table-sm'>"
        "<thead><tr><th>주문 ID</th><th>상태</th><th>금액</th><th>날짜</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )
    return _render("주문 목록", body)


@admin_panel_bp.route("/inventory")
def admin_inventory():
    """재고 현황 — 재고 부족 경고, 재주문 필요."""
    inventory = _load_inventory()

    low_stock = [i for i in inventory if int(i.get("quantity", i.get("stock", 0)) or 0) < 5]
    reorder = [i for i in inventory if int(i.get("quantity", i.get("stock", 0)) or 0) == 0]

    rows = ""
    for item in inventory[:MAX_DISPLAY_ITEMS]:
        name = str(item.get("name", item.get("title", "—")))[:60]
        qty = item.get("quantity", item.get("stock", 0))
        sku = item.get("sku", "—")
        if int(qty or 0) == 0:
            badge = "<span class='badge bg-danger'>재주문 필요</span>"
        elif int(qty or 0) < 5:
            badge = "<span class='badge bg-warning text-dark'>재고 부족</span>"
        else:
            badge = "<span class='badge bg-success'>정상</span>"
        rows += f"<tr><td>{sku}</td><td>{name}</td><td>{qty}</td><td>{badge}</td></tr>"

    if not rows:
        rows = "<tr><td colspan='4' class='text-center text-muted'>데이터 없음</td></tr>"

    warnings = ""
    if reorder:
        warnings += (
            f"<div class='alert alert-danger'>⚠️ 재주문 필요 상품: {len(reorder)}개</div>"
        )
    if low_stock:
        warnings += (
            f"<div class='alert alert-warning'>⚠️ 재고 부족 상품: {len(low_stock)}개</div>"
        )

    body = (
        "<h4 class='mb-4'>📋 재고 현황</h4>"
        + warnings
        + "<table class='table table-hover table-sm'>"
        "<thead><tr><th>SKU</th><th>상품명</th><th>수량</th><th>상태</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )
    return _render("재고 현황", body)
