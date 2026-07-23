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
<meta property="og:site_name" content="{{ brand_name }}">
<meta property="og:title" content="{{ brand_name }}">
<meta property="og:description" content="{{ description }}">
<meta property="og:type" content="website">
<title>{{ title }} | {{ brand_name }}</title>
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
  <h1>🛒 고가브릿지</h1>
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


def _render(title: str, body: str, description: str = "고가브릿지 관리 대시보드") -> str:
    from src.utils.branding import get_brand_name

    return render_template_string(
        _BASE_HTML,
        title=title,
        body=body,
        description=description,
        brand_name=get_brand_name(),
    )


# v82 STEP5: 주문 관리 화면 전용 스코프 스타일(.kgp-oc). _BASE_HTML(전 화면 공용)은 불변 — D-9 범위통제.
#   gogabridj 토큰을 스코프 CSS 변수 단일 소스로. 색 파생은 color-mix로(하드코딩 tint hex 금지).
_ORDERS_STYLE = """
<style>
.kgp-oc{--ink:#1A1714;--hanji:#F5EFE3;--paper:#FBF8F1;--gold:#C9A24B;--teal:#119A8E;--orange:#F5821F;
  --red:#C0392B;--line:#E6DECB;--muted:#8A8275;--ink-soft:#3A352E;--r:16px;
  --shadow:0 1px 2px rgba(26,23,20,.06),0 8px 30px rgba(26,23,20,.08);
  --ease-out:cubic-bezier(.23,1,.32,1);--ease-drawer:cubic-bezier(.32,.72,0,1);color:var(--ink)}
.kgp-oc *{box-sizing:border-box}
.kgp-oc .oc-h{font-family:"Noto Serif KR",serif;font-weight:700;font-size:1.5rem;letter-spacing:-.02em;margin:4px 0 2px}
.kgp-oc .oc-subh{color:var(--muted);font-size:.85rem;margin-bottom:18px}
.kgp-oc .oc-tabs{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:16px}
.kgp-oc .oc-div{width:1px;height:22px;background:var(--line);margin:0 6px}
.kgp-oc .oc-tab{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:999px;
  text-decoration:none;color:var(--ink-soft);font-size:.86rem;font-weight:600;border:1px solid transparent;
  transition:background .18s var(--ease-out),color .18s var(--ease-out)}
.kgp-oc .oc-tab:hover{background:var(--hanji)}
.kgp-oc .oc-tab--active{background:var(--ink);color:var(--hanji)}
.kgp-oc .oc-tab-count{font-size:.75rem;opacity:.7}
.kgp-oc .oc-new{background:var(--teal);color:#fff;font-size:.6rem;font-weight:800;letter-spacing:.04em;padding:2px 5px;border-radius:5px}
.kgp-oc .oc-card{background:var(--paper);border:1px solid var(--line);box-shadow:var(--shadow);border-radius:var(--r);padding:16px 18px;margin-bottom:18px}
.kgp-oc .oc-filt{display:flex;flex-wrap:wrap;gap:16px;align-items:center}
.kgp-oc .oc-filt-grp{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.kgp-oc .oc-lbl{font-size:.78rem;color:var(--muted);margin-right:2px}
.kgp-oc .oc-preset{padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:#fff;
  color:var(--ink-soft);font-size:.8rem;cursor:pointer;transition:transform .12s var(--ease-out),border-color .18s,color .18s}
.kgp-oc .oc-preset:active{transform:scale(.97)}
.kgp-oc .oc-preset--on{border-color:var(--teal);color:var(--teal);background:color-mix(in srgb,var(--teal) 8%,transparent)}
.kgp-oc .oc-chip{display:inline-flex;align-items:center;gap:5px;padding:5px 10px;border-radius:999px;border:1px solid var(--line);background:#fff;font-size:.8rem;cursor:pointer}
.kgp-oc .oc-chip input{accent-color:var(--teal)}
.kgp-oc .oc-refresh{margin-left:auto;font-size:.76rem;color:var(--muted)}
.kgp-oc .oc-tablewrap{background:#fff;border:1px solid var(--line);box-shadow:var(--shadow);border-radius:var(--r);overflow-x:auto}
.kgp-oc table{width:100%;min-width:860px;border-collapse:collapse}
.kgp-oc thead th{background:var(--hanji);color:var(--ink-soft);font-size:.74rem;font-weight:700;text-align:left;padding:11px 14px;white-space:nowrap}
.kgp-oc tbody td{padding:12px 14px;border-top:1px solid var(--line);font-size:.86rem;vertical-align:middle}
.kgp-oc tbody tr{transition:background .15s var(--ease-out)}
.kgp-oc tbody tr:hover{background:var(--paper)}
.kgp-oc .oc-sub{color:var(--muted);font-size:.76rem;margin-top:2px}
.kgp-oc .oc-cust,.kgp-oc .oc-title{font-weight:600}
.kgp-oc .oc-title{max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kgp-oc .oc-price{font-weight:700}
.kgp-oc .oc-dt{color:var(--ink-soft);white-space:nowrap}
.kgp-oc .oc-badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:.74rem;font-weight:700;white-space:nowrap}
.kgp-oc tbody td:first-child{white-space:nowrap}
.kgp-oc .oc-badge--paid{background:color-mix(in srgb,var(--teal) 14%,transparent);color:var(--teal)}
.kgp-oc .oc-badge--prep{background:color-mix(in srgb,var(--orange) 16%,transparent);color:color-mix(in srgb,var(--orange),var(--ink) 42%)}
.kgp-oc .oc-badge--ship{background:color-mix(in srgb,var(--gold) 20%,transparent);color:color-mix(in srgb,var(--gold),var(--ink) 55%)}
.kgp-oc .oc-badge--done{background:color-mix(in srgb,var(--muted) 16%,transparent);color:var(--ink-soft)}
.kgp-oc .oc-badge--cancel{background:color-mix(in srgb,var(--red) 12%,transparent);color:var(--red)}
.kgp-oc .oc-links{white-space:nowrap}
.kgp-oc .oc-ico{display:inline-flex;width:26px;height:26px;align-items:center;justify-content:center;border-radius:8px;
  text-decoration:none;color:var(--teal);border:1px solid var(--line);margin-right:4px;transition:transform .12s var(--ease-out),background .15s}
.kgp-oc .oc-ico:hover{background:var(--hanji)}
.kgp-oc .oc-ico:active{transform:scale(.94)}
.kgp-oc .oc-ico--off{color:var(--line);cursor:default}
.kgp-oc .oc-detail{background:var(--ink);color:var(--hanji);border:0;padding:7px 14px;border-radius:999px;font-size:.8rem;font-weight:600;cursor:pointer;white-space:nowrap;transition:transform .12s var(--ease-out)}
.kgp-oc td:last-child{white-space:nowrap}
.kgp-oc .oc-detail:active{transform:scale(.97)}
.kgp-oc .oc-empty{color:var(--muted);text-align:center;padding:48px 0}
.kgp-oc-scrim{position:fixed;inset:0;background:rgba(26,23,20,.38);opacity:0;pointer-events:none;transition:opacity .3s var(--ease-out);z-index:9998}
.kgp-oc-scrim.on{opacity:1;pointer-events:auto}
.kgp-oc-drawer{position:fixed;top:0;right:0;height:100%;width:min(440px,92vw);background:var(--paper);
  box-shadow:-12px 0 40px rgba(26,23,20,.22);transform:translateX(100%);transition:transform .42s var(--ease-drawer);
  z-index:9999;display:flex;flex-direction:column}
.kgp-oc-drawer.on{transform:translateX(0)}
.kgp-oc-dhead{padding:18px 20px;border-bottom:1px solid var(--line);position:relative}
.kgp-oc-dhead .oc-h{font-size:1.2rem}
.kgp-oc-dbtns{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
.kgp-oc-dbtn{display:inline-flex;align-items:center;gap:6px;padding:8px 13px;border-radius:999px;border:1px solid var(--teal);
  color:var(--teal);background:#fff;text-decoration:none;font-size:.8rem;font-weight:600;transition:transform .12s var(--ease-out),background .15s}
.kgp-oc-dbtn:hover{background:color-mix(in srgb,var(--teal) 8%,transparent)}
.kgp-oc-dbtn:active{transform:scale(.97)}
.kgp-oc-dbtn--off{border-color:var(--line);color:var(--muted);pointer-events:none}
.kgp-oc-dbody{padding:18px 20px;overflow-y:auto;flex:1}
.kgp-oc-sec{margin-bottom:20px}
.kgp-oc-sec h4{font-family:"Noto Serif KR",serif;font-size:.95rem;margin:0 0 8px;color:var(--ink)}
.kgp-oc-row{display:flex;justify-content:space-between;gap:14px;padding:7px 0;border-bottom:1px dashed var(--line);font-size:.85rem}
.kgp-oc-row .k{color:var(--muted)}
.kgp-oc-row .v{color:var(--ink);font-weight:600;text-align:right;word-break:break-all}
.kgp-oc-x{position:absolute;top:16px;right:16px;background:transparent;border:0;font-size:1.3rem;cursor:pointer;color:var(--ink-soft);line-height:1}
@media (prefers-reduced-motion:reduce){.kgp-oc-drawer{transition:transform .01ms}.kgp-oc-scrim{transition:opacity .01ms}
  .kgp-oc *{transition-duration:.01ms!important}}
@media (max-width:860px){.kgp-oc-drawer{width:100vw}.kgp-oc .oc-title{max-width:150px}}
</style>
"""

