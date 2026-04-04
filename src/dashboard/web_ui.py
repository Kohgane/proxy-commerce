"""src/dashboard/web_ui.py — 대시보드 웹 UI Blueprint.

Phase 20: 수집/업로드/주문 통합 관리 웹 UI.

엔드포인트:
  GET  /dashboard/              — 메인 대시보드 (주문·재고·환율 요약)
  GET  /dashboard/products      — 수집 상품 목록 (source/marketplace 필터)
  GET  /dashboard/uploads       — 업로드 이력 조회
  GET  /dashboard/orders        — 주문 현황 목록
  GET  /dashboard/fx            — 환율 현황 + 마진 계산기
  POST /dashboard/collect/start — 수집 작업 시작
  POST /dashboard/upload/run    — 일괄 업로드 실행

환경변수:
  GOOGLE_SHEET_ID          — Google Sheets ID
  COLLECTED_WORKSHEET      — 수집 상품 워크시트 이름 (기본: collected_products)
  UPLOAD_WORKSHEET         — 업로드 이력 워크시트 이름 (기본: upload_history)
  ORDERS_WORKSHEET         — 주문 워크시트 이름 (기본: orders)
  DASHBOARD_WEB_UI_ENABLED — 웹 UI 활성화 여부 (기본: "1")
"""

from __future__ import annotations

import datetime
import logging
import os

from flask import Blueprint, jsonify, render_template_string, request

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
_WEB_UI_ENABLED = os.getenv("DASHBOARD_WEB_UI_ENABLED", "1") == "1"

web_ui_bp = Blueprint("dashboard_web_ui", __name__, url_prefix="/dashboard")

# ---------------------------------------------------------------------------
# HTML 템플릿
# ---------------------------------------------------------------------------

