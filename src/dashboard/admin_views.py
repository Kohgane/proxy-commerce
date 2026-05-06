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


# ---------------------------------------------------------------------------
# Phase 136: /admin/diagnostics — 운영 진단 대시보드
# ---------------------------------------------------------------------------

@admin_panel_bp.route("/diagnostics")
def admin_diagnostics():
    """운영 진단 대시보드 (Phase 136).

    admin 역할 필수.
    """
    from flask import session, jsonify as _jsonify

    # require_role("admin") 패턴 (auth Blueprint 데코레이터 사용 불가이므로 직접 구현)
    user_role = session.get("user_role")
    if not session.get("user_id"):
        from flask import redirect, url_for
        return redirect("/auth/login?next=/admin/diagnostics")
    if user_role != "admin":
        return _render("접근 거부", "<div class='alert alert-danger'>관리자 권한이 필요합니다.</div>"), 403

    # 섹션 1: 환경변수 매트릭스
    env_matrix = _build_env_matrix()

    # 섹션 2: OAuth 콜백 URL
    base_url = _get_base_url()
    oauth_urls = {
        "Google": f"{base_url}/auth/google/callback",
        "Kakao": f"{base_url}/auth/kakao/callback",
        "Naver": f"{base_url}/auth/naver/callback",
    }

    # 섹션 3: 메신저 채널 health
    messenger_health = _build_messenger_health()

    # 섹션 4: 마켓 어댑터 health
    market_health = _build_market_health()

    # 섹션 5: 가격 엔진 상태
    pricing_status = _build_pricing_status()

    # 섹션 6: 최근 24시간 알림 로그
    message_log = _build_message_log()

    from flask import render_template_string
    from markupsafe import Markup

    return render_template_string(
        _DIAGNOSTICS_TEMPLATE,
        env_matrix=env_matrix,
        oauth_urls=oauth_urls,
        messenger_health=messenger_health,
        market_health=market_health,
        pricing_status=pricing_status,
        message_log=message_log,
        base_url=base_url,
    )


@admin_panel_bp.post("/diagnostics/test-telegram")
def diagnostics_test_telegram():
    """텔레그램 테스트 메시지 발송 (Phase 136)."""
    try:
        from src.notifications.telegram import send_telegram
        ok = send_telegram("🔔 /admin/diagnostics 테스트 메시지입니다.", urgency="info")
        return {"ok": ok, "message": "전송 성공" if ok else "전송 실패 (로그 확인)"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500


@admin_panel_bp.get("/diagnostics/telegram-health")
def diagnostics_telegram_health():
    """텔레그램 health_check JSON (Phase 136)."""
    from src.notifications.telegram import health_check
    from flask import jsonify
    return jsonify(health_check())


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
            result.append({
                "name": api.name,
                "purpose": api.purpose,
                "category": api.category.value if hasattr(api.category, "value") else str(api.category),
                "status": api.status,
                "env_vars": api.env_vars,
                "docs_url": api.docs_url if hasattr(api, "docs_url") else "",
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
    """가격 엔진 상태."""
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

    return {
        "active_rules": active_count,
        "dry_run": os.getenv("PRICING_DRY_RUN", "1") == "1",
        "cron_hour": os.getenv("PRICING_CRON_HOUR", "3"),
        "last_run_at": last_run,
        "min_margin_pct": os.getenv("PRICING_MIN_MARGIN_PCT", "15"),
        "fx_trigger_pct": os.getenv("PRICING_FX_TRIGGER_PCT", "3"),
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
<div class="container-fluid">
<div class="row">
  <nav class="col-md-2 sidebar p-3">
    <h5 class="text-white mb-3">🛒 Admin</h5>
    <ul class="nav flex-column">
      <li><a class="nav-link" href="/admin/">대시보드</a></li>
      <li><a class="nav-link text-white fw-bold" href="/admin/diagnostics">🔍 진단</a></li>
      <li><a class="nav-link" href="/seller/">← 셀러 콘솔</a></li>
    </ul>
  </nav>
  <main class="col-md-10 p-4">
    <h4 class="mb-4">🔍 운영 진단 대시보드</h4>

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

    <!-- 섹션 2: OAuth 콜백 URL -->
    <div class="card mb-4">
      <div class="card-header fw-bold">🔑 섹션 2 — OAuth 콜백 URL</div>
      <div class="card-body">
        <p class="text-muted small mb-3">각 개발자 콘솔에 아래 URL을 정확히 등록하세요.</p>
        <table class="table table-sm">
          <thead><tr><th>프로바이더</th><th>콜백 URL</th><th></th></tr></thead>
          <tbody>
          {% for provider, url in oauth_urls.items() %}
            <tr>
              <td>{{ provider }}</td>
              <td><code id="cb-{{ loop.index }}">{{ url }}</code></td>
              <td>
                <button class="btn btn-outline-secondary btn-sm copy-btn"
                        onclick="navigator.clipboard.writeText('{{ url }}').then(()=>this.textContent='✅')">
                  📋 복사
                </button>
              </td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
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

    <!-- 섹션 5: 가격 엔진 상태 -->
    <div class="card mb-4">
      <div class="card-header fw-bold">💰 섹션 5 — 가격 엔진 상태</div>
      <div class="card-body">
        <div class="row g-3">
          <div class="col-md-2">
            <div class="text-muted small">활성 룰</div>
            <div class="fs-4 fw-bold">{{ pricing_status.active_rules }}</div>
          </div>
          <div class="col-md-3">
            <div class="text-muted small">DRY_RUN 모드</div>
            <div class="fs-5">
              {% if pricing_status.dry_run %}
                <span class="badge bg-info">🔵 시뮬레이션 전용</span>
              {% else %}
                <span class="badge bg-success">🟢 실제 적용</span>
              {% endif %}
            </div>
          </div>
          <div class="col-md-3">
            <div class="text-muted small">마지막 실행</div>
            <div class="small">{{ pricing_status.last_run_at or '없음' }}</div>
          </div>
          <div class="col-md-2">
            <div class="text-muted small">Cron 시각 (KST)</div>
            <div>{{ pricing_status.cron_hour }}시</div>
          </div>
          <div class="col-md-2">
            <a href="/seller/pricing/rules" class="btn btn-outline-primary btn-sm">룰 관리 →</a>
          </div>
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

  </main>
</div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