# 주문 관리 클라이언트 로직(기간/마켓 필터 · 상세 드로어). 라우트·데이터 불변 — 렌더된 행에서만 동작.
_ORDERS_SCRIPT = """
<script>
(function(){
  var activePreset=null;
  function esc(s){return String(s).replace(/[&<>\\"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','\\"':'&quot;'}[c];});}
  window.ocFilter=function(){
    var rows=document.querySelectorAll('.kgp-oc tbody tr[data-order]');
    var chips=document.querySelectorAll('.kgp-oc .oc-chip input');
    var on={},any=false;
    chips.forEach(function(c){ if(c.checked){on[c.value]=1;any=true;} });
    var now=Date.now();
    rows.forEach(function(tr){
      var show=true;
      if(any){ var m=tr.getAttribute('data-market')||''; if(!on[m]) show=false; }
      if(show && activePreset){ var d=Date.parse((tr.getAttribute('data-date')||'')+'T00:00:00');
        if(isNaN(d) || (now-d)>activePreset) show=false; }
      tr.style.display=show?'':'none';
    });
  };
  window.ocPreset=function(btn,days){
    var was=btn.classList.contains('oc-preset--on');
    document.querySelectorAll('.kgp-oc .oc-preset').forEach(function(b){b.classList.remove('oc-preset--on');});
    if(was){activePreset=null;} else {btn.classList.add('oc-preset--on'); activePreset=days*86400000;}
    window.ocFilter();
  };
  window.ocOpen=function(btn){
    var tr=btn.closest('tr'); if(!tr) return;
    var data={}; try{data=JSON.parse(tr.getAttribute('data-order')||'{}');}catch(e){}
    var body=document.getElementById('ocDbody'), btns=document.getElementById('ocDbtns');
    var html='';
    ['주문정보','상품정보','배송정보'].forEach(function(sec){
      var obj=data[sec]||{}, rowsp='';
      Object.keys(obj).forEach(function(k){ var v=obj[k]; if(v===''||v==null) return;
        rowsp+='<div class="kgp-oc-row"><span class="k">'+esc(k)+'</span><span class="v">'+esc(String(v))+'</span></div>'; });
      if(rowsp) html+='<div class="kgp-oc-sec"><h4>'+esc(sec)+'</h4>'+rowsp+'</div>';
    });
    body.innerHTML=html||'<div class="oc-empty">표시할 정보가 없어요.</div>';
    var L=data.links||{};
    var defs=[['수집처',L['수집처'],'◈'],['판매마켓',L['판매마켓'],'▤'],['상세페이지',L['상세페이지'],'↗']];
    btns.innerHTML=defs.map(function(d){
      if(d[1]) return '<a class="kgp-oc-dbtn" href="'+esc(d[1])+'" target="_blank" rel="noopener">'+d[2]+' '+esc(d[0])+'</a>';
      return '<span class="kgp-oc-dbtn kgp-oc-dbtn--off">'+d[2]+' '+esc(d[0])+'</span>';
    }).join('');
    document.getElementById('ocScrim').classList.add('on');
    document.getElementById('ocDrawer').classList.add('on');
  };
  window.ocClose=function(){
    document.getElementById('ocDrawer').classList.remove('on');
    document.getElementById('ocScrim').classList.remove('on');
  };
  document.addEventListener('keydown',function(e){ if(e.key==='Escape') window.ocClose(); });
})();
</script>
"""


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

    # v82 STEP5: 주문 관리 화면 리모델(표면 계층만 — 라우트·데이터 구조·JSON 응답 불변).
    #   상태 탭바 + 필터 카드(기간/마켓/갱신시각) + 리모델 테이블(링크 아이콘·상세 버튼) + 상세 드로어.
    #   gogabridj 토큰(스코프 CSS 변수)·Noto Serif KR 헤드라인·상태뱃지 공통·drawer 우측 슬라이드.
    import html as _html
    import json as _json
    from collections import Counter
    from markupsafe import Markup

    status_filter = request.args.get("status", "").lower()
    all_orders = _load_orders()
    view_orders = [
        o for o in all_orders
        if not status_filter or str(o.get("status", "")).lower() == status_filter
    ]

    if request.args.get("format") == "json" or request.accept_mimetypes.best == "application/json":
        return jsonify({"count": len(view_orders), "orders": view_orders})

    counts = Counter(str(o.get("status", "")).lower() for o in all_orders)

    def _fmt_price(v):
        try:
            return "₩{:,}".format(int(float(v)))
        except (TypeError, ValueError):
            v = "" if v is None else str(v)
            return _html.escape(v) if v else "—"

    def _fmt_dt(v):
        s = str(v or "")
        try:
            d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
            return d.strftime("%m-%d %H:%M")
        except Exception:
            return (s[:16].replace("T", " ")) or "—"

    _STATUS_KO = {
        "paid": "결제완료", "pending": "배송준비중", "processing": "배송준비중",
        "in_progress": "배송준비중", "shipped": "배송중", "completed": "배송완료",
        "cancelled": "취소", "canceled": "취소", "returned": "반품",
        "exchanged": "교환", "refunded": "환불",
    }

    def _status_ko(status):
        return _STATUS_KO.get(str(status).lower(), str(status) or "—")

    def _order_chip(status):
        s = str(status).lower()
        label = _status_ko(status)
        if s == "paid":
            tone = "paid"
        elif s in ("pending", "processing", "in_progress"):
            tone = "prep"
        elif s == "shipped":
            tone = "ship"
        elif s == "completed":
            tone = "done"
        else:
            tone = "cancel"
        return '<span class="oc-badge oc-badge--%s">%s</span>' % (tone, _html.escape(str(label)))

    # 상태 탭(진행군 + 취소·반품·교환군 분리). ?status= 기존 라우트 파라미터 재사용.
    def _tab(val, lbl, is_new=False):
        active = " oc-tab--active" if (status_filter == val or (not val and not status_filter)) else ""
        n = counts.get(val, 0)
        cnt = ' <span class="oc-tab-count">%d</span>' % n if val and n else ""
        newb = ' <span class="oc-new">NEW</span>' if (is_new and n) else ""
        href = ("?status=%s" % val) if val else "?"
        return '<a class="oc-tab%s" href="%s">%s%s%s</a>' % (active, href, _html.escape(lbl), cnt, newb)

    flow = [("", "전체"), ("paid", "결제완료"), ("pending", "배송준비중"),
            ("shipped", "배송중"), ("completed", "배송완료")]
    post = [("cancelled", "취소"), ("returned", "반품"), ("exchanged", "교환")]
    tabs_html = "".join(_tab(v, l, is_new=(v == "paid")) for v, l in flow)
    post_html = "".join(_tab(v, l) for v, l in post)

    markets = sorted({str(o.get("market") or o.get("marketplace") or "").strip()
                      for o in all_orders if (o.get("market") or o.get("marketplace"))})
    chips_html = "".join(
        '<label class="oc-chip"><input type="checkbox" checked value="%s" onchange="ocFilter()"> %s</label>'
        % (_html.escape(m), _html.escape(m)) for m in markets)

    def _lnk(url, label, glyph):
        if not url:
            return '<span class="oc-ico oc-ico--off" title="%s 없음">%s</span>' % (_html.escape(label), glyph)
        return ('<a class="oc-ico" href="%s" target="_blank" rel="noopener" title="%s">%s</a>'
                % (_html.escape(url), _html.escape(label), glyph))

    rows = ""
    for o in view_orders[:200]:
        oid = o.get("order_id", o.get("order_number", "")) or ""
        onum = o.get("order_number", oid) or oid
        customer = o.get("customer_name", "") or "—"
        sku = o.get("sku", "") or ""
        title = o.get("title_ko") or o.get("title_original") or sku or "—"
        option = o.get("option") or o.get("sku_option") or ""
        market = str(o.get("market") or o.get("marketplace") or "—")
        qty = o.get("quantity", o.get("qty", 1)) or 1
        status = o.get("status", "")
        order_dt = str(o.get("order_date", "")) or ""
        src_url = o.get("source_url") or o.get("source_link") or ""
        mkt_url = o.get("market_url") or o.get("listing_url") or ""
        det_url = o.get("detail_url") or o.get("product_url") or ""
        drawer = {
            "주문정보": {
                "주문번호": str(onum), "주문ID": str(oid), "주문시간": _fmt_dt(order_dt),
                "상태": _status_ko(status), "마켓": market, "주문자": str(customer),
                "개인통관고유부호(PCC)": o.get("pcc") or o.get("personal_customs_code") or "",
            },
            "상품정보": {
                "상품명": str(title), "옵션": str(option), "SKU": str(sku), "수량": str(qty),
                "판매가": _fmt_price(o.get("sell_price_krw", "")),
                "원가": _fmt_price(o.get("buy_price", o.get("price_original", ""))),
                "마진": ("%s%%" % o.get("margin_pct")) if o.get("margin_pct") not in (None, "") else "",
            },
            "배송정보": {
                "수취인": str(customer), "국가": o.get("country") or "",
                "송장번호": o.get("tracking_no") or o.get("tracking") or "",
                "배송상태": _status_ko(status),
            },
            "links": {"수집처": src_url, "판매마켓": mkt_url, "상세페이지": det_url},
        }
        dj = _html.escape(_json.dumps(drawer, ensure_ascii=False), quote=True)
        links_cell = _lnk(src_url, "수집처", "◈") + _lnk(mkt_url, "판매마켓", "▤") + _lnk(det_url, "상세페이지", "↗")
        rows += (
            '<tr data-market="%s" data-date="%s" data-order="%s">' % (
                _html.escape(market), _html.escape(order_dt[:10]), dj)
            + '<td>%s</td>' % _order_chip(status)
            + '<td class="oc-dt">%s</td>' % _html.escape(_fmt_dt(order_dt))
            + '<td>%s</td>' % _html.escape(market)
            + '<td><div class="oc-cust">%s</div><div class="oc-sub">%s</div></td>' % (
                _html.escape(str(customer)), _html.escape(str(onum)))
            + '<td><div class="oc-title">%s</div><div class="oc-sub">%s</div></td>' % (
                _html.escape(str(title)), _html.escape(str(option)))
            + '<td><div>×%s</div><div class="oc-price">%s</div></td>' % (
                _html.escape(str(qty)), _fmt_price(o.get("sell_price_krw", "")))
            + '<td class="oc-links">%s</td>' % links_cell
            + '<td><button type="button" class="oc-detail" onclick="ocOpen(this)">상세</button></td>'
            + '</tr>'
        )
    if not rows:
        rows = '<tr><td colspan="8" class="oc-empty">해당 조건의 주문이 없어요. 필터를 바꿔보세요.</td></tr>'

    now_hm = datetime.datetime.now().strftime("%H:%M:%S")
    body = (
        _ORDERS_STYLE
        + '<div class="kgp-oc">'
        + '<div class="oc-h">주문 관리</div>'
        + '<div class="oc-subh">결제부터 배송까지, 한 화면에서 봅니다.</div>'
        + '<div class="oc-tabs">' + tabs_html + '<span class="oc-div"></span>' + post_html + '</div>'
        + '<div class="oc-card"><div class="oc-filt">'
        + '<div class="oc-filt-grp"><span class="oc-lbl">기간</span>'
        + '<button type="button" class="oc-preset" onclick="ocPreset(this,1)">오늘</button>'
        + '<button type="button" class="oc-preset" onclick="ocPreset(this,3)">3일</button>'
        + '<button type="button" class="oc-preset" onclick="ocPreset(this,7)">1주</button>'
        + '<button type="button" class="oc-preset" onclick="ocPreset(this,14)">2주</button>'
        + '<button type="button" class="oc-preset" onclick="ocPreset(this,30)">1개월</button>'
        + '</div>'
        + (('<div class="oc-filt-grp"><span class="oc-lbl">마켓</span>' + chips_html + '</div>') if chips_html else '')
        + '<span class="oc-refresh">갱신 ' + now_hm + '</span>'
        + '</div></div>'
        + '<div class="oc-tablewrap"><table><thead><tr>'
        + '<th>상태</th><th>주문시간</th><th>마켓</th><th>주문자 / 번호</th>'
        + '<th>상품명 / 옵션</th><th>수량 / 금액</th><th>링크</th><th></th>'
        + '</tr></thead><tbody>' + rows + '</tbody></table></div>'
        + '<div class="oc-subh" style="margin-top:12px">표시 ' + str(len(view_orders[:200]))
        + '건 · 전체 ' + str(len(all_orders)) + '건</div>'
        + '</div>'
        + '<div class="kgp-oc"><div id="ocScrim" class="kgp-oc-scrim" onclick="ocClose()"></div>'
        + '<aside id="ocDrawer" class="kgp-oc-drawer" role="dialog" aria-modal="true" aria-label="주문 상세">'
        + '<button class="kgp-oc-x" onclick="ocClose()" aria-label="닫기">×</button>'
        + '<div class="kgp-oc-dhead"><div class="oc-h">주문 상세</div><div id="ocDbtns" class="kgp-oc-dbtns"></div></div>'
        + '<div id="ocDbody" class="kgp-oc-dbody"></div>'
        + '</aside></div>'
        + _ORDERS_SCRIPT
    )
    # v82 STEP5: 동적 값은 전부 _html.escape 완료 → 이 화면 body만 안전 표시(_BASE_HTML의 {{body}} 오토이스케이프
    #   회피). _render(전 화면 공용)은 불변이라 타 화면 이스케이프 정책·보안 자세는 그대로.
    return _render("주문 관리", Markup(body))


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