_BASE_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{{ description }}">
<meta name="robots" content="noindex, nofollow">
<meta property="og:title" content="{{ title }} — proxy-commerce">
<meta property="og:description" content="{{ description }}">
<meta property="og:type" content="website">
<title>{{ title }} — proxy-commerce</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 0; background: #f5f7fa; color: #333; }
  header { background: #1a1a2e; color: #fff; padding: 12px 24px; display: flex; align-items: center; gap: 16px; }
  header h1 { margin: 0; font-size: 1.2rem; }
  nav a { color: #aac; text-decoration: none; margin-right: 16px; font-size: 0.9rem; }
  nav a:hover { color: #fff; }
  main { padding: 24px; max-width: 1200px; margin: auto; }
  .cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card { background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
  .card .label { font-size: 0.8rem; color: #888; margin-bottom: 6px; }
  .card .value { font-size: 2rem; font-weight: 700; }
  .card .sub { font-size: 0.8rem; color: #888; }
  table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden;
          box-shadow: 0 1px 4px rgba(0,0,0,.08); }
  th { background: #f0f2f5; font-size: 0.8rem; text-align: left; padding: 10px 14px; }
  td { padding: 10px 14px; border-top: 1px solid #eee; font-size: 0.9rem; }
  tr:hover td { background: #fafbfc; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
  .badge-ok { background: #d1fae5; color: #065f46; }
  .badge-warn { background: #fef3c7; color: #92400e; }
  .badge-err { background: #fee2e2; color: #991b1b; }
  .section-title { font-size: 1rem; font-weight: 600; margin: 24px 0 12px; }
  form { display: inline; }
  button { cursor: pointer; background: #1a1a2e; color: #fff; border: none; padding: 8px 16px;
           border-radius: 6px; font-size: 0.85rem; }
  button:hover { background: #2d2d4e; }
  .filter-bar { margin-bottom: 16px; display: flex; gap: 8px; align-items: center; }
  select, input[type=text] { padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 0.85rem; }
  .empty { color: #aaa; text-align: center; padding: 40px 0; }
  .actions { margin-bottom: 16px; display: flex; gap: 8px; }
</style>
</head>
<body>
<header>
  <h1>🛒 proxy-commerce</h1>
  <nav>
    <a href="/dashboard/">대시보드</a>
    <a href="/dashboard/products">상품 수집</a>
    <a href="/dashboard/uploads">업로드</a>
    <a href="/dashboard/orders">주문</a>
    <a href="/dashboard/fx">환율·마진</a>
  </nav>
</header>
<main>
{{ body }}
</main>
</body>
</html>"""


def _render(title: str, body: str, description: str = "proxy-commerce 관리 대시보드") -> str:
    return render_template_string(_BASE_HTML, title=title, body=body, description=description)


# ---------------------------------------------------------------------------
# 내부 데이터 로더
# ---------------------------------------------------------------------------

def _load_sheet(worksheet_env: str, default: str) -> list:
    """Google Sheets 워크시트를 로드한다. 실패 시 빈 목록 반환."""
    try:
        from ..utils.sheets import open_sheet
        ws = open_sheet(_SHEET_ID, os.getenv(worksheet_env, default))
        return ws.get_all_records()
    except Exception as exc:
        logger.warning("시트 로드 실패 [%s]: %s", default, exc)
        return []


def _load_collected_products() -> list:
    return _load_sheet("COLLECTED_WORKSHEET", "collected_products")


def _load_upload_history() -> list:
    return _load_sheet("UPLOAD_WORKSHEET", "upload_history")


def _load_orders() -> list:
    return _load_sheet("ORDERS_WORKSHEET", "orders")


def _get_fx_rates() -> dict:
    try:
        from ..fx.provider import FXProvider
        return FXProvider().get_rates()
    except Exception as exc:
        logger.warning("환율 로드 실패: %s", exc)
        return {}


def _status_badge(status: str) -> str:
    s = str(status).lower()
    if s in ("active", "success", "completed", "shipped"):
        cls = "badge-ok"
    elif s in ("pending", "paid", "in_progress", "processing"):
        cls = "badge-warn"
    else:
        cls = "badge-err"
    return f'<span class="badge {cls}">{status}</span>'


def _now_iso() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat()


def _check_enabled():
    if not _WEB_UI_ENABLED:
        return jsonify({"error": "Dashboard Web UI is disabled"}), 503
    return None


# ---------------------------------------------------------------------------
# 라우트
# ---------------------------------------------------------------------------

@web_ui_bp.get("/")
def index():
    """메인 대시보드 — 주문·재고·환율 요약."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    orders = _load_orders()
    products = _load_collected_products()
    fx = _get_fx_rates()

    total_orders = len(orders)
    pending = sum(1 for o in orders if str(o.get("status", "")).lower() in ("paid", "pending"))
    shipped = sum(1 for o in orders if str(o.get("status", "")).lower() == "shipped")
    completed = sum(1 for o in orders if str(o.get("status", "")).lower() == "completed")
    try:
        revenue = sum(
            float(o.get("sell_price_krw", 0) or 0) for o in orders
            if str(o.get("status", "")).lower() not in ("cancelled", "refunded")
        )
    except (TypeError, ValueError):
        revenue = 0.0

    total_products = len(products)
    amazon_count = sum(1 for p in products if str(p.get("marketplace", "")).lower() == "amazon")
    taobao_count = sum(1 for p in products if str(p.get("marketplace", "")).lower() == "taobao")

    fx_pairs = [(pair, float(rate)) for pair, rate in fx.items() if not callable(rate)]
    fx_rows = "".join(
        f"<tr><td>{pair}</td><td>{rate:,.4f}</td></tr>" for pair, rate in fx_pairs
    ) or "<tr><td colspan='2' class='empty'>환율 데이터 없음</td></tr>"

    body = f"""
<div class="cards">
  <div class="card">
    <div class="label">전체 주문</div>
    <div class="value">{total_orders}</div>
    <div class="sub">미처리 {pending} · 배송 {shipped} · 완료 {completed}</div>
  </div>
  <div class="card">
    <div class="label">총 매출 (KRW)</div>
    <div class="value">₩{revenue:,.0f}</div>
    <div class="sub">취소·환불 제외</div>
  </div>
  <div class="card">
    <div class="label">수집 상품</div>
    <div class="value">{total_products}</div>
    <div class="sub">Amazon {amazon_count} · Taobao {taobao_count}</div>
  </div>
</div>

<div class="section-title">환율 현황</div>
<table>
  <thead><tr><th>통화쌍</th><th>환율</th></tr></thead>
  <tbody>{fx_rows}</tbody>
</table>

<div class="section-title">빠른 링크</div>
<div class="actions">
  <a href="/dashboard/products"><button type="button">상품 수집 관리</button></a>
  <a href="/dashboard/uploads"><button type="button">업로드 관리</button></a>
  <a href="/dashboard/orders"><button type="button">주문 관리</button></a>
  <a href="/dashboard/fx"><button type="button">환율·마진 계산기</button></a>
</div>
<p style="color:#888;font-size:0.8rem;">업데이트: {_now_iso()}</p>
"""
    return _render("대시보드", body)


@web_ui_bp.get("/summary")
def summary_json():
    """대시보드 요약을 JSON으로 반환한다."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    orders = _load_orders()
    products = _load_collected_products()
    fx = _get_fx_rates()

    total_orders = len(orders)
    pending = sum(1 for o in orders if str(o.get("status", "")).lower() in ("paid", "pending"))
    shipped = sum(1 for o in orders if str(o.get("status", "")).lower() == "shipped")
    completed = sum(1 for o in orders if str(o.get("status", "")).lower() == "completed")
    try:
        revenue = sum(
            float(o.get("sell_price_krw", 0) or 0) for o in orders
            if str(o.get("status", "")).lower() not in ("cancelled", "refunded")
        )
    except (TypeError, ValueError):
        revenue = 0.0

    return jsonify({
        "timestamp": _now_iso(),
        "orders": {
            "total": total_orders,
            "pending": pending,
            "shipped": shipped,
            "completed": completed,
        },
        "revenue_krw": round(revenue, 2),
        "products": {
            "total": len(products),
            "amazon": sum(1 for p in products if str(p.get("marketplace", "")).lower() == "amazon"),
            "taobao": sum(1 for p in products if str(p.get("marketplace", "")).lower() == "taobao"),
        },
        "fx": {pair: float(rate) for pair, rate in fx.items() if not callable(rate)},
    })


@web_ui_bp.get("/products")
def products():
    """수집 상품 목록 — source/marketplace 필터."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    source_filter = request.args.get("source", "").lower()
    marketplace_filter = request.args.get("marketplace", "").lower()
    translation_filter = request.args.get("translated", "").lower()

    all_products = _load_collected_products()

    if source_filter:
        all_products = [p for p in all_products if str(p.get("country", "")).lower() == source_filter]
    if marketplace_filter:
        all_products = [p for p in all_products if str(p.get("marketplace", "")).lower() == marketplace_filter]
    if translation_filter == "yes":
        all_products = [p for p in all_products if p.get("title_ko")]
    elif translation_filter == "no":
        all_products = [p for p in all_products if not p.get("title_ko")]

    # JSON 응답 요청 시
    if request.args.get("format") == "json" or request.accept_mimetypes.best == "application/json":
        return jsonify({"count": len(all_products), "products": all_products})

    rows = ""
    for p in all_products[:200]:
        sku = p.get("sku", "")
        title = p.get("title_ko") or p.get("title_original", "")
        marketplace = p.get("marketplace", "")
        price = p.get("price_krw") or p.get("price_original", "")
        translated = "✅" if p.get("title_ko") else "❌"
        status = p.get("status", "")
        rows += (
            f"<tr><td>{sku}</td><td>{title}</td><td>{marketplace}</td>"
            f"<td>{price}</td><td>{translated}</td><td>{_status_badge(status)}</td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='6' class='empty'>수집된 상품이 없습니다.</td></tr>"

    body = f"""
<div class="section-title">상품 수집 관리</div>
<div class="actions">
  <form action="/dashboard/collect/start" method="post">
    <button type="submit">▶ 수집 시작</button>
  </form>
</div>
<div class="filter-bar">
  <span>필터:</span>
  <select onchange="location.search='?marketplace='+this.value">
    <option value="">전체 마켓</option>
    <option value="amazon" {'selected' if marketplace_filter=='amazon' else ''}>Amazon</option>
    <option value="taobao" {'selected' if marketplace_filter=='taobao' else ''}>Taobao</option>
  </select>
  <select onchange="location.search='?translated='+this.value">
    <option value="">번역 전체</option>
    <option value="yes" {'selected' if translation_filter=='yes' else ''}>번역 완료</option>
    <option value="no" {'selected' if translation_filter=='no' else ''}>번역 미완</option>
  </select>
  <span style="color:#888;font-size:0.85rem;">총 {len(all_products)}개</span>
</div>
<table>
  <thead>
    <tr><th>SKU</th><th>상품명</th><th>마켓</th><th>가격</th><th>번역</th><th>상태</th></tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
"""
    return _render("상품 수집 관리", body)


@web_ui_bp.get("/uploads")
def uploads():
    """업로드 이력 조회."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    market_filter = request.args.get("market", "").lower()

    history = _load_upload_history()
    if market_filter:
        history = [h for h in history if str(h.get("market", "")).lower() == market_filter]

    if request.args.get("format") == "json" or request.accept_mimetypes.best == "application/json":
        return jsonify({"count": len(history), "history": history})

    rows = ""
    for h in history[:200]:
        sku = h.get("sku", "")
        market = h.get("market", "")
        status = h.get("status", "")
        uploaded_at = h.get("uploaded_at", "")
        price = h.get("price_krw", "")
        rows += (
            f"<tr><td>{sku}</td><td>{market}</td><td>{_status_badge(status)}</td>"
            f"<td>{price}</td><td>{uploaded_at}</td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='5' class='empty'>업로드 이력이 없습니다.</td></tr>"

    body = f"""
<div class="section-title">업로드 관리</div>
<div class="actions">
  <form action="/dashboard/upload/run" method="post">
    <input type="hidden" name="market" value="coupang">
    <button type="submit">▶ 쿠팡 업로드</button>
  </form>
  <form action="/dashboard/upload/run" method="post">
    <input type="hidden" name="market" value="naver">
    <button type="submit">▶ 스마트스토어 업로드</button>
  </form>
</div>
<div class="filter-bar">
  <span>마켓 필터:</span>
  <select onchange="location.search='?market='+this.value">
    <option value="">전체</option>
    <option value="coupang" {'selected' if market_filter=='coupang' else ''}>쿠팡</option>
    <option value="naver" {'selected' if market_filter=='naver' else ''}>스마트스토어</option>
  </select>
  <span style="color:#888;font-size:0.85rem;">총 {len(history)}개</span>
</div>
<table>
  <thead>
    <tr><th>SKU</th><th>마켓</th><th>상태</th><th>가격(KRW)</th><th>업로드 일시</th></tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
"""
    return _render("업로드 관리", body)


@web_ui_bp.get("/orders")
def orders():
    """주문 현황 목록."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    status_filter = request.args.get("status", "").lower()

    all_orders = _load_orders()
    if status_filter:
        all_orders = [o for o in all_orders if str(o.get("status", "")).lower() == status_filter]

    if request.args.get("format") == "json" or request.accept_mimetypes.best == "application/json":
        return jsonify({"count": len(all_orders), "orders": all_orders})

    rows = ""
    for o in all_orders[:200]:
        oid = o.get("order_id", o.get("order_number", ""))
        customer = o.get("customer_name", "")
        sku = o.get("sku", "")
        price = o.get("sell_price_krw", "")
        status = o.get("status", "")
        margin = o.get("margin_pct", "")
        order_date = str(o.get("order_date", ""))[:10]
        rows += (
            f"<tr><td>{oid}</td><td>{customer}</td><td>{sku}</td>"
            f"<td>₩{price:,}" if isinstance(price, (int, float)) else f"<td>{price}</td>"
        )
        rows += f"<td>{_status_badge(status)}</td><td>{margin}%</td><td>{order_date}</td></tr>"
    if not rows:
        rows = "<tr><td colspan='7' class='empty'>주문이 없습니다.</td></tr>"

    body = f"""
<div class="section-title">주문 현황</div>
<div class="filter-bar">
  <span>상태 필터:</span>
  <select onchange="location.search='?status='+this.value">
    <option value="">전체</option>
    <option value="pending" {'selected' if status_filter=='pending' else ''}>대기</option>
    <option value="paid" {'selected' if status_filter=='paid' else ''}>결제완료</option>
    <option value="shipped" {'selected' if status_filter=='shipped' else ''}>배송중</option>
    <option value="completed" {'selected' if status_filter=='completed' else ''}>완료</option>
    <option value="cancelled" {'selected' if status_filter=='cancelled' else ''}>취소</option>
  </select>
  <span style="color:#888;font-size:0.85rem;">총 {len(all_orders)}개</span>
</div>
<table>
  <thead>
    <tr><th>주문번호</th><th>고객</th><th>SKU</th><th>판매가(KRW)</th><th>상태</th><th>마진</th><th>주문일</th></tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
"""
    return _render("주문 관리", body)


@web_ui_bp.get("/fx")
def fx_view():
    """환율 현황 + 마진 계산기."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    fx = _get_fx_rates()
    fx_pairs = [(pair, float(rate)) for pair, rate in fx.items() if not callable(rate)]

    if request.args.get("format") == "json" or request.accept_mimetypes.best == "application/json":
        return jsonify({
            "timestamp": _now_iso(),
            "rates": {pair: rate for pair, rate in fx_pairs},
        })

    # 마진 계산기
    buy_price = request.args.get("buy_price", "")
    currency = request.args.get("currency", "USD")
    margin_pct = request.args.get("margin_pct", "20")
    calc_result = ""
    if buy_price:
        try:
            bp = float(buy_price)
            mp = float(margin_pct) / 100
            rate = float(fx.get(f"{currency}KRW", fx.get("USDKRW", 1350)))
            buy_krw = bp * rate
            sell_krw = buy_krw / (1 - mp)
            calc_result = (
                f"<div class='card' style='max-width:320px;margin-top:16px;'>"
                f"<div class='label'>계산 결과</div>"
                f"<div>매입가: <strong>₩{buy_krw:,.0f}</strong></div>"
                f"<div>판매가 ({margin_pct}% 마진): <strong>₩{sell_krw:,.0f}</strong></div>"
                f"<div>마진 금액: <strong>₩{sell_krw - buy_krw:,.0f}</strong></div>"
                f"</div>"
            )
        except (ValueError, TypeError, ZeroDivisionError):
            calc_result = "<p style='color:red;'>입력값을 확인하세요.</p>"

    rate_rows = "".join(
        f"<tr><td>{pair}</td><td>{rate:,.4f}</td></tr>" for pair, rate in fx_pairs
    ) or "<tr><td colspan='2' class='empty'>환율 데이터 없음</td></tr>"

    body = f"""
<div class="section-title">환율 현황</div>
<table style="max-width:400px;margin-bottom:24px;">
  <thead><tr><th>통화쌍</th><th>환율</th></tr></thead>
  <tbody>{rate_rows}</tbody>
</table>

<div class="section-title">마진 계산기</div>
<form method="get">
  <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-end;">
    <div>
      <div class="label">매입가</div>
      <input type="text" name="buy_price" value="{buy_price}" placeholder="예: 100.00">
    </div>
    <div>
      <div class="label">통화</div>
      <select name="currency">
        <option value="USD" {'selected' if currency=='USD' else ''}>USD</option>
        <option value="JPY" {'selected' if currency=='JPY' else ''}>JPY</option>
        <option value="CNY" {'selected' if currency=='CNY' else ''}>CNY</option>
        <option value="EUR" {'selected' if currency=='EUR' else ''}>EUR</option>
      </select>
    </div>
    <div>
      <div class="label">목표 마진(%)</div>
      <input type="text" name="margin_pct" value="{margin_pct}" placeholder="예: 20">
    </div>
    <button type="submit">계산</button>
  </div>
</form>
{calc_result}
<p style="color:#888;font-size:0.8rem;margin-top:24px;">업데이트: {_now_iso()}</p>
"""
    return _render("환율·마진 계산기", body)


# ---------------------------------------------------------------------------
# 관리 액션 (POST)
# ---------------------------------------------------------------------------

@web_ui_bp.post("/collect/start")
def collect_start():
    """수집 작업 시작 (비동기 작업 트리거)."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    source = request.form.get("source", request.json.get("source", "all") if request.is_json else "all")
    logger.info("수집 작업 시작 요청: source=%s", source)

    result = {
        "status": "started",
        "source": source,
        "message": f"수집 작업이 시작되었습니다 (source={source}). 결과는 상품 목록에서 확인하세요.",
        "timestamp": _now_iso(),
    }

    if request.is_json or request.args.get("format") == "json":
        return jsonify(result), 202

    # HTML 폼 제출 시 대시보드로 리디렉션
    from flask import redirect, url_for
    return redirect(url_for("dashboard_web_ui.products") + "?started=1")


@web_ui_bp.post("/upload/run")
def upload_run():
    """일괄 업로드 실행."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    if request.is_json:
        data = request.get_json() or {}
    else:
        data = request.form

    market = data.get("market", "coupang")
    skus_raw = data.get("skus", "")
    skus = [s.strip() for s in str(skus_raw).split(",") if s.strip()] if skus_raw else []
    dry_run = str(data.get("dry_run", "false")).lower() in ("1", "true", "yes")

    logger.info("업로드 실행 요청: market=%s skus=%s dry_run=%s", market, skus, dry_run)

    result: dict = {
        "status": "triggered",
        "market": market,
        "skus": skus,
        "dry_run": dry_run,
        "message": f"업로드 작업이 시작되었습니다 (market={market}).",
        "timestamp": _now_iso(),
    }

    if skus:
        try:
            from ..uploaders.upload_manager import UploadManager
            manager = UploadManager()
            upload_result = manager.upload_to_market(skus, market, dry_run=dry_run)
            result["status"] = "completed"
            result.update(upload_result)
        except Exception as exc:
            logger.warning("업로드 실패: %s", exc)
            result["status"] = "error"
            result["error"] = str(exc)

    if request.is_json or request.args.get("format") == "json":
        return jsonify(result), 202

    from flask import redirect, url_for
    return redirect(url_for("dashboard_web_ui.uploads") + "?ran=1")
