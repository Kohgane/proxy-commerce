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
import os

from flask import Blueprint, current_app, redirect, render_template_string, request, session

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
    '{% include "partials/topnav.html" %}'
    '<div class="container-fluid">'
    '<div class="row">'
    '<nav class="col-md-2 sidebar p-3">'
    '<h5 class="text-white mb-3">🛒 Admin</h5>'
    '<ul class="nav flex-column">'
    '<li class="nav-item"><a class="nav-link" href="/admin/">대시보드</a></li>'
    '<li class="nav-item"><a class="nav-link" href="/admin/products">상품 목록</a></li>'
    '<li class="nav-item"><a class="nav-link" href="/admin/orders">주문 목록</a></li>'
    '<li class="nav-item"><a class="nav-link" href="/admin/inventory">재고 현황</a></li>'
    '<li class="nav-item"><a class="nav-link" href="/admin/diagnostics">🔧 진단</a></li>'
    '<li class="nav-item"><a class="nav-link" href="/admin/users">👥 사용자 관리</a></li>'
    '<li class="nav-item"><a class="nav-link" href="/admin/env">⚙️ 환경변수</a></li>'
    '<li class="nav-item"><a class="nav-link" href="/admin/logs">📜 로그</a></li>'
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


@admin_panel_bp.route("/users")
def admin_users():
    body = "<h4 class='mb-3'>👥 사용자 관리</h4><div class='alert alert-secondary'>준비 중입니다.</div>"
    return _render("사용자 관리", body)


@admin_panel_bp.route("/env")
def admin_env():
    body = "<h4 class='mb-3'>⚙️ 환경변수</h4><div class='alert alert-secondary'>/admin/diagnostics에서 상세 점검 가능합니다.</div>"
    return _render("환경변수", body)


@admin_panel_bp.route("/logs")
def admin_logs():
    body = "<h4 class='mb-3'>📜 로그</h4><div class='alert alert-secondary'>최근 이벤트 로그는 /admin/diagnostics를 참고하세요.</div>"
    return _render("로그", body)


# ---------------------------------------------------------------------------
# Phase 136+142: /admin/diagnostics — 운영 진단 대시보드
# ---------------------------------------------------------------------------

def _require_admin():
    """admin 권한 확인 헬퍼. 거부 시 (response, code) 튜플 반환, 통과 시 None."""
    from src.auth.admin_resolver import is_admin_session
    if not session.get("user_id"):
        return redirect("/auth/login?next=/admin/diagnostics"), None
    admin_ok, _ = is_admin_session(session)
    if not admin_ok:
        return _render("접근 거부", "<div class='alert alert-danger'>관리자 권한이 필요합니다.</div>"), 403
    return None, None


@admin_panel_bp.route("/diagnostics")
def admin_diagnostics():
    """운영 진단 대시보드 (Phase 136+142).

    admin 역할 필수 (admin_resolver 통해 ADMIN_EMAILS/ADMIN_KAKAO_IDS 등도 인정).
    """
    from src.auth.admin_resolver import is_admin_session
    if not session.get("user_id"):
        return redirect("/auth/login?next=/admin/diagnostics")
    admin_ok, _ = is_admin_session(session)
    if not admin_ok:
        return _render("접근 거부", "<div class='alert alert-danger'>관리자 권한이 필요합니다.</div>"), 403

    return _render_diagnostics(issued_magic_link=None)


def _render_diagnostics(issued_magic_link: str | None):
    # 섹션 1: 환경변수 매트릭스
    env_matrix = _build_env_matrix()

    # 섹션 2: OAuth 콜백 URL
    base_url = _get_base_url()
    oauth_urls = {
        "Google": f"{base_url}/auth/google/callback",
        "Kakao": f"{base_url}/auth/kakao/callback",
        "Naver": f"{base_url}/auth/naver/callback",
    }
    emergency_access = _build_emergency_access_status()
    emergency_access["issued_magic_link"] = issued_magic_link
    oauth_diagnostics = _build_oauth_diagnostics(base_url, oauth_urls)

    # 섹션 3: 메신저 채널 health
    messenger_health = _build_messenger_health()

    # 섹션 4: 마켓 어댑터 health
    market_health = _build_market_health()

    # 섹션 5: 가격 엔진 상태
    pricing_status = _build_pricing_status()

    # 섹션 6: 최근 24시간 알림 로그
    message_log = _build_message_log()
    cs_bot_status = _build_cs_bot_status()

    # Phase 142: 인증 상태 + 자동화 카드
    auth_status = _build_auth_status()
    auto_reorder_status = _build_auto_reorder_status()
    discount_campaign_status = _build_discount_campaign_status()

    # Phase 143: 소싱 파이프라인 카드
    sourcing_pipeline_status = _build_sourcing_pipeline_status()

    # Phase 144: 광고 자동 운영 + 라우트 점검 카드
    ads_status = _build_ads_status()
    route_check_status = _build_route_check_status()
    sidebar_nav_status = _build_sidebar_nav_status()
    order_auto_status = _build_order_auto_status()
    cs_unified_inbox_status = _build_cs_unified_inbox_status()
    shipping_monitor_status = _build_shipping_monitor_status()
    header_branch_status = _build_header_branch_status()
    returns_automation_status = _build_returns_automation_status()
    settlement_report_status = _build_settlement_report_status()

    # Phase 147: PWA / Web Push / 옴니 재고 / 큐 카드
    pwa_status = _build_pwa_status()
    web_push_status = _build_web_push_status()
    omni_sync_status = _build_omni_sync_status()
    job_queue_status = _build_job_queue_status()

    # Phase 148: 버전 표시 / B2B 도매 / 정기구독 카드
    version_display_status = _build_version_display_status()
    wholesale_status = _build_wholesale_status()
    product_subscription_status = _build_product_subscription_status()

    return render_template_string(
        _DIAGNOSTICS_TEMPLATE,
        env_matrix=env_matrix,
        oauth_urls=oauth_urls,
        emergency_access=emergency_access,
        oauth_diagnostics=oauth_diagnostics,
        messenger_health=messenger_health,
        market_health=market_health,
        pricing_status=pricing_status,
        message_log=message_log,
        cs_bot_status=cs_bot_status,
        auth_status=auth_status,
        auto_reorder_status=auto_reorder_status,
        discount_campaign_status=discount_campaign_status,
        sourcing_pipeline_status=sourcing_pipeline_status,
        ads_status=ads_status,
        route_check_status=route_check_status,
        sidebar_nav_status=sidebar_nav_status,
        order_auto_status=order_auto_status,
        cs_unified_inbox_status=cs_unified_inbox_status,
        shipping_monitor_status=shipping_monitor_status,
        header_branch_status=header_branch_status,
        returns_automation_status=returns_automation_status,
        settlement_report_status=settlement_report_status,
        pwa_status=pwa_status,
        web_push_status=web_push_status,
        omni_sync_status=omni_sync_status,
        job_queue_status=job_queue_status,
        version_display_status=version_display_status,
        wholesale_status=wholesale_status,
        product_subscription_status=product_subscription_status,
        env=os.environ,
        base_url=base_url,
    )


@admin_panel_bp.post("/diagnostics/issue-magic-link")
def diagnostics_issue_magic_link():
    from src.auth.admin_resolver import is_admin_session
    if not session.get("user_id"):
        return redirect("/auth/login?next=/admin/diagnostics")
    admin_ok, _ = is_admin_session(session)
    if not admin_ok:
        return _render("접근 거부", "<div class='alert alert-danger'>관리자 권한이 필요합니다.</div>"), 403

    email = (request.form.get("email") or "").strip().lower()
    admin_emails = [e.strip().lower() for e in os.getenv("ADMIN_EMAILS", "").split(",") if e.strip()]
    if not email or "@" not in email:
        return _render("발급 실패", "<div class='alert alert-danger'>올바른 이메일을 입력하세요.</div>"), 400
    if email not in admin_emails:
        return _render("발급 실패", "<div class='alert alert-danger'>ADMIN_EMAILS에 등록된 관리자 이메일만 발급 가능합니다.</div>"), 403

    from src.auth.magic_link import issue_magic_link

    issued_magic_link = issue_magic_link(email=email, next_url="/admin/diagnostics")
    return _render_diagnostics(issued_magic_link=issued_magic_link)


@admin_panel_bp.post("/diagnostics/expire-diagnostic-tokens")
def diagnostics_expire_diagnostic_tokens():
    from src.auth.admin_resolver import is_admin_session
    if not session.get("user_id"):
        return redirect("/auth/login?next=/admin/diagnostics")
    admin_ok, _ = is_admin_session(session)
    if not admin_ok:
        return _render("접근 거부", "<div class='alert alert-danger'>관리자 권한이 필요합니다.</div>"), 403
    try:
        from src.auth.diagnostic_token import expire_all_tokens

        expired_count = expire_all_tokens()
        return _render_diagnostics(issued_magic_link=f"진단 토큰 {expired_count}개를 만료 처리했습니다.")
    except Exception as exc:
        logger.warning("diagnostic token 만료 처리 실패: %s", exc)
        return _render("처리 실패", "<div class='alert alert-danger'>만료 처리 중 오류가 발생했습니다.</div>"), 500


@admin_panel_bp.post("/diagnostics/test-telegram")
def diagnostics_test_telegram():
    """텔레그램 테스트 메시지 발송 (Phase 136)."""
    try:
        from src.notifications.telegram import send_telegram
        ok = send_telegram("🔔 /admin/diagnostics 테스트 메시지입니다.", urgency="info")
        return {"ok": ok, "message": "전송 성공" if ok else "전송 실패 (로그 확인)"}
    except Exception as exc:
        logger.warning("텔레그램 테스트 메시지 오류: %s", exc)
        return {"ok": False, "error": "테스트 메시지 발송 중 오류가 발생했습니다."}, 500


@admin_panel_bp.get("/diagnostics/telegram-health")
def diagnostics_telegram_health():
    """텔레그램 health_check JSON (Phase 136)."""
    from src.notifications.telegram import health_check
    from flask import jsonify
    return jsonify(health_check())


# ---------------------------------------------------------------------------
# Phase 148 — VAPID 자동 생성 UI
# ---------------------------------------------------------------------------

@admin_panel_bp.post("/diagnostics/vapid-generate")
def diagnostics_vapid_generate():
    """VAPID 키 쌍 생성 API (Phase 148).

    생성된 키는 WEB_PUSH_VAPID_PUBLIC / WEB_PUSH_VAPID_PRIVATE 에 설정해야 함.
    Private 키는 마스킹(앞 4 + ... + 뒤 4)하여 표시.
    """
    from src.auth.admin_resolver import is_admin_session
    if not session.get("user_id"):
        return redirect("/auth/login?next=/admin/diagnostics")
    admin_ok, _ = is_admin_session(session)
    if not admin_ok:
        return _render("접근 거부", "<div class='alert alert-danger'>관리자 권한이 필요합니다.</div>"), 403

    try:
        from src.notifications.web_push import generate_vapid_keys, vapid_configured
        keys = generate_vapid_keys()
        pub = keys.get("public", "")
        priv = keys.get("private", "")
        # Private Key 마스킹: 앞 4 + ... + 뒤 4 (보안: 평문 Private Key는 UI에 노출하지 않음)
        # VAPID private key는 통상 87+ 문자 — 16자 미만은 생성 오류로 처리
        if len(priv) >= 16:
            priv_masked = priv[:4] + "..." + priv[-4:]
        elif priv.startswith("("):
            # 생성 불가 stub 메시지
            priv_masked = priv
        else:
            logger.warning("VAPID Private Key가 비정상적으로 짧습니다 (length=%d)", len(priv))
            priv_masked = "⚠️ 키 생성 오류 — 서버 로그 확인"
        already = vapid_configured()
        hint = keys.get("hint", "")
        # Private Key를 서버 로그에만 기록 (운영자가 직접 서버 로그에서 확인)
        logger.info("VAPID 키 생성 완료 — Public: %s | Private: [서버 로그 전용]", pub)
        logger.info("VAPID PRIVATE KEY (서버 로그): %s", priv)
        msg = (
            f"<div class='alert alert-{'warning' if already else 'success'}'>"
            + (f"⚠️ 이미 VAPID 키가 등록되어 있습니다. 교체하면 모든 사용자가 재구독해야 합니다.<br>" if already else "")
            + f"<strong>Public Key:</strong> <code>{pub}</code><br>"
            + f"<strong>Private Key (마스킹):</strong> <code>{priv_masked}</code><br>"
            + "<small class='text-muted'>⚠️ 보안 정책에 따라 Private Key는 서버 로그에서 확인하세요. "
            + "Render Dashboard → Logs → 가장 최근 VAPID 생성 로그를 참조하세요.</small><br>"
            + f"<br>Render 환경변수에 추가하세요:<br>"
            + f"<code>WEB_PUSH_VAPID_PUBLIC={pub}</code><br>"
            + f"<code>WEB_PUSH_VAPID_PRIVATE=&lt;서버 로그에서 복사&gt;</code>"
            + (f"<br><small class='text-muted'>{hint}</small>" if hint else "")
            + "</div>"
        )
        return _render_diagnostics(issued_magic_link=msg)
    except Exception as exc:
        logger.warning("VAPID 생성 실패: %s", exc)
        return _render("생성 실패", f"<div class='alert alert-danger'>VAPID 키 생성 중 오류: {exc}</div>"), 500


# ---------------------------------------------------------------------------
# Phase 147 — /admin/jobs (잡 큐 관리)
# ---------------------------------------------------------------------------

@admin_panel_bp.get("/jobs")
def admin_jobs():
    """잡 큐 관리 대시보드 (Phase 147)."""
    from src.auth.admin_resolver import is_admin_session
    if not session.get("user_id"):
        return redirect("/auth/login?next=/admin/jobs")
    admin_ok, _ = is_admin_session(session)
    if not admin_ok:
        return _render("접근 거부", "<div class='alert alert-danger'>관리자 권한이 필요합니다.</div>"), 403

    try:
        from src.jobs.queue_manager import get_queue
        q = get_queue()
        summary = q.summary()
        queued_jobs = q.list_queue(status="queued")[:50]
        running_jobs = q.list_queue(status="running")[:20]
        dead_letters = q.list_dead_letters()[:50]
    except Exception as exc:
        logger.warning("잡 큐 로드 실패: %s", exc)
        summary = {"queued": 0, "running": 0, "dead_letters": 0, "by_category": {}, "worker_distribution": {}, "backend": "db"}
        queued_jobs = running_jobs = dead_letters = []

    from markupsafe import Markup

    def _job_rows(jobs):
        if not jobs:
            return "<tr><td colspan='6' class='text-center text-muted'>없음</td></tr>"
        rows = ""
        for j in jobs:
            badge_class = "bg-primary" if j.status == "running" else "bg-secondary"
            rows += (
                f"<tr>"
                f"<td><code class='small'>{j.job_id[:12]}...</code></td>"
                f"<td><span class='badge bg-secondary'>{j.category}</span></td>"
                f"<td>{j.priority}</td>"
                f"<td><span class='badge {badge_class}'>{j.status}</span></td>"
                f"<td class='small text-muted'>{j.created_at[:19]}</td>"
                f"<td class='small text-muted'>{j.worker_id or '-'}</td>"
                f"</tr>"
            )
        return rows

    def _dead_rows(jobs):
        if not jobs:
            return "<tr><td colspan='5' class='text-center text-muted'>없음</td></tr>"
        rows = ""
        for j in jobs:
            rows += (
                f"<tr>"
                f"<td><code class='small'>{j.job_id[:12]}...</code></td>"
                f"<td>{j.category}</td>"
                f"<td>{j.attempts}</td>"
                f"<td class='small text-danger'>{(j.error or '')[:60]}</td>"
                f"<td>"
                f"<form method='post' action='/admin/jobs/retry-dead' style='display:inline'>"
                f"<input type='hidden' name='job_id' value='{j.job_id}'>"
                f"<button class='btn btn-outline-primary btn-sm'>재시도</button>"
                f"</form>"
                f"</td>"
                f"</tr>"
            )
        return rows

    body = Markup(
        "<h4 class='mb-3'>⚙️ 잡 큐 관리 (Phase 147)</h4>"
        "<div class='row mb-3'>"
        f"<div class='col-md-2'><div class='card text-center'><div class='card-body'><h5 class='text-warning'>{summary['queued']}</h5><small>대기 중</small></div></div></div>"
        f"<div class='col-md-2'><div class='card text-center'><div class='card-body'><h5 class='text-primary'>{summary['running']}</h5><small>실행 중</small></div></div></div>"
        f"<div class='col-md-2'><div class='card text-center'><div class='card-body'><h5 class='text-danger'>{summary['dead_letters']}</h5><small>데드레터</small></div></div></div>"
        f"<div class='col-md-3'><div class='card text-center'><div class='card-body'><h5>{len(summary.get('worker_distribution', {}))}</h5><small>활성 워커</small></div></div></div>"
        f"<div class='col-md-3'><div class='card text-center'><div class='card-body'><h5><code>{summary.get('backend', 'db')}</code></h5><small>백엔드</small></div></div></div>"
        "</div>"
        "<div class='row mb-3'>"
        "<div class='col-md-6'>"
        "<h6>카테고리별 대기</h6><ul class='small mb-0'>"
        + "".join(f"<li>{cat}: {cnt}건</li>" for cat, cnt in summary.get("by_category", {}).items())
        + ("" if summary.get("by_category") else "<li class='text-muted'>없음</li>")
        + "</ul></div>"
        "<div class='col-md-6'>"
        "<h6>워커별 분포</h6><ul class='small mb-0'>"
        + "".join(f"<li><code>{w}</code>: {cnt}건</li>" for w, cnt in summary.get("worker_distribution", {}).items())
        + ("" if summary.get("worker_distribution") else "<li class='text-muted'>없음</li>")
        + "</ul></div></div>"
        "<h5 class='mb-2'>대기 중 작업</h5>"
        "<div class='table-responsive mb-4'>"
        "<table class='table table-sm table-hover'>"
        "<thead><tr><th>Job ID</th><th>카테고리</th><th>우선순위</th><th>상태</th><th>생성</th><th>워커</th></tr></thead>"
        f"<tbody>{_job_rows(queued_jobs)}</tbody></table></div>"
        "<h5 class='mb-2'>실행 중 작업</h5>"
        "<div class='table-responsive mb-4'>"
        "<table class='table table-sm table-hover'>"
        "<thead><tr><th>Job ID</th><th>카테고리</th><th>우선순위</th><th>상태</th><th>생성</th><th>워커</th></tr></thead>"
        f"<tbody>{_job_rows(running_jobs)}</tbody></table></div>"
        "<h5 class='mb-2'>데드레터 리스트</h5>"
        "<div class='table-responsive mb-4'>"
        "<table class='table table-sm table-hover'>"
        "<thead><tr><th>Job ID</th><th>카테고리</th><th>재시도</th><th>오류</th><th>액션</th></tr></thead>"
        f"<tbody>{_dead_rows(dead_letters)}</tbody></table></div>"
    )
    return _render("잡 큐 관리", body)


@admin_panel_bp.post("/jobs/retry-dead")
def admin_jobs_retry_dead():
    """dead letter 재시도 (Phase 147)."""
    from src.auth.admin_resolver import is_admin_session
    if not session.get("user_id"):
        return redirect("/auth/login?next=/admin/jobs")
    admin_ok, _ = is_admin_session(session)
    if not admin_ok:
        return _render("접근 거부", "<div class='alert alert-danger'>관리자 권한이 필요합니다.</div>"), 403
    from flask import jsonify
    try:
        from src.jobs.queue_manager import get_queue
        job_id = (request.form.get("job_id") or "").strip()
        if not job_id:
            return redirect("/admin/jobs")
        ok = get_queue().retry_dead(job_id)
        return redirect("/admin/jobs")
    except Exception as exc:
        logger.warning("dead letter 재시도 오류: %s", exc)
        return redirect("/admin/jobs")


@admin_panel_bp.post("/cs/poll-now")
def admin_cs_poll_now():
    """즉시 다채널 폴링 트리거."""
    from flask import jsonify
    if not session.get("user_id"):
        return jsonify({"ok": False, "error": "인증 필요"}), 401
    try:
        from src.cs_bot.scheduler import poll_all_channels
        result = poll_all_channels()
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        logger.warning("cs poll-now 오류: %s", exc)
        return jsonify({"ok": False, "error": "내부 오류가 발생했습니다"}), 500


@admin_panel_bp.post("/cs/check-sla")
def admin_cs_check_sla():
    """SLA 점검 수동 트리거."""
    from flask import jsonify
    try:
        from src.cs_bot.sla import check_and_notify_sla
        result = check_and_notify_sla()
        return jsonify({"ok": True, "nearing": result.get("nearing_count", 0), "overdue": result.get("overdue_count", 0)})
    except Exception as exc:
        logger.warning("cs check-sla 오류: %s", exc)
        return jsonify({"ok": False, "error": "내부 오류가 발생했습니다"}), 500


@admin_panel_bp.post("/cs/rebuild-embeddings")
def admin_cs_rebuild_embeddings():
    """FAQ 임베딩 일괄 재계산."""
    from flask import jsonify
    if not session.get("user_id"):
        return jsonify({"ok": False, "error": "인증 필요"}), 401
    try:
        from src.cs_bot.faq_store import FAQStore
        from src.cs_bot.embeddings import rebuild_faq_embeddings
        updated = rebuild_faq_embeddings(FAQStore())
        return jsonify({"ok": True, "updated": updated})
    except Exception as exc:
        logger.warning("cs rebuild-embeddings 오류: %s", exc)
        return jsonify({"ok": False, "error": "내부 오류가 발생했습니다"}), 500


@admin_panel_bp.get("/cs/stats")
def admin_cs_stats():
    """CS 통계 대시보드 (JSON API)."""
    from flask import jsonify
    try:
        from src.cs_bot.inbox_store import InboxStore
        store = InboxStore()
        stats = store.stats_24h()
        return jsonify({"ok": True, "stats": stats})
    except Exception as exc:
        logger.warning("cs stats 오류: %s", exc)
        return jsonify({"ok": False, "error": "내부 오류가 발생했습니다"}), 500


# ── 진단 헬퍼 함수 ────────────────────────────────────────────────────────

def _get_base_url() -> str:
    import os
    return os.getenv("APP_BASE_URL", "https://kohganepercentiii.com").rstrip("/")


def _build_env_matrix() -> list:
    """환경변수 카탈로그 상태 매트릭스."""
    try:
        from src.utils.env_catalog import API_REGISTRY
        result = []
        for api in API_REGISTRY:
            cat = api.category
            result.append({
                "name": api.name,
                "purpose": api.purpose,
                "category": cat.value if hasattr(cat, "value") else str(cat),
                "status": api.status,
                "env_vars": api.env_vars,
                "docs_url": getattr(api, "docs_url", ""),
            })
        return result
    except Exception as exc:
        logger.warning("env_matrix 로드 실패: %s", exc)
        return []


def _build_messenger_health() -> dict:
    """메신저 채널 health 상태."""
    health = {}

    # 텔레그램
    try:
        from src.notifications.telegram import health_check
        health["telegram"] = health_check()
    except Exception as exc:
        health["telegram"] = {"status": "error", "error": str(exc)}

    # Resend
    import os
    health["resend"] = {
        "status": "active" if os.getenv("RESEND_API_KEY") else "missing",
        "hint": "RESEND_API_KEY 미설정" if not os.getenv("RESEND_API_KEY") else None,
    }

    # 카카오 알림톡
    health["kakao_alimtalk"] = {
        "status": "active" if os.getenv("KAKAO_ALIMTALK_API_KEY") else "missing",
    }

    # LINE
    health["line"] = {
        "status": "active" if (os.getenv("LINE_NOTIFY_TOKEN") or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")) else "missing",
    }

    # WhatsApp
    health["whatsapp"] = {
        "status": "active" if os.getenv("META_WHATSAPP_TOKEN") else "missing",
    }

    # Discord
    health["discord"] = {
        "status": "active" if os.getenv("DISCORD_WEBHOOK_URL") else "missing",
    }

    return health


def _build_market_health() -> dict:
    """마켓 어댑터 health 상태."""
    health = {}
    adapter_map = {
        "coupang": ("src.seller_console.market_adapters.coupang_adapter", "CoupangAdapter"),
        "smartstore": ("src.seller_console.market_adapters.smartstore_adapter", "SmartStoreAdapter"),
        "11st": ("src.seller_console.market_adapters.eleven_adapter", "ElevenAdapter"),
        "woocommerce": ("src.seller_console.market_adapters.woocommerce_adapter", "WooCommerceAdapter"),
    }
    for name, (module_path, class_name) in adapter_map.items():
        try:
            import importlib
            module = importlib.import_module(module_path)
            adapter_cls = getattr(module, class_name)
            adapter = adapter_cls()
            health[name] = adapter.health_check()
        except Exception as exc:
            health[name] = {"status": "error", "detail": str(exc)}
    return health


def _build_pricing_status() -> dict:
    """가격 자동화 상태."""
    import os
    try:
        from src.pricing.rule import PricingRuleStore
        store = PricingRuleStore()
        rules = store.active_sorted()
        active_count = len(rules)
        last_run = None
        for rule in sorted(rules, key=lambda r: r.last_run_at or "", reverse=True):
            if rule.last_run_at:
                last_run = rule.last_run_at
                break
    except Exception:
        active_count = 0
        last_run = None

    competitor_monitored = 0
    competitor_24h = 0
    try:
        from src.pricing.competitor_monitor import CompetitorMonitor

        summary = CompetitorMonitor().summary_24h()
        competitor_monitored = int(summary.get("active_monitored", 0))
        competitor_24h = int(summary.get("recent_changes", 0))
    except Exception:
        pass

    own_24h = 0
    margin_warn = 0
    persistence_health = []
    try:
        from datetime import datetime, timedelta, timezone
        from src.pricing.history_store import PriceHistoryStore

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        rows = PriceHistoryStore().list_history(limit=5000)
        for row in rows:
            ts = str(row.get("applied_at") or "")
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt >= cutoff:
                    own_24h += 1
            except Exception:
                continue
    except Exception:
        pass

    fx_summary = "정상"
    try:
        from src.pricing.fx_impact import FXImpactAnalyzer

        changes = FXImpactAnalyzer().daily_changes()
        bits = []
        for currency in ("USD", "JPY"):
            val = float(changes.get(currency, 0))
            arrow = "↑" if val > 0 else ("↓" if val < 0 else "-")
            bits.append(f"{currency} {abs(val):.1f}% {arrow}")
        fx_summary = " / ".join(bits) if bits else "정상"
    except Exception:
        pass
    try:
        from src.pricing.rule import PricingRuleStore

        persistence_health.append(("PricingRuleStore", PricingRuleStore().health_check()))
    except Exception:
        pass
    try:
        from src.pricing.competitor_store import CompetitorStore

        persistence_health.append(("CompetitorStore", CompetitorStore().health_check()))
    except Exception:
        pass

    return {
        "active_rules": active_count,
        "dry_run": os.getenv("PRICING_DRY_RUN", "1") == "1",
        "cron_hour": os.getenv("PRICING_CRON_HOUR", "3"),
        "last_run_at": last_run,
        "min_margin_pct": os.getenv("PRICING_MIN_MARGIN_PCT", "15"),
        "fx_trigger_pct": os.getenv("PRICING_FX_TRIGGER_PCT", "3"),
        "competitor_monitored": competitor_monitored,
        "own_changes_24h": own_24h,
        "competitor_changes_24h": competitor_24h,
        "margin_warnings": margin_warn,
        "fx_summary": fx_summary,
        "auto_apply": os.getenv("PRICING_AUTO_APPLY", "0") == "1",
        "auto_apply_threshold_pct": os.getenv("PRICING_AUTO_APPLY_THRESHOLD_PCT", "5"),
        "persistence_health": persistence_health,
    }


def _build_message_log() -> dict:
    """최근 24시간 메시지 로그 요약."""
    try:
        from src.messaging.router import MessageLog
        log = MessageLog()
        rows = log.recent(200)
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
        recent = []
        for row in rows:
            ts = row.get("sent_at") or row.get("created_at") or ""
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    from datetime import timezone as _tz
                    dt = dt.replace(tzinfo=_tz.utc)
                if dt >= cutoff:
                    recent.append(row)
            except Exception:
                recent.append(row)

        by_channel: dict = {}
        errors: dict = {}
        for row in recent:
            ch = row.get("channel", "unknown")
            by_channel.setdefault(ch, {"sent": 0, "failed": 0})
            if row.get("success") in (True, "True", "1", 1):
                by_channel[ch]["sent"] += 1
            else:
                by_channel[ch]["failed"] += 1
                err = str(row.get("error") or "알 수 없는 오류")[:80]
                errors[err] = errors.get(err, 0) + 1

        return {
            "total": len(recent),
            "by_channel": by_channel,
            "top_errors": sorted(errors.items(), key=lambda x: -x[1])[:5],
        }
    except Exception as exc:
        logger.debug("message_log 로드 실패: %s", exc)
        return {"total": 0, "by_channel": {}, "top_errors": []}


def _build_cs_bot_status() -> dict:
    try:
        auto_send_daily_limit = int(os.getenv("CS_AUTO_SEND_DAILY_LIMIT", "20"))
    except Exception:
        auto_send_daily_limit = 20
    result = {
        "faq_total": 0,
        "faq_enabled": 0,
        "faq_by_lang": {"ko": 0, "en": 0, "ja": 0, "zh": 0},
        "translation_cache_count": 0,
        "new_24h": 0,
        "unanswered": 0,
        "urgent_unanswered": 0,
        "auto_sent_24h": 0,
        "avg_response_minutes": 0.0,
        "response_rate": 0.0,
        "ai_calls_24h": 0,
        "ai_adoption_rate": 0.0,
        "ai_edit_rate": 0.0,
        "low_quality_count": 0,
        "budget_remaining_pct": 100.0,
        "auto_send": os.getenv("CS_AUTO_SEND", "0") == "1",
        "auto_send_categories": [x.strip() for x in os.getenv("CS_AUTO_SEND_CATEGORIES", "general,shipping").split(",") if x.strip()],
        "auto_send_daily_limit": auto_send_daily_limit,
        "auto_send_used_today": 0,
        "embedding_cached": "0/0",
        "sla_nearing": 0,
        "sla_overdue": 0,
        "channels": [],
        "scheduler_jobs": [],
        "scheduler_missed_24h": 0,
        "scheduler_leader_pid": "-",
        "scheduler_leader_hostname": "-",
    }
    try:
        from src.cs_bot.faq_store import FAQStore

        faq_items = FAQStore().list_all(enabled_only=False)
        result["faq_total"] = len(faq_items)
        result["faq_enabled"] = len([x for x in faq_items if x.enabled])
        by_lang = {"ko": 0, "en": 0, "ja": 0, "zh": 0}
        cache_count = 0
        emb_count = 0
        for item in faq_items:
            lang = str(item.language or "ko")
            if lang in by_lang:
                by_lang[lang] += 1
            cache_count += len(item.translations or {})
            if item.embedding:
                emb_count += 1
        result["faq_by_lang"] = by_lang
        result["translation_cache_count"] = cache_count
        result["embedding_cached"] = f"{emb_count}/{len(faq_items)}"
    except Exception as exc:
        logger.debug("cs_bot FAQ 상태 조회 실패: %s", exc)

    try:
        from src.cs_bot.inbox_store import InboxStore

        store = InboxStore()
        stats = store.stats_24h()
        result["new_24h"] = stats.get("new_24h", 0)
        result["unanswered"] = stats.get("unanswered", 0)
        result["urgent_unanswered"] = stats.get("urgent_unanswered", 0)
        rows = store.list_messages(limit=5000)
        result["auto_sent_24h"] = len([x for x in rows if x.status == "auto_handled"])
        result["avg_response_minutes"] = stats.get("avg_response_minutes", 0.0)
        result["response_rate"] = stats.get("response_rate", 0.0)
        ai_calls = len([x for x in rows if x.suggested_reply and x.received_at])
        result["ai_calls_24h"] = ai_calls
        ai_used = len([x for x in rows if x.suggested_reply and x.final_reply and x.final_reply.strip() == x.suggested_reply.strip()])
        if ai_calls > 0:
            adoption = round((ai_used / ai_calls) * 100, 1)
            result["ai_adoption_rate"] = adoption
            result["ai_edit_rate"] = round(max(0.0, 100.0 - adoption), 1)
        if rows:
            result["auto_send_used_today"] = len([x for x in rows if x.status == "auto_handled"])
    except Exception as exc:
        logger.debug("cs_bot Inbox 상태 조회 실패: %s", exc)

    try:
        from src.ai.budget import BudgetGuard

        budget = BudgetGuard().summary()
        result["budget_remaining_pct"] = max(0.0, round(100.0 - float(budget.get("pct", 0.0)), 1))
    except Exception as exc:
        logger.debug("cs_bot 예산 조회 실패: %s", exc)

    try:
        from src.cs_bot.quality_logger import get_low_quality_faqs

        low_quality = get_low_quality_faqs()
        result["low_quality_count"] = len(low_quality)
    except Exception as exc:
        logger.debug("cs_bot 품질 상태 조회 실패: %s", exc)

    try:
        from src.cs_bot.channel_adapters import list_channel_adapters

        result["channels"] = [adapter.status() for adapter in list_channel_adapters()]
    except Exception as exc:
        logger.debug("cs_bot 채널 상태 조회 실패: %s", exc)

    try:
        from src.cs_bot.inbox_store import InboxStore
        from src.cs_bot.sla import classify_sla

        summary = classify_sla(InboxStore().list_messages(limit=5000))
        result["sla_nearing"] = summary.get("nearing_count", 0)
        result["sla_overdue"] = summary.get("overdue_count", 0)
    except Exception as exc:
        logger.debug("cs_bot SLA 상태 조회 실패: %s", exc)

    try:
        from src.cs_bot.scheduler import get_scheduler_status
        sched = get_scheduler_status()
        result["scheduler_enabled"] = sched.get("enabled", False)
        result["scheduler_running"] = sched.get("running", False)
        result["scheduler_next_poll"] = sched.get("next_poll")
        result["scheduler_next_sla"] = sched.get("next_sla")
        result["scheduler_jobs"] = sched.get("jobs", [])
        result["scheduler_missed_24h"] = sched.get("missed_jobs_24h", 0)
        leader = sched.get("leader", {}) or {}
        result["scheduler_leader_pid"] = leader.get("pid", "-")
        result["scheduler_leader_hostname"] = leader.get("hostname", "-")
    except Exception as exc:
        logger.debug("cs_bot 스케줄러 상태 조회 실패: %s", exc)

    result.setdefault("scheduler_enabled", False)
    result.setdefault("scheduler_running", False)
    result.setdefault("scheduler_next_poll", None)
    result.setdefault("scheduler_next_sla", None)
    result.setdefault("scheduler_jobs", [])
    result.setdefault("scheduler_missed_24h", 0)
    result.setdefault("scheduler_leader_pid", "-")
    result.setdefault("scheduler_leader_hostname", "-")

    return result


# ---------------------------------------------------------------------------
# Phase 142 — 진단 헬퍼: 인증 상태 / 자동 리오더 / 할인 캠페인
# ---------------------------------------------------------------------------

def _build_auth_status() -> dict:
    """Phase 142: 인증 상태 카드 데이터."""
    from src.auth.admin_resolver import is_admin_session, _env_list
    admin_ok, admin_rule = is_admin_session(session)
    user_email = session.get("user_email", "")
    user_name = session.get("user_name", "")

    # OAuth 제공자 상태 확인
    base_url = _get_base_url()
    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_id_hint = ("..." + google_client_id[-8:]) if len(google_client_id) >= 8 else ("미설정" if not google_client_id else google_client_id)

    return {
        "user_email": user_email,
        "user_name": user_name,
        "is_admin": admin_ok,
        "admin_rule": admin_rule,
        "admin_emails_configured": bool(_env_list("ADMIN_EMAILS")),
        "admin_kakao_configured": bool(_env_list("ADMIN_KAKAO_IDS")),
        "admin_google_configured": bool(_env_list("ADMIN_GOOGLE_SUBS")),
        "admin_naver_configured": bool(_env_list("ADMIN_NAVER_IDS")),
        "kakao_oauth_active": bool(os.getenv("KAKAO_CLIENT_ID")),
        "google_oauth_active": bool(google_client_id),
        "naver_oauth_active": bool(os.getenv("NAVER_CLIENT_ID")),
        "google_client_id_hint": google_client_id_hint,
        "google_redirect_uri": f"{base_url}/auth/google/callback",
        "flash_isolation_enabled": True,  # Phase 142 적용 완료
    }


def _build_auto_reorder_status() -> dict:
    """Phase 142: 자동 리오더 상태 카드 데이터."""
    result = {
        "enabled": os.getenv("AUTO_REORDER_ENABLED", "0") == "1",
        "auto_place": os.getenv("AUTO_REORDER_AUTO_PLACE", "0") == "1",
        "daily_budget_krw": int(os.getenv("AUTO_REORDER_DAILY_BUDGET_KRW", "500000")),
        "safety_days": int(os.getenv("AUTO_REORDER_SAFETY_DAYS", "14")),
        "pending_count": 0,
        "estimated_cost_krw": 0,
        "last_checked_ago": "알 수 없음",
    }
    try:
        from src.inventory.auto_reorder import AutoReorderEngine
        engine = AutoReorderEngine()
        summary = engine.summary()
        result["pending_count"] = summary.get("pending_count", 0)
        result["estimated_cost_krw"] = summary.get("estimated_cost_krw", 0)
        result["last_checked_ago"] = summary.get("last_checked_ago", "알 수 없음")
    except Exception as exc:
        logger.debug("auto_reorder 상태 조회 실패: %s", exc)
    return result


def _build_discount_campaign_status() -> dict:
    """Phase 142: 할인 캠페인 상태 카드 데이터."""
    result = {
        "enabled": os.getenv("DISCOUNT_CAMPAIGN_ENABLED", "0") == "1",
        "max_pct": int(os.getenv("DISCOUNT_CAMPAIGN_MAX_PCT", "20")),
        "margin_floor_pct": int(os.getenv("DISCOUNT_CAMPAIGN_MARGIN_FLOOR_PCT", "10")),
        "recommended_count": 0,
        "active_count": 0,
        "overstocked_skus": 0,
    }
    try:
        from src.marketing.discount_campaign import DiscountCampaignEngine
        engine = DiscountCampaignEngine()
        summary = engine.summary()
        result["recommended_count"] = summary.get("recommended_count", 0)
        result["active_count"] = summary.get("active_count", 0)
        result["overstocked_skus"] = summary.get("overstocked_skus", 0)
    except Exception as exc:
        logger.debug("discount_campaign 상태 조회 실패: %s", exc)
    return result


def _build_sourcing_pipeline_status() -> dict:
    """Phase 143: 소싱 파이프라인 상태 카드 데이터."""
    result = {
        "active_watches": 0,
        "total_watches": 0,
        "candidates_24h": 0,
        "pending_approval": 0,
        "auto_listed": 0,
        "avg_margin_pct": 0.0,
        "watch_interval_minutes": int(os.getenv("SOURCING_WATCH_INTERVAL_MINUTES", "60")),
        "min_margin_pct": float(os.getenv("SOURCING_AUTO_QUEUE_MIN_MARGIN_PCT", "15")),
        "auto_publish_enabled": os.getenv("LISTING_AUTO_PUBLISH", "0") == "1",
        "image_pipeline_enabled": os.getenv("IMAGE_PIPELINE_ENABLED", "1") == "1",
        "image_inpaint_enabled": os.getenv("IMAGE_INPAINT_ENABLED", "1") == "1",
        "translation_quality_tier": os.getenv("TRANSLATION_QUALITY_TIER", "high"),
        "deepl_configured": bool(os.getenv("DEEPL_API_KEY")),
    }
    try:
        from src.sourcing.pipeline import pipeline_stats
        stats = pipeline_stats()
        result.update(stats)
    except Exception as exc:
        logger.debug("sourcing_pipeline 상태 조회 실패: %s", exc)
    try:
        from src.listing.auto_publish import listing_stats
        lst = listing_stats()
        result["listings_24h"] = lst.get("listings_24h", 0)
        result["image_success_pct"] = lst.get("image_success_pct", 0)
    except Exception as exc:
        logger.debug("listing 상태 조회 실패: %s", exc)
    return result


def _build_ads_status() -> dict:
    """Phase 144: 광고 자동 운영 상태 카드 데이터."""
    result = {
        "enabled": os.getenv("ADS_AUTO_CAMPAIGN_ENABLED", "0") == "1",
        "auto_launch": os.getenv("ADS_AUTO_CAMPAIGN_AUTO_LAUNCH", "0") == "1",
        "daily_budget_krw": int(os.getenv("ADS_DAILY_BUDGET_KRW", "20000")),
        "target_roas": float(os.getenv("ADS_TARGET_ROAS", "3.0")),
        "bid_adjust_max_pct": float(os.getenv("ADS_BID_ADJUST_MAX_PCT", "20")),
        "keyword_provider": os.getenv("KEYWORD_OPT_PROVIDER", "mock"),
        "active_campaigns": 0,
        "by_channel": {},
        "cost_krw_24h": 0,
        "revenue_krw_24h": 0,
        "roas_24h": 0.0,
        "pending_recs": 0,
        "bid_adjustments_24h": 0,
    }
    try:
        from src.ads.auto_campaign import ads_stats
        stats = ads_stats()
        result.update(stats)
    except Exception as exc:
        logger.debug("ads_status 조회 실패: %s", exc)
    return result


SELLER_SIDEBAR_LINKS = [
    ("/seller/dashboard", "📊 대시보드"),
    ("/seller/manual-collect", "🔍 수동 수집기"),
    ("/seller/margin", "💰 마진 계산기"),
    ("/seller/markets", "🏪 마켓 현황"),
    ("/seller/catalog", "📦 상품 카탈로그"),
    ("/seller/orders", "🚚 주문 관리"),
    ("/seller/orders/auto", "📦 주문 자동 처리"),
    ("/seller/notifications", "🔔 알림 설정"),
    ("/seller/cs/messaging", "💬 고객 메시징"),
    ("/seller/cs/autoreply", "🤖 CS 자동응답"),
    ("/seller/api/status", "🔑 API 상태"),
    ("/seller/me", "👤 마이페이지"),
    ("/seller/api/tokens", "🔐 API 토큰"),
    ("/seller/bookmarklet", "📌 북마클릿"),
    ("/seller/discovery", "🔎 Discovery"),
    ("/seller/collect-history", "📜 수집 이력"),
    ("/seller/pricing/rules", "💵 가격 정책 룰"),
    ("/seller/pricing/competitors", "🕵️ 경쟁사"),
    ("/seller/pricing/fx-impact", "🔄 환율 영향"),
    ("/seller/analytics", "📈 BI 분석"),
    ("/seller/inventory/reorder", "📦 자동 리오더"),
    ("/seller/marketing/campaigns", "🎟️ 할인 캠페인"),
    ("/seller/sourcing/watches", "🔎 소싱 watches"),
    ("/seller/sourcing/candidates", "📥 후보 큐"),
    ("/seller/listing/history", "📤 등록 이력"),
    ("/seller/media/queue", "🖼️ 이미지 큐"),
    ("/seller/ads/campaigns", "📣 광고 캠페인"),
    ("/seller/ads/keywords", "🎯 키워드 최적화"),
    ("/seller/shipping/tracking", "🚚 배송 모니터링"),
    ("/seller/settlement", "💰 정산 리포트"),
    ("/seller/cs/inbox", "📥 통합 인박스"),
    ("/seller/returns/inbox", "↩️ 반품/환불"),
    # Phase 147
    ("/seller/inventory/omni", "🔄 옴니채널 재고"),
    ("/seller/me/notifications", "🔔 푸시 알림 설정"),
    # Phase 148
    ("/seller/wholesale/tiers", "🏢 도매 등급"),
    ("/seller/wholesale/applications", "📋 B2B 신청 큐"),
    ("/seller/subscriptions", "🔁 정기구독 관리"),
    ("/seller/me/subscriptions", "🔁 내 구독"),
]


def _build_route_check_status() -> dict:
    """Phase 144: 라우트 등록 점검 상태 데이터."""
    # Phase별 핵심 라우트 화이트리스트
    key_routes = [
        ("seller_console.cs_inbox", "/seller/cs/inbox"),
        ("seller_console.pricing_rules", "/seller/pricing/rules"),
        ("seller_console.manual_collect_alias", "/seller/manual-collect"),
        ("seller_console.sourcing_watches", "/seller/sourcing/watches"),
        ("seller_console.sourcing_candidates", "/seller/sourcing/candidates"),
        ("seller_console.listing_history", "/seller/listing/history"),
        ("seller_console.media_queue", "/seller/media/queue"),
        ("seller_console.ads_campaigns", "/seller/ads/campaigns"),
        ("seller_console.ads_keywords", "/seller/ads/keywords"),
        ("seller_console.orders_auto", "/seller/orders/auto"),
        ("seller_console.shipping_tracking", "/seller/shipping/tracking"),
        ("seller_console.inventory_reorder", "/seller/inventory/reorder"),
        ("seller_console.marketing_campaigns", "/seller/marketing/campaigns"),
        ("seller_console.returns_inbox", "/seller/returns/inbox"),
        ("seller_console.settlement_report", "/seller/settlement"),
        # Phase 147
        ("seller_console.inventory_omni", "/seller/inventory/omni"),
        ("seller_console.me_notifications", "/seller/me/notifications"),
        ("admin_panel.admin_jobs", "/admin/jobs"),
        # Phase 148
        ("seller_console.wholesale_tiers", "/seller/wholesale/tiers"),
        ("seller_console.wholesale_applications", "/seller/wholesale/applications"),
        ("seller_console.seller_subscriptions", "/seller/subscriptions"),
        ("seller_console.me_subscriptions", "/seller/me/subscriptions"),
    ]

    sidebar_links = SELLER_SIDEBAR_LINKS

    registered = []
    missing = []
    try:
        from flask import current_app
        view_funcs = current_app.view_functions
        total = len(view_funcs)

        for endpoint, url in key_routes:
            if endpoint in view_funcs:
                registered.append({"endpoint": endpoint, "url": url, "ok": True})
            else:
                missing.append({"endpoint": endpoint, "url": url, "ok": False})
                logger.warning("라우트 미등록: %s → %s", endpoint, url)

        return {
            "total_routes": total,
            "key_routes": registered + missing,
            "missing_count": len(missing),
            "sidebar_links": sidebar_links,
            "ok": len(missing) == 0,
        }
    except Exception as exc:
        logger.debug("route_check 실패: %s", exc)
        return {
            "total_routes": 0,
            "key_routes": [],
            "missing_count": -1,
            "sidebar_links": sidebar_links,
            "ok": False,
        }


def _build_sidebar_nav_status() -> dict:
    registered_routes = {rule.rule for rule in current_app.url_map.iter_rules()}
    broken = [url for url, _label in SELLER_SIDEBAR_LINKS if url not in registered_routes]
    return {
        "seller_menu_count": len(SELLER_SIDEBAR_LINKS),
        "registered_routes": len(SELLER_SIDEBAR_LINKS) - len(broken),
        "broken_links": len(broken),
        "broken_link_urls": broken,
        "branch_ok": True,
    }


def _build_order_auto_status() -> dict:
    try:
        from src.orders.auto_processor import OrderAutoProcessor

        proc = OrderAutoProcessor()
        summary = proc.summary_24h()
    except Exception:
        summary = {
            "new_orders_24h": 0,
            "auto_processed_24h": 0,
            "manual_intervention_24h": 0,
            "auto_place_po": False,
            "invoice_sync_ok": True,
        }
    summary["enabled"] = os.getenv("ORDER_AUTO_PROCESS_ENABLED", "1") == "1"
    return summary


def _build_cs_unified_inbox_status() -> dict:
    try:
        from src.cs.unified_inbox import UnifiedInbox

        inbox = UnifiedInbox()
        summary = inbox.summary_24h()
    except Exception:
        summary = {"unanswered": 0, "sla_violations": 0, "ai_draft_enabled": False, "processed_24h": 0}
    summary["enabled"] = os.getenv("CS_UNIFIED_INBOX_ENABLED", "1") == "1"
    return summary


def _build_shipping_monitor_status() -> dict:
    try:
        from src.shipping.tracker import ShippingMonitor

        monitor = ShippingMonitor()
        summary = monitor.summary()
    except Exception:
        summary = {"provider": "mock", "tracking_count": 0, "delay_suspected": 0, "lost_suspected": 0}
    return summary


def _build_header_branch_status() -> dict:
    return {
        "seller_console": True,
        "admin_console": True,
        "global_page": True,
        "error_404": True,
    }


def _build_returns_automation_status() -> dict:
    try:
        from src.returns.auto_processor import ReturnsAutoProcessor

        summary = ReturnsAutoProcessor().summary_24h()
    except Exception:
        summary = {"requests_24h": 0, "auto_approved_24h": 0, "manual_queue_24h": 0, "avg_minutes": "-"}
    return summary


def _build_settlement_report_status() -> dict:
    try:
        from src.settlement.reporter import SettlementReporter
        from datetime import datetime

        report = SettlementReporter().monthly_report(datetime.now().strftime("%Y-%m"), rows=[])
        return {
            "month_sales_krw": report.get("total_sales_krw", 0),
            "channel_share": report.get("by_channel", {}),
            "next_settlement_date": report.get("next_settlement_date", "-"),
        }
    except Exception:
        return {"month_sales_krw": 0, "channel_share": {}, "next_settlement_date": "-"}


# ---------------------------------------------------------------------------
# Phase 147 — 진단 헬퍼
# ---------------------------------------------------------------------------

def _build_pwa_status() -> dict:
    """Phase 147: PWA/모바일 상태 카드 데이터."""
    pwa_enabled = os.getenv("PWA_ENABLED", "1") == "1"
    return {
        "pwa_enabled": pwa_enabled,
        "viewport_meta": True,  # _base.html에 고정 포함
        "manifest_linked": True,  # _base.html에 고정 포함
        "sw_registered": True,   # _base.html JS에서 등록
        "app_name": os.getenv("PWA_APP_NAME", "Proxy Commerce"),
    }


def _build_web_push_status() -> dict:
    """Phase 147: Web Push 상태 카드 데이터."""
    try:
        from src.notifications.web_push import push_status
        return push_status()
    except Exception as exc:
        logger.debug("web_push 상태 조회 실패: %s", exc)
        return {"vapid_configured": False, "subscriber_count": 0, "vapid_public_hint": "오류"}


def _build_omni_sync_status() -> dict:
    """Phase 147: 옴니채널 재고 동기화 상태 카드 데이터."""
    try:
        from src.inventory.omni_sync import OmniInventorySyncer
        return OmniInventorySyncer().summary()
    except Exception as exc:
        logger.debug("omni_sync 상태 조회 실패: %s", exc)
        return {
            "enabled": False, "mode": "common_pool", "configured_channels": [],
            "channel_count": 0, "failure_24h": 0, "sync_interval_sec": 60,
        }


def _build_job_queue_status() -> dict:
    """Phase 147: 멀티워커 큐 상태 카드 데이터."""
    try:
        from src.jobs.queue_manager import get_queue
        return get_queue().summary()
    except Exception as exc:
        logger.debug("job_queue 상태 조회 실패: %s", exc)
        return {
            "backend": os.getenv("JOB_QUEUE_BACKEND", "db"),
            "queued": 0, "running": 0, "dead_letters": 0,
            "by_category": {}, "worker_distribution": {}, "max_retries": 3,
        }


def _page_route_available(endpoint: str) -> bool:
    return endpoint in current_app.view_functions


# ---------------------------------------------------------------------------
# Phase 148 — 진단 헬퍼
# ---------------------------------------------------------------------------

def _build_version_display_status() -> dict:
    """Phase 148: 푸터 버전 표시 상태."""
    try:
        from src.version import get_current_phase, CURRENT_PHASE, APP_VERSION
        current = get_current_phase()
        return {
            "current_phase": current,
            "hardcoded_phase": CURRENT_PHASE,
            "app_version": APP_VERSION,
            "ok": True,
        }
    except Exception as exc:
        logger.debug("version 상태 조회 실패: %s", exc)
        return {"current_phase": 0, "hardcoded_phase": 0, "app_version": "?", "ok": False}


def _build_wholesale_status() -> dict:
    """Phase 148: B2B 도매 모드 상태."""
    try:
        from src.wholesale.tier_manager import WholesaleTierManager
        from src.wholesale.application_manager import WholesaleApplicationManager, ApplicationStatus
        tier_mgr = WholesaleTierManager()
        app_mgr = WholesaleApplicationManager()
        return {
            "enabled": tier_mgr.enabled,
            "tier_count": len(tier_mgr.list_tiers()),
            "total_applications": app_mgr.count(),
            "pending_applications": app_mgr.count(ApplicationStatus.PENDING),
            "approved_members": app_mgr.count(ApplicationStatus.APPROVED),
        }
    except Exception as exc:
        logger.debug("wholesale 상태 조회 실패: %s", exc)
        return {
            "enabled": os.getenv("WHOLESALE_ENABLED", "1") == "1",
            "tier_count": 0,
            "total_applications": 0,
            "pending_applications": 0,
            "approved_members": 0,
        }


def _build_product_subscription_status() -> dict:
    """Phase 148: 정기구독 상품 상태."""
    try:
        from src.product_subscriptions.subscription_products import ProductSubscriptionManager
        return ProductSubscriptionManager().summary()
    except Exception as exc:
        logger.debug("product_subscription 상태 조회 실패: %s", exc)
        return {
            "enabled": os.getenv("SUBSCRIPTION_ENABLED", "1") == "1",
            "pg_provider": os.getenv("SUBSCRIPTION_PG_PROVIDER", "mock"),
            "active_count": 0,
            "billed_this_week": 0,
            "failed_count": 0,
            "cancelled_count": 0,
            "total_count": 0,
        }


def _build_emergency_access_status() -> dict:
    import os

    bootstrap_token = os.getenv("ADMIN_BOOTSTRAP_TOKEN", "")
    masked_prefix = f"{bootstrap_token[:6]}..." if len(bootstrap_token) >= 6 else ("***" if bootstrap_token else None)
    diagnostic_stats = {"active_count": 0, "latest_issued_at": None}
    diagnostic_runtime = {
        "worker_pid": "-",
        "web_concurrency": "-",
        "nonce_cache_size": 0,
        "issued_last_hour": 0,
        "redeemed_last_hour": 0,
    }
    try:
        from src.auth.diagnostic_token import runtime_stats, token_status

        diagnostic_stats = token_status()
        diagnostic_runtime = runtime_stats()
    except Exception as exc:
        logger.debug("diagnostic token 상태 조회 실패: %s", exc)

    return {
        "magic_link_url": "/auth/magic-link",
        "bootstrap_configured": bool(os.getenv("ADMIN_BOOTSTRAP_TOKEN")),
        "bootstrap_url": "/auth/bootstrap?token=<TOKEN>&email=<ADMIN_EMAIL>",
        "bootstrap_masked_prefix": masked_prefix,
        "admin_emails_configured": bool(os.getenv("ADMIN_EMAILS")),
        "diagnostic_reveal_enabled": os.getenv("DIAGNOSTIC_REVEAL", "0") == "1",
        "diagnostic_issue_url": "/auth/diagnostic-token/issue?reveal_safe=1&format=html",
        "diagnostic_active_count": diagnostic_stats["active_count"],
        "diagnostic_latest_issued_at": diagnostic_stats["latest_issued_at"],
        "diagnostic_worker_pid": diagnostic_runtime["worker_pid"],
        "diagnostic_web_concurrency": diagnostic_runtime["web_concurrency"] or "-",
        "diagnostic_nonce_cache_size": diagnostic_runtime["nonce_cache_size"],
        "diagnostic_issued_last_hour": diagnostic_runtime["issued_last_hour"],
        "diagnostic_redeemed_last_hour": diagnostic_runtime["redeemed_last_hour"],
    }


def _build_oauth_diagnostics(base_url: str, oauth_urls: dict) -> list[dict]:
    import os
    from urllib.parse import urlparse

    domain = urlparse(base_url).netloc or base_url.replace("https://", "").replace("http://", "")
    privacy_url = f"{base_url}/privacy"
    terms_url = f"{base_url}/terms"
    privacy_ok = _page_route_available("legal.privacy")
    terms_ok = _page_route_available("legal.terms")

    return [
        {
            "name": "Google OAuth",
            "client_id_env": "GOOGLE_OAUTH_CLIENT_ID",
            "client_secret_env": "GOOGLE_OAUTH_CLIENT_SECRET",
            "client_id_set": bool(os.getenv("GOOGLE_OAUTH_CLIENT_ID")),
            "client_secret_set": bool(os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")),
            "callback_url": oauth_urls["Google"],
            "checklist": [
                {"label": "Google Cloud Console → 클라이언트 → 콜백 URL 정확히 등록", "done": None},
                {
                    "label": "OAuth 동의 화면 → 게시 상태 확인",
                    "done": None,
                    "details": [
                        "테스트 모드: 테스트 사용자 추가 필수",
                        "프로덕션: 도메인 검증 + 개인정보처리방침 + 약관 필수",
                    ],
                },
                {"label": f"승인된 도메인: {domain}만 유지", "done": None},
                {"label": f"개인정보처리방침 URL: {privacy_url}", "done": privacy_ok},
                {"label": f"이용약관 URL: {terms_url}", "done": terms_ok},
                {"label": "변경 후 5~10분 대기 (Google 캐시)", "done": None},
            ],
        },
        {
            "name": "Kakao OAuth",
            "client_id_env": "KAKAO_REST_API_KEY",
            "client_secret_env": "KAKAO_CLIENT_SECRET",
            "client_id_set": bool(os.getenv("KAKAO_REST_API_KEY")),
            "client_secret_set": bool(os.getenv("KAKAO_CLIENT_SECRET")),
            "callback_url": oauth_urls["Kakao"],
            "checklist": [
                {"label": f"Web 플랫폼 등록: {base_url}", "done": None},
                {"label": f"Redirect URI 정확히 등록: {oauth_urls['Kakao']}", "done": None},
                {"label": "카카오 로그인 활성화", "done": None},
                {"label": "필수 동의 항목(이메일/닉네임) 확인", "done": None},
                {"label": f"개인정보처리방침 URL: {privacy_url}", "done": privacy_ok},
                {"label": f"이용약관 URL: {terms_url}", "done": terms_ok},
            ],
        },
        {
            "name": "Naver OAuth",
            "client_id_env": "NAVER_CLIENT_ID",
            "client_secret_env": "NAVER_CLIENT_SECRET",
            "client_id_set": bool(os.getenv("NAVER_CLIENT_ID")),
            "client_secret_set": bool(os.getenv("NAVER_CLIENT_SECRET")),
            "callback_url": oauth_urls["Naver"],
            "checklist": [
                {"label": f"서비스 URL/Callback URL 정확히 등록: {oauth_urls['Naver']}", "done": None},
                {"label": "멤버 관리는 네이버 로그인 ID 기준으로 등록", "done": None},
                {"label": "앱 상태가 개발 중이면 등록된 멤버만 로그인 가능", "done": None},
                {"label": "정식 서비스 전환을 위해 앱 검수 요청", "done": None},
                {"label": f"개인정보처리방침 URL: {privacy_url}", "done": privacy_ok},
                {"label": f"이용약관 URL: {terms_url}", "done": terms_ok},
            ],
        },
    ]


# ── 진단 HTML 템플릿 ──────────────────────────────────────────────────────

_DIAGNOSTICS_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>운영 진단 — Admin</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
  <style>
    body { background: #f8f9fa; }
    .sidebar { min-height: 100vh; background: #212529; }
    .sidebar .nav-link { color: #adb5bd; }
    .sidebar .nav-link:hover { color: #fff; }
    .status-ok { color: #198754; }
    .status-fail { color: #dc3545; }
    .status-missing { color: #6c757d; }
    .status-dry_run { color: #0dcaf0; }
    .copy-btn { cursor: pointer; }
  </style>
</head>
<body>
{% include "partials/topnav.html" %}
<div class="container-fluid">
<div class="row">
  <nav class="col-md-2 sidebar p-3">
    <h5 class="text-white mb-3">🛒 Admin</h5>
    <ul class="nav flex-column">
      <li><a class="nav-link" href="/admin/">대시보드</a></li>
      <li><a class="nav-link" href="/admin/products">📋 상품 목록</a></li>
      <li><a class="nav-link" href="/admin/orders">📦 주문 목록</a></li>
      <li><a class="nav-link" href="/admin/inventory">📊 재고 현황</a></li>
      <li><a class="nav-link text-white fw-bold" href="/admin/diagnostics">🔧 진단</a></li>
      <li><a class="nav-link" href="/admin/users">👥 사용자 관리</a></li>
      <li><a class="nav-link" href="/admin/env">⚙️ 환경변수</a></li>
      <li><a class="nav-link" href="/admin/logs">📜 로그</a></li>
      <li><a class="nav-link" href="/seller/">← 셀러 콘솔</a></li>
    </ul>
  </nav>
  <main class="col-md-10 p-4">
    <h4 class="mb-4">🔍 운영 진단 대시보드</h4>
    {% if env.DIAGNOSTIC_REVEAL == '1' %}
    <div class="alert alert-warning">
      ⚠️ <b>비상 진입 모드 ON</b> — 운영 안정화 완료 시
      <code>DIAGNOSTIC_REVEAL=0</code>으로 되돌리는 것을 권장합니다.
    </div>
    {% endif %}

    <!-- 섹션 1: 환경변수 매트릭스 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">📋 섹션 1 — 환경변수 매트릭스</div>
      <div class="card-body">
        <div class="row g-2">
          {% set categories = env_matrix | map(attribute='category') | unique | list %}
          {% for cat in categories %}
            <div class="col-md-6 mb-3">
              <h6 class="text-muted text-uppercase small">{{ cat }}</h6>
              <table class="table table-sm table-hover mb-0">
                <tbody>
                {% for api in env_matrix if api.category == cat %}
                  <tr>
                    <td class="w-50">
                      <span class="fw-semibold">{{ api.name }}</span>
                      <br><small class="text-muted">{{ api.purpose[:50] }}</small>
                    </td>
                    <td>
                      {% if api.status == 'active' %}
                        <span class="badge bg-success">✅ 활성</span>
                      {% else %}
                        <span class="badge bg-secondary">❌ 누락</span>
                        {% if api.docs_url %}
                          <a href="{{ api.docs_url }}" target="_blank" class="ms-1 small">발급 →</a>
                        {% endif %}
                      {% endif %}
                    </td>
                  </tr>
                {% endfor %}
                </tbody>
              </table>
            </div>
          {% endfor %}
        </div>
      </div>
    </div>

    <!-- 섹션 2: 비상 로그인 + OAuth 진단 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">🆘 섹션 2 — 비상 로그인 + OAuth 진단</div>
      <div class="card-body">
        <div class="alert alert-warning">
          <div class="fw-semibold mb-2">🆘 비상 진입 도구 (OAuth 정상화 전 임시)</div>
          <ul class="mb-0 ps-3">
            <li>Magic Link: <a href="{{ emergency_access.magic_link_url }}">{{ emergency_access.magic_link_url }}</a></li>
            <li>
              Diagnostic Token:
              <a href="{{ emergency_access.diagnostic_issue_url }}" target="_blank">{{ emergency_access.diagnostic_issue_url }}</a>
              {% if emergency_access.diagnostic_reveal_enabled %}
                <span class="badge bg-success">DIAGNOSTIC_REVEAL=1</span>
              {% else %}
                <span class="badge bg-secondary">DIAGNOSTIC_REVEAL=0</span>
              {% endif %}
            </li>
            <li>
              활성 토큰: <span class="fw-semibold">{{ emergency_access.diagnostic_active_count }}</span>개
              {% if emergency_access.diagnostic_latest_issued_at %}
                <span class="small text-muted">(최근 발급: {{ emergency_access.diagnostic_latest_issued_at }})</span>
              {% endif %}
            </li>
            <li class="small">
              Worker PID: <code>{{ emergency_access.diagnostic_worker_pid }}</code> ·
              WEB_CONCURRENCY: <code>{{ emergency_access.diagnostic_web_concurrency }}</code> ·
              nonce 캐시: <span class="fw-semibold">{{ emergency_access.diagnostic_nonce_cache_size }}</span>
            </li>
            <li class="small">
              최근 1시간 issue/redeem:
              <span class="fw-semibold">{{ emergency_access.diagnostic_issued_last_hour }}</span> /
              <span class="fw-semibold">{{ emergency_access.diagnostic_redeemed_last_hour }}</span>
            </li>
            <li>
              Bootstrap:
              {% if emergency_access.bootstrap_configured %}
                <span class="badge bg-success">ADMIN_BOOTSTRAP_TOKEN 설정됨 ✅</span>
                {% if emergency_access.bootstrap_masked_prefix %}
                  <span class="small text-muted">(prefix: {{ emergency_access.bootstrap_masked_prefix }})</span>
                {% endif %}
              {% else %}
                <span class="badge bg-secondary">ADMIN_BOOTSTRAP_TOKEN 미설정</span>
              {% endif %}
              <div class="small text-muted mt-1">사용법: <code>{{ emergency_access.bootstrap_url }}</code></div>
            </li>
            <li class="small mt-1">권장: OAuth 정상화 후 ADMIN_BOOTSTRAP_TOKEN 환경변수 삭제</li>
          </ul>
          <div class="mt-3 d-flex gap-2 flex-wrap">
            <a class="btn btn-sm btn-danger" target="_blank" href="{{ emergency_access.diagnostic_issue_url }}">🆘 Diagnostic Token 즉시 발급 + 화면 표시</a>
            <form method="POST" action="/admin/diagnostics/expire-diagnostic-tokens">
              <button type="submit" class="btn btn-sm btn-outline-danger">🧯 이 토큰들 모두 만료시키기</button>
            </form>
          </div>
          <form method="POST" action="/admin/diagnostics/issue-magic-link" class="mt-3 d-flex gap-2 flex-wrap">
            <input type="email" name="email" class="form-control form-control-sm" style="max-width:280px" placeholder="admin 이메일" required>
            <button type="submit" class="btn btn-sm btn-outline-primary">📧 Magic Link 즉시 발급 (이메일+화면 표시)</button>
          </form>
          {% if emergency_access.issued_magic_link %}
            <div class="mt-2 p-2 bg-white border rounded small">
              <div class="fw-semibold mb-1">발급된 1회용 링크</div>
              <code>{{ emergency_access.issued_magic_link }}</code>
            </div>
          {% endif %}
        </div>

        {% for item in oauth_diagnostics %}
          <div class="border rounded p-3 mb-3 bg-white">
            <div class="d-flex flex-wrap justify-content-between align-items-start gap-3">
              <div>
                <h5 class="mb-2">🔐 {{ item.name }}</h5>
                <div class="small">
                  <div>{{ item.client_id_env }}:
                    {% if item.client_id_set %}<span class="badge bg-success">✅ 설정됨</span>{% else %}<span class="badge bg-secondary">❌ 누락</span>{% endif %}
                  </div>
                  <div class="mt-1">{{ item.client_secret_env }}:
                    {% if item.client_secret_set %}<span class="badge bg-success">✅ 설정됨</span>{% else %}<span class="badge bg-secondary">❌ 누락</span>{% endif %}
                  </div>
                  <div class="mt-2">콜백 URL (등록필요): <code>{{ item.callback_url }}</code></div>
                </div>
              </div>
              <button class="btn btn-outline-secondary btn-sm copy-btn"
                      onclick="navigator.clipboard.writeText('{{ item.callback_url }}').then(()=>this.textContent='✅ 복사됨')">
                📋 콜백 URL 복사
              </button>
            </div>
            <details class="mt-3">
              <summary class="fw-semibold">트러블슈팅 체크리스트</summary>
              <ul class="mt-2 mb-0 ps-3">
                {% for check in item.checklist %}
                  <li class="mb-1">
                    {% if check.done is sameas true %}
                      ✅
                    {% elif check.done is sameas false %}
                      ❌
                    {% else %}
                      ⬜
                    {% endif %}
                    {{ check.label }}
                    {% if check.details %}
                      <ul class="small text-muted mt-1">
                        {% for detail in check.details %}
                          <li>{{ detail }}</li>
                        {% endfor %}
                      </ul>
                    {% endif %}
                  </li>
                {% endfor %}
              </ul>
            </details>
          </div>
        {% endfor %}
      </div>
    </div>

    <!-- 섹션 3: 메신저 채널 health -->
    <div class="card mb-4">
      <div class="card-header fw-bold">📡 섹션 3 — 메신저 채널 Health</div>
      <div class="card-body">
        <div class="row g-3">
          {% for channel, info in messenger_health.items() %}
            <div class="col-md-4">
              <div class="card h-100">
                <div class="card-body">
                  <h6 class="card-title">
                    {% if info.status == 'ok' or info.status == 'active' %}
                      <span class="status-ok">✅</span>
                    {% elif info.status == 'missing' %}
                      <span class="status-missing">⬜</span>
                    {% else %}
                      <span class="status-fail">❌</span>
                    {% endif %}
                    {{ channel }}
                  </h6>
                  {% if info.status == 'ok' %}
                    <p class="text-success small mb-1">봇: {{ info.bot or '' }}</p>
                    {% if info.chat_title %}<p class="text-muted small mb-0">채팅: {{ info.chat_title }}</p>{% endif %}
                  {% elif info.hint %}
                    <p class="text-muted small mb-0">{{ info.hint }}</p>
                  {% elif info.error %}
                    <p class="text-danger small mb-0">{{ info.error[:80] }}</p>
                  {% endif %}
                  {% if channel == 'telegram' %}
                    <button class="btn btn-outline-primary btn-sm mt-2"
                            onclick="fetch('/admin/diagnostics/test-telegram',{method:'POST'}).then(r=>r.json()).then(d=>alert(d.message||d.error))">
                      📨 테스트
                    </button>
                    <button class="btn btn-outline-secondary btn-sm mt-2"
                            onclick="fetch('/admin/diagnostics/telegram-health').then(r=>r.json()).then(d=>alert(JSON.stringify(d,null,2)))">
                      🔄 재진단
                    </button>
                  {% endif %}
                </div>
              </div>
            </div>
          {% endfor %}
        </div>
      </div>
    </div>

    <!-- 섹션 4: 마켓 어댑터 health -->
    <div class="card mb-4">
      <div class="card-header fw-bold">🏪 섹션 4 — 마켓 어댑터 Health</div>
      <div class="card-body">
        <div class="row g-3">
          {% for market, info in market_health.items() %}
            <div class="col-md-3">
              <div class="card h-100">
                <div class="card-body">
                  <h6>{% if info.status == 'ok' %}✅{% elif info.status == 'missing' %}⬜{% else %}❌{% endif %} {{ market }}</h6>
                  <p class="small text-muted mb-0">{{ info.detail or info.status }}</p>
                </div>
              </div>
            </div>
          {% endfor %}
        </div>
      </div>
    </div>

    <!-- 섹션 5: 가격 자동화 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">💰 가격 자동화 (Phase 140)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>활성 룰: {{ pricing_status.active_rules }}개 / 모니터링 중인 경쟁사 상품: {{ pricing_status.competitor_monitored }}개</li>
          <li>24h 가격 변경: 본사 {{ pricing_status.own_changes_24h }}건 / 경쟁사 {{ pricing_status.competitor_changes_24h }}건</li>
          <li>마진 미달 경고: {{ pricing_status.margin_warnings }}건</li>
          <li>환율 변동: {{ pricing_status.fx_summary }}{% if pricing_status.fx_summary == '정상' %} (정상){% endif %}</li>
          <li>자동 적용: {% if pricing_status.auto_apply %}<span class="badge bg-danger">ON</span>{% else %}<span class="badge bg-secondary">OFF</span>{% endif %} ({{ pricing_status.auto_apply_threshold_pct }}% 이내만)</li>
        </ul>
        {% if pricing_status.persistence_health %}
          <div class="alert alert-light border small">
            <div class="fw-semibold mb-1">Store 영속성 점검</div>
            <ul class="mb-0">
              {% for name, st in pricing_status.persistence_health %}
                <li>{{ name }}: Sheets {{ '✅' if st.sheets else '❌' }} + JSONL {{ '✅' if st.ok else '❌' }}</li>
              {% endfor %}
            </ul>
          </div>
        {% endif %}
        <div class="d-flex flex-wrap gap-2">
          <a href="/seller/pricing/rules" class="btn btn-outline-primary btn-sm">룰 관리</a>
          <a href="/seller/pricing/competitors" class="btn btn-outline-primary btn-sm">경쟁사</a>
          <a href="/seller/pricing/fx-impact" class="btn btn-outline-primary btn-sm">환율 영향</a>
          <a href="/seller/pricing/history" class="btn btn-outline-primary btn-sm">마진 점검</a>
        </div>
      </div>
    </div>

    <!-- 섹션 6: 최근 24시간 알림 로그 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">📊 섹션 6 — 최근 24시간 알림 로그</div>
      <div class="card-body">
        <p class="text-muted small">총 {{ message_log.total }}건</p>
        {% if message_log.by_channel %}
          <table class="table table-sm table-hover">
            <thead><tr><th>채널</th><th>성공</th><th>실패</th></tr></thead>
            <tbody>
            {% for ch, stats in message_log.by_channel.items() %}
              <tr>
                <td>{{ ch }}</td>
                <td class="text-success">{{ stats.sent }}</td>
                <td class="{% if stats.failed > 0 %}text-danger fw-bold{% endif %}">{{ stats.failed }}</td>
              </tr>
            {% endfor %}
            </tbody>
          </table>
        {% else %}
          <p class="text-muted">로그 없음</p>
        {% endif %}
        {% if message_log.top_errors %}
          <h6 class="mt-3">오류 Top-{{ message_log.top_errors | length }}</h6>
          <ul class="list-unstyled">
          {% for err, cnt in message_log.top_errors %}
            <li class="text-danger small">{{ err }} <span class="badge bg-danger">{{ cnt }}</span></li>
          {% endfor %}
          </ul>
        {% endif %}
      </div>
    </div>

    <!-- 섹션 7: CS 봇 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">🤖 섹션 7 — CS 봇 (Phase 139)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>활성 채널: {% for ch in cs_bot_status.channels %}{{ ch.channel }} {% if ch.enabled %}✅{% else %}❌{% endif %}{% if not loop.last %}, {% endif %}{% endfor %}</li>
          <li>FAQ: {{ cs_bot_status.faq_total }}개 (KO {{ cs_bot_status.get('faq_by_lang', {}).get('ko', 0) }}, EN {{ cs_bot_status.get('faq_by_lang', {}).get('en', 0) }} 자동번역 캐시 {{ cs_bot_status.get('translation_cache_count', 0) }}, JA {{ cs_bot_status.get('faq_by_lang', {}).get('ja', 0) }}, ZH {{ cs_bot_status.get('faq_by_lang', {}).get('zh', 0) }})</li>
          <li>24h: 신규 {{ cs_bot_status.new_24h }} / 미응답 {{ cs_bot_status.unanswered }} / 자동발송 {{ cs_bot_status.auto_sent_24h }} / 평균응답 {{ cs_bot_status.avg_response_minutes }}분</li>
          <li>AI 제안 채택률: {{ cs_bot_status.ai_adoption_rate }}% (편집률 {{ cs_bot_status.ai_edit_rate }}%)</li>
          <li>저품질 FAQ: {{ cs_bot_status.low_quality_count }}개 검토 필요</li>
          <li>AI 제안 호출: {{ cs_bot_status.ai_calls_24h }}건 (예산 잔여 {{ cs_bot_status.budget_remaining_pct }}%)</li>
          <li>자동 발송: {% if cs_bot_status.auto_send %}<span class="badge bg-danger">ON</span>{% else %}<span class="badge bg-secondary">OFF</span>{% endif %} ({{ cs_bot_status.get('auto_send_categories', ['general','shipping'])|join('/') }}만, 일일 {{ cs_bot_status.get('auto_send_used_today', 0) }}/{{ cs_bot_status.get('auto_send_daily_limit', 20) }})</li>
          <li>SLA: 임박 {{ cs_bot_status.sla_nearing }}건 / 초과 {{ cs_bot_status.sla_overdue }}건</li>
          <li>임베딩 캐시: {{ cs_bot_status.get('embedding_cached', '0/0') }} ✅</li>
          <li>스케줄러: {% if cs_bot_status.scheduler_running %}<span class="badge bg-success">실행 중</span>{% elif cs_bot_status.scheduler_enabled %}<span class="badge bg-warning text-dark">활성/미실행</span>{% else %}<span class="badge bg-secondary">비활성</span>{% endif %}{% if cs_bot_status.scheduler_next_poll %} · 다음 폴링 {{ cs_bot_status.scheduler_next_poll[:19] }}{% endif %}</li>
        </ul>
        <div class="border rounded p-3 bg-light mb-3">
          <div class="fw-semibold mb-2">⏰ Scheduler (Phase 141)</div>
          <div class="small mb-1">
            상태:
            {% if cs_bot_status.scheduler_running %}
              ✅ Running (잠금 보유 PID {{ cs_bot_status.scheduler_leader_pid }}, hostname {{ cs_bot_status.scheduler_leader_hostname }})
            {% elif cs_bot_status.scheduler_enabled %}
              🟨 Enabled
            {% else %}
              ⬜ Disabled
            {% endif %}
          </div>
          <div class="small mb-1">등록된 잡: {{ cs_bot_status.scheduler_jobs|length }}개</div>
          <ul class="small mb-2">
            {% for job in cs_bot_status.scheduler_jobs %}
              <li>{{ job.id }} — 마지막 {{ job.last_run_at or '-' }} · 다음 {{ job.next_run_time or '-' }} · {{ '✅' if job.last_status == 'ok' else ('⚠️' if job.last_status == 'error' else '⬜') }}</li>
            {% endfor %}
          </ul>
          <div class="small">미실행 잡 24h: {{ cs_bot_status.scheduler_missed_24h }}건</div>
        </div>
        <div class="d-flex gap-2 flex-wrap">
          <a class="btn btn-outline-primary btn-sm" href="/seller/cs/inbox">Inbox 열기</a>
          <a class="btn btn-outline-secondary btn-sm" href="/seller/cs/faq">FAQ 관리</a>
          <a class="btn btn-outline-info btn-sm" href="/seller/cs/mobile">Mobile PWA</a>
          <a class="btn btn-outline-secondary btn-sm" href="/seller/cs/stats">통계</a>
          <a class="btn btn-outline-secondary btn-sm" href="/seller/cs/quality">Quality</a>
          <a class="btn btn-outline-secondary btn-sm" href="/seller/cs/inbox?msg=&channel=&status=&q=">Multi-Send Test</a>
          <button class="btn btn-outline-warning btn-sm"
                  onclick="fetch('/admin/cs/check-sla',{method:'POST'}).then(r=>r.json()).then(d=>alert(JSON.stringify(d,null,2)))">
            SLA 점검 실행
          </button>
          <button class="btn btn-outline-success btn-sm"
                  onclick="fetch('/admin/cs/poll-now',{method:'POST'}).then(r=>r.json()).then(d=>alert(JSON.stringify(d,null,2)))">
            즉시 폴링
          </button>
          <button class="btn btn-outline-secondary btn-sm"
                  onclick="fetch('/admin/cs/rebuild-embeddings',{method:'POST'}).then(r=>r.json()).then(d=>alert(JSON.stringify(d,null,2)))">
            임베딩 재계산
          </button>
        </div>
      </div>
    </div>

    <!-- Phase 142: 섹션 8 — 인증 상태 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">🔐 섹션 8 — 인증 상태 (Phase 142)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>현재 사용자: <strong>{{ auth_status.user_email or auth_status.user_name or '비로그인' }}</strong>
            {% if auth_status.is_admin %}
              <span class="badge bg-success">admin ✅ ({{ auth_status.admin_rule }})</span>
            {% else %}
              <span class="badge bg-secondary">비admin</span>
            {% endif %}
          </li>
          <li>ADMIN_EMAILS: {% if auth_status.admin_emails_configured %}<span class="badge bg-success">✅ 설정됨</span>{% else %}<span class="badge bg-secondary">미설정</span>{% endif %}</li>
          <li>ADMIN_KAKAO_IDS: {% if auth_status.admin_kakao_configured %}<span class="badge bg-success">✅ 설정됨</span>{% else %}<span class="badge bg-secondary">미설정</span>{% endif %}</li>
          <li>ADMIN_GOOGLE_SUBS: {% if auth_status.admin_google_configured %}<span class="badge bg-success">✅ 설정됨</span>{% else %}<span class="badge bg-secondary">미설정</span>{% endif %}</li>
          <li>ADMIN_NAVER_IDS: {% if auth_status.admin_naver_configured %}<span class="badge bg-success">✅ 설정됨</span>{% else %}<span class="badge bg-secondary">미설정</span>{% endif %}</li>
        </ul>
        <h6 class="fw-semibold">OAuth 제공자</h6>
        <ul class="mb-3">
          <li>카카오: {% if auth_status.kakao_oauth_active %}<span class="badge bg-success">✅ 설정됨</span>{% else %}<span class="badge bg-secondary">KAKAO_CLIENT_ID 미설정</span>{% endif %}</li>
          <li>Google:
            {% if auth_status.google_oauth_active %}
              <span class="badge bg-success">✅ 설정됨</span>
              <span class="small text-muted">CLIENT_ID: {{ auth_status.google_client_id_hint }}</span>
            {% else %}
              <span class="badge bg-secondary">GOOGLE_CLIENT_ID 미설정</span>
            {% endif %}
            <span class="ms-2"><a href="/admin/diagnostics/google-oauth-guide" class="small">[진단 가이드 →]</a></span>
          </li>
          <li>네이버: {% if auth_status.naver_oauth_active %}<span class="badge bg-success">✅ 설정됨</span>{% else %}<span class="badge bg-secondary">NAVER_CLIENT_ID 미설정</span>{% endif %}</li>
        </ul>
        <div class="alert alert-info small mb-0">
          <div class="fw-semibold mb-1">Google OAuth "액세스 차단" 진단 체크리스트</div>
          <ol class="mb-0 ps-3">
            <li>Google Cloud Console &gt; APIs &amp; Services &gt; Credentials &gt; OAuth 2.0 Client IDs</li>
            <li>Authorized redirect URIs에 추가: <code>{{ auth_status.google_redirect_uri }}</code>
              <button class="btn btn-sm btn-outline-secondary ms-1 py-0 copy-btn"
                      onclick="navigator.clipboard.writeText('{{ auth_status.google_redirect_uri }}').then(()=>this.textContent='✅')">📋</button>
            </li>
            <li>OAuth consent screen &gt; Testing 모드 → 본인 이메일을 Test users에 추가</li>
            <li>또는 Publishing status를 In production으로 전환 (Google 검증 필요)</li>
          </ol>
          <a href="/docs/operations/GOOGLE_OAUTH_SETUP.md" class="small" target="_blank">📄 전체 가이드 보기</a>
        </div>
      </div>
    </div>

    <!-- Phase 142: 섹션 9 — 자동 리오더 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">📦 섹션 9 — 자동 리오더 (Phase 142)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>활성화: {% if auto_reorder_status.enabled %}<span class="badge bg-success">ON</span>{% else %}<span class="badge bg-secondary">OFF</span>{% endif %}</li>
          <li>자동 발주: {% if auto_reorder_status.auto_place %}<span class="badge bg-danger">AUTO ON</span>{% else %}<span class="badge bg-secondary">OFF (승인 필요)</span>{% endif %}</li>
          <li>일일 예산: ₩{{ "{:,}".format(auto_reorder_status.daily_budget_krw) }}</li>
          <li>안전 재고일: {{ auto_reorder_status.safety_days }}일</li>
          <li>권장 발주: <strong>{{ auto_reorder_status.pending_count }}건</strong>
            {% if auto_reorder_status.estimated_cost_krw > 0 %}
              (예상 ₩{{ "{:,}".format(auto_reorder_status.estimated_cost_krw) }})
            {% endif %}
          </li>
          <li>마지막 점검: {{ auto_reorder_status.last_checked_ago }}</li>
        </ul>
        <a href="/seller/inventory/reorder" class="btn btn-outline-primary btn-sm">📋 발주 목록 보기</a>
      </div>
    </div>

    <!-- Phase 142: 섹션 10 — 할인 캠페인 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">🎟️ 섹션 10 — 할인 캠페인 자동화 (Phase 142)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>활성화: {% if discount_campaign_status.enabled %}<span class="badge bg-success">ON</span>{% else %}<span class="badge bg-secondary">OFF</span>{% endif %}</li>
          <li>최대 할인율: {{ discount_campaign_status.max_pct }}%</li>
          <li>마진 하한선: {{ discount_campaign_status.margin_floor_pct }}%</li>
          <li>재고 과잉 SKU: <strong>{{ discount_campaign_status.overstocked_skus }}종</strong></li>
          <li>추천 캠페인: <strong>{{ discount_campaign_status.recommended_count }}건</strong></li>
          <li>활성 캠페인: <strong>{{ discount_campaign_status.active_count }}건</strong></li>
        </ul>
        <a href="/seller/marketing/campaigns" class="btn btn-outline-primary btn-sm">📣 캠페인 관리</a>
      </div>
    </div>

    <!-- Phase 143: 섹션 11 — 소싱 파이프라인 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">🔎 섹션 11 — 소싱 파이프라인 (Phase 143)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>활성 Watch: <strong>{{ sourcing_pipeline_status.active_watches }}개</strong> (전체 {{ sourcing_pipeline_status.total_watches }}개)</li>
          <li>24h 후보: <strong>{{ sourcing_pipeline_status.candidates_24h }}건</strong>
            / 승인 대기: <span class="badge bg-warning text-dark">{{ sourcing_pipeline_status.pending_approval }}건</span>
            / 자동 등록: <span class="badge bg-primary">{{ sourcing_pipeline_status.auto_listed }}건</span>
          </li>
          <li>평균 마진 예상: <strong>{{ sourcing_pipeline_status.avg_margin_pct }}%</strong>
            (기준: {{ sourcing_pipeline_status.min_margin_pct }}% 이상)
          </li>
          <li>Watch 주기: {{ sourcing_pipeline_status.watch_interval_minutes }}분</li>
          <li>자동 등록:
            {% if sourcing_pipeline_status.auto_publish_enabled %}
              <span class="badge bg-danger">ON</span>
            {% else %}
              <span class="badge bg-secondary">OFF (LISTING_AUTO_PUBLISH=0)</span>
            {% endif %}
          </li>
        </ul>
        <h6 class="fw-semibold">이미지 파이프라인</h6>
        <ul class="mb-3">
          <li>파이프라인:
            {% if sourcing_pipeline_status.image_pipeline_enabled %}
              <span class="badge bg-success">ON</span>
            {% else %}
              <span class="badge bg-secondary">OFF</span>
            {% endif %}
          </li>
          <li>Inpainting (워터마크 제거):
            {% if sourcing_pipeline_status.image_inpaint_enabled %}
              <span class="badge bg-success">ON</span>
            {% else %}
              <span class="badge bg-secondary">OFF</span>
            {% endif %}
          </li>
          <li>처리 성공: {{ sourcing_pipeline_status.get('image_success_pct', 0) }}%</li>
        </ul>
        <h6 class="fw-semibold">번역</h6>
        <ul class="mb-3">
          <li>품질 티어: <strong>{{ sourcing_pipeline_status.translation_quality_tier }}</strong></li>
          <li>DeepL:
            {% if sourcing_pipeline_status.deepl_configured %}
              <span class="badge bg-success">✅ 설정됨</span>
            {% else %}
              <span class="badge bg-secondary">DEEPL_API_KEY 미설정 (stub)</span>
            {% endif %}
          </li>
        </ul>
        <div class="d-flex gap-2 flex-wrap">
          <a class="btn btn-outline-primary btn-sm" href="/seller/sourcing/watches">🔗 Watch 관리</a>
          <a class="btn btn-outline-success btn-sm" href="/seller/sourcing/candidates">📋 후보 큐</a>
          <a class="btn btn-outline-secondary btn-sm" href="/seller/sourcing/candidates?status=listed">📦 등록 이력</a>
        </div>
      </div>
    </div>

    <!-- Phase 144: 섹션 12 — 광고 자동 운영 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">📣 섹션 12 — 광고 자동 운영 (Phase 144)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>자동 운영:
            {% if ads_status.enabled %}
              <span class="badge bg-success">ON</span>
            {% else %}
              <span class="badge bg-secondary">OFF (ADS_AUTO_CAMPAIGN_ENABLED=0)</span>
            {% endif %}
          </li>
          <li>Launch 모드:
            {% if ads_status.auto_launch %}
              <span class="badge bg-danger">자동 launch</span>
            {% else %}
              <span class="badge bg-secondary">수동 승인 (ADS_AUTO_CAMPAIGN_AUTO_LAUNCH=0)</span>
            {% endif %}
          </li>
          <li>일일 예산: <strong>{{ "{:,}".format(ads_status.daily_budget_krw) }}원</strong></li>
          <li>목표 ROAS: <strong>{{ ads_status.target_roas }}</strong></li>
          <li>키워드 최적화 공급자: <code>{{ ads_status.keyword_provider }}</code></li>
        </ul>
        <h6 class="fw-semibold">24h 성과</h6>
        <ul class="mb-3">
          <li>활성 캠페인: <strong>{{ ads_status.active_campaigns }}개</strong>
            {% for ch, cnt in ads_status.by_channel.items() %}
              <span class="badge bg-primary">{{ ch }} {{ cnt }}</span>
            {% endfor %}
          </li>
          <li>광고비: <strong>{{ "{:,}".format(ads_status.cost_krw_24h) }}원</strong>
              / 매출: <strong>{{ "{:,}".format(ads_status.revenue_krw_24h) }}원</strong>
              / ROAS: <strong>{{ ads_status.roas_24h }}</strong></li>
          <li>추천 캠페인 대기: <span class="badge bg-warning text-dark">{{ ads_status.pending_recs }}건</span></li>
        </ul>
        <div class="d-flex gap-2 flex-wrap">
          <a class="btn btn-outline-primary btn-sm" href="/seller/ads/campaigns">🔗 캠페인 관리</a>
          <a class="btn btn-outline-secondary btn-sm" href="/seller/sourcing/watches">🔎 소싱 Watch</a>
        </div>
      </div>
    </div>

    <!-- Phase 144: 섹션 13 — 라우트 점검 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">
        🛣️ 섹션 13 — 라우트 점검 (Phase 144 hotfix)
        {% if route_check_status.ok %}
          <span class="badge bg-success ms-2">정상</span>
        {% else %}
          <span class="badge bg-danger ms-2">{{ route_check_status.missing_count }}개 누락</span>
        {% endif %}
      </div>
      <div class="card-body">
        <p class="mb-2">
          등록된 라우트: <strong>{{ route_check_status.total_routes }}개</strong>
          / 깨진 핵심 라우트: <strong class="{% if route_check_status.missing_count > 0 %}text-danger{% else %}text-success{% endif %}">{{ route_check_status.missing_count }}건</strong>
        </p>
        <div class="table-responsive mb-3">
          <table class="table table-sm table-hover">
            <thead><tr><th>엔드포인트</th><th>URL</th><th>상태</th></tr></thead>
            <tbody>
              {% for r in route_check_status.key_routes %}
              <tr>
                <td><code class="small">{{ r.endpoint }}</code></td>
                <td><a href="{{ r.url }}" target="_blank">{{ r.url }}</a></td>
                <td>
                  {% if r.ok %}
                    <span class="badge bg-success">✅ 등록됨</span>
                  {% else %}
                    <span class="badge bg-danger">❌ 누락</span>
                  {% endif %}
                </td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        <h6 class="fw-semibold">사이드바 링크</h6>
        <div class="d-flex flex-wrap gap-2">
          {% for link in route_check_status.sidebar_links %}
            <a href="{{ link[0] }}" class="btn btn-outline-secondary btn-sm">{{ link[1] }}</a>
          {% endfor %}
        </div>
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-header fw-bold">🛣️ 라우트 매트릭스 (Phase 146)</div>
      <div class="card-body">
        <ul class="mb-0">
          <li>사이드바 링크: {{ sidebar_nav_status.seller_menu_count }} / 라우트 등록: {{ sidebar_nav_status.registered_routes }} {% if sidebar_nav_status.broken_links == 0 %}✅{% endif %}</li>
          <li>깨진 링크: {{ sidebar_nav_status.broken_links }}건{% if sidebar_nav_status.broken_links > 0 %} ({{ sidebar_nav_status.broken_link_urls|join(', ') }}){% endif %}</li>
          <li>글로벌 404 헤더 분기: {% if header_branch_status.error_404 %}✅{% else %}❌{% endif %}</li>
        </ul>
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-header fw-bold">🔐 헤더 로그인 분기 (Phase 146 재확인)</div>
      <div class="card-body">
        <ul class="mb-0">
          <li>셀러 콘솔: {% if header_branch_status.seller_console %}✅{% else %}❌{% endif %}</li>
          <li>admin 콘솔: {% if header_branch_status.admin_console %}✅{% else %}❌{% endif %}</li>
          <li>글로벌 페이지: {% if header_branch_status.global_page %}✅{% else %}❌{% endif %}</li>
          <li>404 페이지: {% if header_branch_status.error_404 %}✅{% else %}❌{% endif %}</li>
        </ul>
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-header fw-bold">🔁 반품/환불 자동화 (Phase 146)</div>
      <div class="card-body">
        <ul class="mb-0">
          <li>24h 반품 요청: {{ returns_automation_status.requests_24h }}건</li>
          <li>자동 승인: {{ returns_automation_status.auto_approved_24h }}건 / 수동 대기: {{ returns_automation_status.manual_queue_24h }}건</li>
          <li>평균 처리 시간: {{ returns_automation_status.avg_minutes }}</li>
        </ul>
      </div>
    </div>

    <div class="card mb-4">
      <div class="card-header fw-bold">💰 정산 리포트</div>
      <div class="card-body">
        <ul>
          <li>이번달 매출(예정): {{ "{:,}".format(settlement_report_status.month_sales_krw) }}원</li>
          <li>채널별 비중: {% if settlement_report_status.channel_share %}{{ settlement_report_status.channel_share }}{% else %}-{% endif %}</li>
          <li>다음 정산일: {{ settlement_report_status.next_settlement_date }}</li>
        </ul>
        <div class="d-flex flex-wrap gap-2">
          <a class="btn btn-outline-secondary btn-sm" href="/admin/diagnostics">🔗 사이드바 매트릭스</a>
          <a class="btn btn-outline-secondary btn-sm" href="/seller/returns/inbox">↩️ 반품</a>
          <a class="btn btn-outline-secondary btn-sm" href="/seller/settlement">💰 정산</a>
          <a class="btn btn-outline-secondary btn-sm" href="/seller/dashboard">🔐 헤더 분기 테스트</a>
        </div>
      </div>
    </div>

    <!-- Phase 147: 섹션 — 모바일/PWA -->
    <div class="card mb-4">
      <div class="card-header fw-bold">📱 모바일/PWA (Phase 147)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>PWA 활성화: {% if pwa_status.pwa_enabled %}<span class="badge bg-success">ON</span>{% else %}<span class="badge bg-secondary">OFF (PWA_ENABLED=0)</span>{% endif %}</li>
          <li>앱 이름: <strong>{{ pwa_status.app_name }}</strong></li>
          <li>viewport 메타: {% if pwa_status.viewport_meta %}✅{% else %}❌{% endif %}</li>
          <li>manifest 링크: {% if pwa_status.manifest_linked %}✅{% else %}❌{% endif %}</li>
          <li>Service Worker: {% if pwa_status.sw_registered %}✅ 등록 스크립트 포함{% else %}❌{% endif %}</li>
        </ul>
        <div class="d-flex gap-2 flex-wrap">
          <a class="btn btn-outline-primary btn-sm" href="/seller/static/manifest.json" target="_blank">📄 PWA 매니페스트</a>
          <a class="btn btn-outline-secondary btn-sm" href="/seller/static/sw.js" target="_blank">⚙️ Service Worker</a>
        </div>
      </div>
    </div>

    <!-- Phase 147: 섹션 — 푸시 알림 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">🔔 푸시 알림 (Phase 147)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>VAPID 키:
            {% if web_push_status.vapid_configured %}
              <span class="badge bg-success">✅ 등록됨</span>
              <span class="small text-muted">({{ web_push_status.vapid_public_hint }})</span>
            {% else %}
              <span class="badge bg-warning text-dark">⚠️ 미설정</span>
              <span class="small text-muted">— WEB_PUSH_VAPID_PUBLIC/PRIVATE 환경변수 설정 필요</span>
            {% endif %}
          </li>
          <li>구독자: <strong>{{ web_push_status.subscriber_count }}</strong>명</li>
        </ul>
        <div class="d-flex gap-2 flex-wrap">
          <a class="btn btn-outline-primary btn-sm" href="/seller/me/notifications">🔔 푸시 구독 페이지</a>
        </div>
      </div>
    </div>

    <!-- Phase 147: 섹션 — 옴니채널 재고 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">📦 옴니채널 재고 동기화 (Phase 147)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>활성화: {% if omni_sync_status.enabled %}<span class="badge bg-success">ON</span>{% else %}<span class="badge bg-secondary">OFF (INVENTORY_OMNI_SYNC_ENABLED=0)</span>{% endif %}</li>
          <li>모드: <code>{{ omni_sync_status.mode }}</code></li>
          <li>연동 채널: <strong>{{ omni_sync_status.channel_count }}</strong>개
            {% if omni_sync_status.configured_channels %}
              ({{ omni_sync_status.configured_channels | join(', ') }})
            {% else %}
              <span class="text-muted small">— 쿠팡/스마트스토어 API 설정 시 표시</span>
            {% endif %}
          </li>
          <li>동기화 주기: {{ omni_sync_status.sync_interval_sec }}초</li>
          <li>24h 실패/지연:
            <span class="{% if omni_sync_status.failure_24h > 0 %}text-danger fw-bold{% endif %}">{{ omni_sync_status.failure_24h }}건</span>
          </li>
        </ul>
        <div class="d-flex gap-2 flex-wrap">
          <a class="btn btn-outline-primary btn-sm" href="/seller/inventory/omni">📦 옴니 재고 관리</a>
        </div>
      </div>
    </div>

    <!-- Phase 147: 섹션 — 큐/락 (멀티워커) -->
    <div class="card mb-4">
      <div class="card-header fw-bold">⚙️ 큐/락 멀티워커 (Phase 147)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>백엔드: <code>{{ job_queue_status.backend }}</code></li>
          <li>활성 워커: <strong>{{ job_queue_status.worker_distribution | length }}</strong>개</li>
          <li>큐 대기: <strong>{{ job_queue_status.queued }}</strong>건 / 실행 중: <strong>{{ job_queue_status.running }}</strong>건</li>
          <li>데드레터: <span class="{% if job_queue_status.dead_letters > 0 %}text-danger fw-bold{% endif %}">{{ job_queue_status.dead_letters }}건</span></li>
          <li>최대 재시도: {{ job_queue_status.max_retries }}회</li>
          {% if job_queue_status.by_category %}
            <li>카테고리별:
              {% for cat, cnt in job_queue_status.by_category.items() %}
                <span class="badge bg-secondary">{{ cat }} {{ cnt }}</span>
              {% endfor %}
            </li>
          {% endif %}
        </ul>
        <div class="d-flex gap-2 flex-wrap">
          <a class="btn btn-outline-primary btn-sm" href="/admin/jobs">⚙️ 잡 큐 관리</a>
        </div>
      </div>
    </div>

    <!-- Phase 148: 섹션 — 버전 표시 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">🏷️ 버전 표시 (Phase 148)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>현재 Phase:
            <strong>{{ version_display_status.current_phase }}</strong>
            {% if version_display_status.ok %}<span class="badge bg-success ms-1">✅ 자동화</span>{% else %}<span class="badge bg-danger ms-1">❌ 오류</span>{% endif %}
          </li>
          <li>앱 버전: <code>{{ version_display_status.app_version }}</code></li>
          <li>src/version.py CURRENT_PHASE: <code>{{ version_display_status.hardcoded_phase }}</code></li>
        </ul>
        <div class="d-flex gap-2 flex-wrap">
          <a class="btn btn-outline-secondary btn-sm" href="/">🔗 랜딩 푸터 확인</a>
        </div>
      </div>
    </div>

    <!-- Phase 148: 섹션 — 푸시 알림 재확인 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">🔔 푸시 알림 (Phase 148 재확인)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>/seller/me/notifications 라우트:
            {% if web_push_status.route_ok is not defined or web_push_status.route_ok is none %}
              <span class="badge bg-success">✅ 등록됨</span>
            {% elif web_push_status.route_ok %}
              <span class="badge bg-success">✅ 등록됨</span>
            {% else %}
              <span class="badge bg-danger">❌ 미등록</span>
            {% endif %}
          </li>
          <li>VAPID 등록:
            {% if web_push_status.vapid_configured %}
              <span class="badge bg-success">✅ 설정됨</span>
              <span class="small text-muted">({{ web_push_status.vapid_public_hint }})</span>
            {% else %}
              <span class="badge bg-warning text-dark">⚠️ 미설정</span>
            {% endif %}
          </li>
          <li>구독자: <strong>{{ web_push_status.subscriber_count }}</strong>명</li>
        </ul>
        <div class="d-flex gap-2 flex-wrap">
          <a class="btn btn-outline-primary btn-sm" href="/seller/me/notifications">🔔 푸시 구독 페이지</a>
          {% if not web_push_status.vapid_configured %}
          <form method="post" action="/admin/diagnostics/vapid-generate" class="d-inline">
            <button type="submit" class="btn btn-outline-warning btn-sm">🔑 VAPID 키 자동 생성</button>
          </form>
          {% else %}
          <form method="post" action="/admin/diagnostics/vapid-generate" class="d-inline">
            <button type="submit" class="btn btn-outline-secondary btn-sm">🔄 VAPID 키 재생성 (경고: 모든 사용자 재구독 필요)</button>
          </form>
          {% endif %}
        </div>
      </div>
    </div>

    <!-- Phase 148: 섹션 — B2B 도매 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">🏢 B2B 도매 (Phase 148)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>도매 기능: {% if wholesale_status.enabled %}<span class="badge bg-success">ON</span>{% else %}<span class="badge bg-secondary">OFF (WHOLESALE_ENABLED=0)</span>{% endif %}</li>
          <li>등급 수: <strong>{{ wholesale_status.tier_count }}</strong>개</li>
          <li>도매 회원: <strong>{{ wholesale_status.approved_members }}</strong>명 / 신청 대기: <strong>{{ wholesale_status.pending_applications }}</strong>건</li>
          <li>전체 신청: {{ wholesale_status.total_applications }}건</li>
        </ul>
        <div class="d-flex gap-2 flex-wrap">
          <a class="btn btn-outline-primary btn-sm" href="/seller/wholesale/tiers">🏢 도매 등급 관리</a>
          <a class="btn btn-outline-secondary btn-sm" href="/seller/wholesale/applications">📋 B2B 신청 큐</a>
        </div>
      </div>
    </div>

    <!-- Phase 148: 섹션 — 정기구독 상품 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">🔁 정기구독 (Phase 148)</div>
      <div class="card-body">
        <ul class="mb-3">
          <li>구독 기능: {% if product_subscription_status.enabled %}<span class="badge bg-success">ON</span>{% else %}<span class="badge bg-secondary">OFF (SUBSCRIPTION_ENABLED=0)</span>{% endif %}</li>
          <li>PG 제공사: <code>{{ product_subscription_status.pg_provider }}</code></li>
          <li>활성 구독: <strong>{{ product_subscription_status.active_count }}</strong>건</li>
          <li>이번주 결제: <strong>{{ product_subscription_status.billed_this_week }}</strong>건 / 실패: <span class="{% if product_subscription_status.failed_count > 0 %}text-danger fw-bold{% endif %}">{{ product_subscription_status.failed_count }}건</span></li>
          <li>해지(누적): {{ product_subscription_status.cancelled_count }}건</li>
        </ul>
        <div class="d-flex gap-2 flex-wrap">
          <a class="btn btn-outline-primary btn-sm" href="/seller/subscriptions">🔁 구독 관리</a>
          <a class="btn btn-outline-secondary btn-sm" href="/seller/me/subscriptions">👤 내 구독</a>
        </div>
      </div>
    </div>

  </main>
</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
