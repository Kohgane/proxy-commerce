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
import html as _html
import logging
import os
from urllib.parse import quote

from flask import Blueprint, jsonify, redirect, render_template_string, request, session
from markupsafe import Markup

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
_WEB_UI_ENABLED = os.getenv("DASHBOARD_WEB_UI_ENABLED", "1") == "1"

web_ui_bp = Blueprint("dashboard_web_ui", __name__, url_prefix="/dashboard")


# ---------------------------------------------------------------------------
# v87 S1.5: 관리자 인증 게이트 (deny-by-default)
# ---------------------------------------------------------------------------
#   /dashboard/* 는 주문 화면에서 고객 실명·개인통관고유부호(PCC)를 렌더한다. 그런데 이 블루프린트에는
#   인증 검사가 아예 없어서 URL만 알면 누구나 열람할 수 있었다(/admin/* 는 이미 게이트가 있었음).
#   블루프린트 단위 before_request 한 곳에서 막는다 — 라우트마다 데코레이터를 붙이지 않으므로
#   **이 블루프린트에 새로 추가되는 라우트도 자동으로 차단**된다(기본 차단).

# 항상 JSON만 돌려주는 엔드포인트 — 브라우저 Accept 헤더와 무관하게 401/403을 JSON으로 준다.
_JSON_ONLY_ENDPOINTS = {"dashboard_web_ui.summary_json"}


def _wants_json() -> bool:
    """JSON/API성 요청인지 — 비인증 시 리다이렉트 대신 401을 줘야 하는 요청."""
    if request.endpoint in _JSON_ONLY_ENDPOINTS:
        return True
    if request.args.get("format") == "json":
        return True
    if request.is_json:
        return True
    return request.accept_mimetypes.best == "application/json"


@web_ui_bp.before_request
def _dashboard_auth_gate():
    """/dashboard/* 전 라우트 단일 인증 게이트.

    미로그인 → HTML은 /auth/login 리다이렉트(next 보존), JSON은 401.
    로그인했지만 비-admin → 403(HTML/JSON 각각).
    """
    from src.auth.admin_resolver import is_admin_session

    if not session.get("user_id"):
        if _wants_json():
            return jsonify({"error": "authentication_required"}), 401
        # next는 반드시 인코딩 — 안 하면 원래 쿼리의 ?/&가 로그인 URL 파싱을 깨뜨린다.
        # 값은 항상 이 앱의 요청 경로(선행 "/")라 외부 도메인으로 새지 않는다.
        nxt = request.full_path if request.query_string else request.path
        return redirect("/auth/login?next=" + quote(nxt, safe="/"))

    admin_ok, _reason = is_admin_session(session)
    if not admin_ok:
        if _wants_json():
            return jsonify({"error": "admin_required"}), 403
        return _render(
            "접근 거부",
            _page_head("접근 제한", "관리자만 볼 수 있어요.",
                       "이 화면은 주문·고객 정보를 다루기 때문에 관리자 계정으로만 열 수 있습니다."),
        ), 403
    return None


@web_ui_bp.after_request
def _dashboard_no_store(response):
    """PCC·고객명이 실리는 화면 — 중간 캐시·뒤로가기 캐시에 남기지 않는다."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    return response

# ---------------------------------------------------------------------------
# HTML 템플릿
# ---------------------------------------------------------------------------

# v87 STEP1: 다리/게이트/키스톤 시그니처 마크(라인아트). 금 아치 + 청록 데크 2줄 + 주황 키스톤.
#   이모지·지구본 금지(gogabridj-design 절대원칙) — 상단바 브랜드 표식은 이 SVG 하나로 통일한다.
_BRIDGE_MARK = (
    '<svg class="kgp-mark" viewBox="0 0 40 28" aria-hidden="true" focusable="false">'
    '<path d="M4 24 A16 16 0 0 1 36 24" fill="none" stroke="var(--gold)" stroke-width="2.4" stroke-linecap="round"/>'
    '<line x1="2" y1="24" x2="38" y2="24" stroke="var(--teal)" stroke-width="2.4" stroke-linecap="round"/>'
    '<line x1="5" y1="19.4" x2="35" y2="19.4" stroke="var(--teal)" stroke-width="1.3" stroke-linecap="round" opacity=".5"/>'
    '<circle cx="20" cy="8" r="2.7" fill="var(--orange)"/>'
    '</svg>'
)

# 상단 내비게이션 단일 정의(경로, 라벨). 활성 표시는 aria-current="page"로 — 상태 없는 링크 금지.
_NAV_ITEMS = (
    ("/dashboard/", "한눈에 보기", "index"),
    ("/dashboard/products", "상품 수집", "products"),
    ("/dashboard/uploads", "업로드", "uploads"),
    ("/dashboard/orders", "주문", "orders"),
    ("/dashboard/fx", "환율·마진", "fx"),
)


def _nav_html(active: str = "") -> str:
    out = []
    for href, label, key in _NAV_ITEMS:
        cur = ' aria-current="page"' if key == active else ""
        out.append('<a href="%s"%s>%s</a>' % (href, cur, _html.escape(label)))
    return "".join(out)


_BASE_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{{ description }}">
<meta name="robots" content="noindex, nofollow">
<meta name="build" content="{{ build_sha }}">{# 라이브 배포 커밋 판정(curl 한 줄) — v53 STEP0 규약 #}
<meta name="theme-color" content="#1A1714">
<meta property="og:site_name" content="{{ brand_name }}">
<meta property="og:title" content="{{ brand_name }}">
<meta property="og:description" content="{{ description }}">
<meta property="og:type" content="website">
<title>{{ title }} | {{ brand_name }}</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600;700&display=swap">
<style>
/* ══ 고가브릿지 콘솔 디자인 시스템 (v87 STEP1) ═══════════════════════════════
   토큰 단일 소스. 화면 CSS는 여기 var()만 참조한다 — 하드코딩 hex/px 금지.
   간격은 8px 리듬(--s1~--s6), 카드는 --line 보더 + --shadow로 통일. */
:root{
  --ink:#1A1714; --ink-soft:#3A352E; --muted:#8A8275;
  --hanji:#F5EFE3; --paper:#FBF8F1; --surface:#FFFFFF;
  --gold:#C9A24B; --teal:#119A8E; --teal-bright:#0FC2C0; --orange:#F5821F; --red:#C0392B;
  --line:#E6DECB;
  --r:18px; --r-sm:10px; --r-pill:999px;
  --shadow:0 1px 2px rgba(26,23,20,.06),0 8px 30px rgba(26,23,20,.08);
  --s1:8px; --s2:16px; --s3:24px; --s4:32px; --s5:48px; --s6:64px;
  --font-display:"Noto Serif KR","Nanum Myeongjo",Georgia,serif;
  --font-ui:"Pretendard Variable","Pretendard","Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  --dur:180ms; --dur-slow:260ms;
  --ease-out:cubic-bezier(.23,1,.32,1); --ease-drawer:cubic-bezier(.32,.72,0,1);
}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--font-ui);
  font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}

/* 개발자스러움 킬리스트 ①② — 브라우저 기본 파랑 링크·기본 포커스링 박멸 */
a{color:var(--teal);text-decoration:none}
a:hover{text-decoration:underline;text-underline-offset:3px}
:focus{outline:none}
:focus-visible{outline:2px solid var(--teal);outline-offset:2px;border-radius:var(--r-sm)}

/* ── 상단바 ── */
.kgp-top{display:flex;align-items:center;gap:var(--s3);height:60px;padding:0 var(--s3);
  background:var(--ink);color:var(--hanji);position:sticky;top:0;z-index:40}
.kgp-brand{display:inline-flex;align-items:center;gap:10px;flex-shrink:0;color:var(--hanji)}
.kgp-brand:hover{text-decoration:none}
.kgp-mark{width:30px;height:21px;display:block}
.kgp-word{font-family:var(--font-display);font-weight:700;font-size:1.05rem;letter-spacing:-.02em}
.kgp-nav{display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}
.kgp-nav::-webkit-scrollbar{display:none}
.kgp-nav a{display:inline-flex;align-items:center;height:44px;padding:0 14px;border-radius:var(--r-pill);
  color:color-mix(in srgb,var(--hanji) 64%,transparent);font-size:.88rem;font-weight:600;white-space:nowrap;
  transition:color var(--dur) var(--ease-out),background var(--dur) var(--ease-out)}
.kgp-nav a:hover{color:var(--hanji);background:color-mix(in srgb,var(--hanji) 10%,transparent);text-decoration:none}
.kgp-nav a[aria-current="page"]{color:var(--hanji);background:color-mix(in srgb,var(--hanji) 14%,transparent)}
.kgp-nav a[aria-current="page"]::before{content:"";width:5px;height:5px;border-radius:50%;
  background:var(--teal-bright);margin-right:7px;flex-shrink:0}
.kgp-main{max-width:1200px;margin:0 auto;padding:var(--s4) var(--s3) var(--s6)}

/* ── 타이포 위계: 세리프 오버사이즈 헤드라인 + 본문 대비 ── */
.kgp-head{margin-bottom:var(--s4)}
.kgp-head::after{content:"";display:block;height:1px;background:var(--line);margin-top:var(--s3)}
.kgp-overline{font-size:.7rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--gold)}
.kgp-h1{font-family:var(--font-display);font-weight:700;font-size:clamp(28px,3.6vw,40px);
  letter-spacing:-.03em;line-height:1.2;margin:6px 0 0}
.kgp-sub{color:var(--muted);font-size:.9rem;margin:var(--s1) 0 0}
.kgp-h2{font-family:var(--font-display);font-weight:600;font-size:1.15rem;letter-spacing:-.02em;
  margin:var(--s5) 0 var(--s2)}

/* ── 카드 · KPI ── */
.kgp-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);
  box-shadow:var(--shadow);padding:var(--s3)}
.kgp-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:var(--s2);margin-bottom:var(--s4)}
.kgp-kpi{position:relative;overflow:hidden}
.kgp-kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--accent,var(--teal))}
.kgp-kpi-label{font-size:.7rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.kgp-kpi-value{font-family:var(--font-display);font-weight:700;font-size:clamp(30px,3.4vw,42px);
  line-height:1.1;letter-spacing:-.03em;margin:10px 0 6px;font-variant-numeric:tabular-nums}
.kgp-kpi-sub{font-size:.8rem;color:var(--muted)}

/* ── 버튼: 주 CTA=키스톤 주황(화면당 1개) / 보조=먹 아웃라인 ── */
.kgp-btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:44px;padding:0 20px;
  border-radius:var(--r-pill);border:1px solid transparent;background:transparent;color:var(--ink);
  font-family:var(--font-ui);font-size:.88rem;font-weight:600;cursor:pointer;
  transition:transform 120ms var(--ease-out),background var(--dur) var(--ease-out),
    border-color var(--dur) var(--ease-out),box-shadow var(--dur) var(--ease-out)}
.kgp-btn:hover{text-decoration:none}
/* 뜨는 hover는 진짜 포인터에서만 — 터치는 탭할 때 가짜 hover가 걸려 눌린 채로 남는다. */
@media (hover:hover) and (pointer:fine){.kgp-btn:hover{transform:translateY(-2px)}}
.kgp-btn:active{transform:translateY(0) scale(.97)}
.kgp-btn--primary{background:var(--orange);color:var(--surface);
  box-shadow:0 2px 10px color-mix(in srgb,var(--orange) 30%,transparent)}
.kgp-btn--primary:hover{box-shadow:0 6px 18px color-mix(in srgb,var(--orange) 36%,transparent)}
.kgp-btn--ghost{border-color:var(--line);background:var(--surface)}
.kgp-btn--ghost:hover{border-color:var(--ink);background:var(--hanji)}
.kgp-btnrow{display:flex;flex-wrap:wrap;gap:var(--s1);align-items:center}
.kgp-btnrow form{margin:0}

/* ── 상태 뱃지(전 화면 공통): 성공=청록 / 확인필요=주황 / 실패=적 / 중립=먹 40% ── */
.kgp-badge{display:inline-flex;align-items:center;padding:4px 11px;border-radius:var(--r-pill);
  font-size:.75rem;font-weight:700;line-height:1.4;white-space:nowrap}
.kgp-badge--ok{background:color-mix(in srgb,var(--teal) 13%,transparent);color:var(--teal)}
.kgp-badge--warn{background:color-mix(in srgb,var(--orange) 16%,transparent);
  color:color-mix(in srgb,var(--orange),var(--ink) 42%)}
.kgp-badge--err{background:color-mix(in srgb,var(--red) 12%,transparent);color:var(--red)}
.kgp-badge--neutral{background:color-mix(in srgb,var(--muted) 15%,transparent);color:var(--ink-soft)}

/* ── 테이블: 고정 헤더 · 호버 행 · 숫자 우정렬 ── */
.kgp-tablewrap{background:var(--surface);border:1px solid var(--line);border-radius:var(--r);
  box-shadow:var(--shadow);overflow:auto;max-height:72vh}
.kgp-table{width:100%;border-collapse:separate;border-spacing:0}
.kgp-table thead th{position:sticky;top:0;z-index:1;background:var(--hanji);color:var(--ink-soft);
  font-size:.72rem;font-weight:700;letter-spacing:.06em;text-align:left;padding:12px var(--s2);
  white-space:nowrap;border-bottom:1px solid var(--line)}
.kgp-table tbody td{padding:13px var(--s2);border-top:1px solid var(--line);font-size:.88rem;vertical-align:middle}
.kgp-table tbody tr:first-child td{border-top:0}
.kgp-table tbody tr{transition:background 150ms var(--ease-out)}
.kgp-table tbody tr:hover td{background:var(--paper)}
.kgp-table .num,.kgp-table th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.kgp-table td.num{font-weight:600}
.kgp-strong{font-weight:600}
.kgp-cellsub{color:var(--muted);font-size:.78rem;margin-top:2px}

/* ── 입력 · 셀렉트 · 체크칩 ── */
.kgp-filter{display:flex;flex-wrap:wrap;gap:var(--s2);align-items:flex-end;margin-bottom:var(--s2)}
.kgp-field{display:flex;flex-direction:column;gap:6px}
.kgp-label{font-size:.72rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.kgp-input,.kgp-select{min-height:44px;padding:0 14px;border:1px solid var(--line);border-radius:var(--r-sm);
  background:var(--surface);color:var(--ink);font-family:var(--font-ui);font-size:.9rem;
  transition:border-color var(--dur) var(--ease-out),box-shadow var(--dur) var(--ease-out)}
.kgp-input:hover,.kgp-select:hover{border-color:color-mix(in srgb,var(--ink) 26%,var(--line))}
.kgp-input:focus,.kgp-select:focus{border-color:var(--teal);
  box-shadow:0 0 0 3px color-mix(in srgb,var(--teal) 16%,transparent)}
.kgp-select{appearance:none;padding-right:38px;cursor:pointer;
  background-image:linear-gradient(45deg,transparent 50%,var(--ink-soft) 50%),
    linear-gradient(135deg,var(--ink-soft) 50%,transparent 50%);
  background-position:calc(100% - 19px) 20px,calc(100% - 14px) 20px;
  background-size:5px 5px,5px 5px;background-repeat:no-repeat}
.kgp-chip{display:inline-flex;align-items:center;gap:6px;min-height:36px;padding:0 13px;
  border-radius:var(--r-pill);border:1px solid var(--line);background:var(--surface);font-size:.82rem;cursor:pointer;
  transition:border-color var(--dur) var(--ease-out),color var(--dur) var(--ease-out),background var(--dur) var(--ease-out)}
.kgp-chip:hover{border-color:var(--ink)}
.kgp-chip input{accent-color:var(--teal);margin:0}
.kgp-count{font-size:.8rem;color:var(--muted);margin-left:auto;align-self:center}

/* ── 빈 상태: 일러스트 없이 세리프 한 줄 + 행동 버튼 ── */
.kgp-empty{text-align:center;padding:var(--s6) var(--s3)}
.kgp-empty-t{font-family:var(--font-display);font-weight:600;font-size:1.1rem;letter-spacing:-.02em;color:var(--ink)}
.kgp-empty-s{color:var(--muted);font-size:.86rem;margin:10px 0 var(--s3)}

/* ── 스켈레톤 로딩 ── */
/* 무한 반복 모션은 linear — ease면 루프 이음매에서 멈칫한다. */
.kgp-skel{height:1em;border-radius:var(--r-sm);background-size:400% 100%;animation:kgpShim 1.4s linear infinite;
  background-image:linear-gradient(90deg,var(--hanji) 25%,
    color-mix(in srgb,var(--hanji) 50%,var(--surface)) 37%,var(--hanji) 63%)}
@keyframes kgpShim{0%{background-position:100% 50%}100%{background-position:0 50%}}

/* ── 토스트 ── */
.kgp-toast{position:fixed;right:var(--s3);bottom:var(--s3);z-index:60;display:flex;align-items:center;gap:10px;
  max-width:min(380px,88vw);padding:14px 18px;border-radius:var(--r);background:var(--ink);color:var(--hanji);
  border-left:3px solid var(--teal);box-shadow:0 12px 40px rgba(26,23,20,.28);font-size:.88rem;
  opacity:0;transform:translateY(10px);pointer-events:none;
  transition:opacity var(--dur-slow) var(--ease-out),transform var(--dur-slow) var(--ease-out)}
.kgp-toast.on{opacity:1;transform:translateY(0);pointer-events:auto}
.kgp-toast--warn{border-left-color:var(--orange)}
.kgp-toast--err{border-left-color:var(--red)}

/* ── 안내 노트 ── */
.kgp-note{display:flex;gap:10px;padding:14px var(--s2);border-radius:var(--r-sm);background:var(--hanji);
  border-left:3px solid var(--gold);font-size:.85rem;color:var(--ink-soft)}
.kgp-meta{color:var(--muted);font-size:.78rem;margin-top:var(--s3)}

@media (max-width:860px){
  .kgp-top{gap:var(--s2);padding:0 var(--s2)}
  .kgp-word{display:none}
  .kgp-main{padding:var(--s3) var(--s2) var(--s5)}
  .kgp-kpis{grid-template-columns:1fr}
  .kgp-filter{gap:var(--s1)}
  .kgp-count{margin-left:0}
}
/* 모션 감소 = 모션 0이 아니다. 위치 이동은 없애되 불투명도·색 전이는 남긴다(상태 변화 이해를 돕는 전이). */
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important}
  .kgp-btn:hover,.kgp-btn:active{transform:none}
  .kgp-toast,.kgp-toast.on{transform:none}
}
</style>
</head>
<body>
<header class="kgp-top">
  <a class="kgp-brand" href="/dashboard/">{{ mark }}<span class="kgp-word">고가브릿지</span></a>
  <nav class="kgp-nav">{{ nav }}</nav>
</header>
<main class="kgp-main">
{{ body }}
</main>
</body>
</html>"""


def _esc(value) -> str:
    """동적 값 HTML 이스케이프.

    v87 STEP1: 화면 body를 Markup으로 표시하므로(오토이스케이프 회피) **시트·쿼리에서 온 값은
    반드시 여기를 거쳐야 한다.** 안 거치면 저장형/반사형 스크립트 주입 경로가 열린다.
    """
    return _html.escape("" if value is None else str(value), quote=True)


def _render(title: str, body: str, description: str = "고가브릿지 관리 대시보드",
            active: str = "") -> str:
    """공용 셸(_BASE_HTML)에 화면 body를 끼워 렌더한다.

    body 계약: 호출자가 동적 값을 전부 `_esc`로 이스케이프한 HTML 문자열을 넘긴다.
    """
    from src.utils.branding import get_brand_name
    from src.utils.build_info import get_build_sha

    return render_template_string(
        _BASE_HTML,
        title=title,
        body=Markup(body),
        description=description,
        brand_name=get_brand_name(),
        build_sha=get_build_sha(),
        mark=Markup(_BRIDGE_MARK),
        nav=Markup(_nav_html(active)),
    )


def _page_head(overline: str, title: str, sub: str) -> str:
    """화면 머리말 — 오버라인(금) + 세리프 오버사이즈 헤드라인 + 본문 대비 부제."""
    return (
        '<div class="kgp-head"><div class="kgp-overline">%s</div>'
        '<h1 class="kgp-h1">%s</h1><p class="kgp-sub">%s</p></div>'
        % (_esc(overline), _esc(title), _esc(sub))
    )


def _empty(title: str, sub: str, action_href: str = "", action_label: str = "") -> str:
    """빈 상태 — 일러스트 없이 세리프 한 줄 + 행동 버튼(무엇이 없고 무엇을 하면 되는지)."""
    btn = ""
    if action_href and action_label:
        btn = '<a class="kgp-btn kgp-btn--ghost" href="%s">%s</a>' % (_esc(action_href), _esc(action_label))
    return ('<div class="kgp-empty"><div class="kgp-empty-t">%s</div>'
            '<div class="kgp-empty-s">%s</div>%s</div>' % (_esc(title), _esc(sub), btn))


# 주문 관리 화면 전용 스코프 스타일(.kgp-oc).
#   v87 STEP1: 여기서 재선언하던 토큰 블록을 삭제하고 _BASE_HTML :root 단일 소스를 상속한다.
#   (STEP2에서 이 스코프 스타일 자체를 공용 컴포넌트 킷으로 흡수 예정.)
_ORDERS_STYLE = """
<style>
.kgp-oc{color:var(--ink)}
.kgp-oc .oc-h{font-family:"Noto Serif KR",serif;font-weight:700;font-size:1.5rem;letter-spacing:-.02em;margin:4px 0 2px}
.kgp-oc .oc-subh{color:var(--muted);font-size:.85rem;margin-bottom:18px}
.kgp-oc .oc-tabs{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-bottom:16px}
.kgp-oc .oc-div{width:1px;height:22px;background:var(--line);margin:0 6px}
.kgp-oc .oc-tab{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:var(--r-pill);
  text-decoration:none;color:var(--ink-soft);font-size:.86rem;font-weight:600;border:1px solid transparent;
  transition:background .18s var(--ease-out),color .18s var(--ease-out)}
.kgp-oc .oc-tab:hover{background:var(--hanji)}
.kgp-oc .oc-tab--active{background:var(--ink);color:var(--hanji)}
.kgp-oc .oc-tab-count{font-size:.75rem;opacity:.7}
.kgp-oc .oc-new{background:var(--teal);color:var(--surface);font-size:.6rem;font-weight:800;letter-spacing:.04em;padding:2px 5px;border-radius:5px}
.kgp-oc .oc-card{background:var(--paper);border:1px solid var(--line);box-shadow:var(--shadow);border-radius:var(--r);padding:16px 18px;margin-bottom:18px}
.kgp-oc .oc-filt{display:flex;flex-wrap:wrap;gap:16px;align-items:center}
.kgp-oc .oc-filt-grp{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.kgp-oc .oc-lbl{font-size:.78rem;color:var(--muted);margin-right:2px}
.kgp-oc .oc-preset{padding:5px 11px;border-radius:var(--r-pill);border:1px solid var(--line);background:var(--surface);
  color:var(--ink-soft);font-size:.8rem;cursor:pointer;transition:transform .12s var(--ease-out),border-color .18s,color .18s}
.kgp-oc .oc-preset:active{transform:scale(.97)}
.kgp-oc .oc-preset--on{border-color:var(--teal);color:var(--teal);background:color-mix(in srgb,var(--teal) 8%,transparent)}
.kgp-oc .oc-chip{display:inline-flex;align-items:center;gap:5px;padding:5px 10px;border-radius:var(--r-pill);border:1px solid var(--line);background:var(--surface);font-size:.8rem;cursor:pointer}
.kgp-oc .oc-chip input{accent-color:var(--teal)}
.kgp-oc .oc-refresh{margin-left:auto;font-size:.76rem;color:var(--muted)}
.kgp-oc .oc-tablewrap{background:var(--surface);border:1px solid var(--line);box-shadow:var(--shadow);border-radius:var(--r);overflow-x:auto}
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
.kgp-oc .oc-badge{display:inline-block;padding:3px 10px;border-radius:var(--r-pill);font-size:.74rem;font-weight:700;white-space:nowrap}
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
.kgp-oc .oc-detail{background:var(--ink);color:var(--hanji);border:0;padding:7px 14px;border-radius:var(--r-pill);font-size:.8rem;font-weight:600;cursor:pointer;white-space:nowrap;transition:transform .12s var(--ease-out)}
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
.kgp-oc-dbtn{display:inline-flex;align-items:center;gap:6px;padding:8px 13px;border-radius:var(--r-pill);border:1px solid var(--teal);
  color:var(--teal);background:var(--surface);text-decoration:none;font-size:.8rem;font-weight:600;transition:transform .12s var(--ease-out),background .15s}
.kgp-oc-dbtn:hover{background:color-mix(in srgb,var(--teal) 8%,transparent)}
.kgp-oc-dbtn:active{transform:scale(.97)}
.kgp-oc-dbtn--off{border-color:var(--line);color:var(--muted);pointer-events:none}
.kgp-oc-dbody{padding:18px 20px;overflow-y:auto;flex:1}
.kgp-oc-sec{margin-bottom:20px}
.kgp-oc-sec h4{font-family:"Noto Serif KR",serif;font-size:.95rem;margin:0 0 8px;color:var(--ink)}
.kgp-oc-row{display:flex;justify-content:space-between;gap:14px;padding:7px 0;border-bottom:1px dashed var(--line);font-size:.85rem}
.kgp-oc-row .k{color:var(--muted)}
.kgp-oc-row .v{color:var(--ink);font-weight:600;text-align:right;word-break:break-all}
/* v87-S2: 소싱처 주문서 붙여넣기 — 여러 줄이라 행이 아니라 블록. 값은 셀러가 그대로 옮긴다. */
.kgp-oc-row.oc-copy{flex-direction:column;align-items:stretch;gap:8px}
.kgp-oc-row.oc-copy .v{text-align:left;font-weight:400;display:flex;flex-direction:column;gap:8px;align-items:flex-start}
.kgp-oc .oc-pre{margin:0;padding:10px 12px;background:var(--hanji);border:1px solid var(--line);
  border-radius:var(--r-sm);font:inherit;font-size:.84rem;line-height:1.55;color:var(--ink);
  white-space:pre-wrap;word-break:break-word;max-height:180px;overflow:auto;width:100%}
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
    // v87-S2: 출처 축 3섹션. '주문서 붙여넣기'는 값이 여러 줄이라 행이 아니라 복사 블록으로 낸다
    //   — 셀러가 소싱처 주문서에 그대로 옮기는 게 이 화면의 실제 작업이다.
    ['수집처','판매마켓','상세'].forEach(function(sec){
      var obj=data[sec]||{}, rowsp='';
      Object.keys(obj).forEach(function(k){
        var v=obj[k]; if(v===''||v==null) return;
        if(k==='주문서 붙여넣기'){
          rowsp+='<div class="kgp-oc-row oc-copy"><span class="k">'+esc(k)+'</span>'
               + '<span class="v"><pre class="oc-pre">'+esc(String(v))+'</pre>'
               + '<button type="button" class="kgp-oc-dbtn" onclick="ocCopy(this)">복사</button></span></div>';
          return;
        }
        rowsp+='<div class="kgp-oc-row"><span class="k">'+esc(k)+'</span><span class="v">'+esc(String(v))+'</span></div>';
      });
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
  window.ocCopy=function(btn){
    var pre=btn.parentElement && btn.parentElement.querySelector('.oc-pre');
    if(!pre) return;
    var done=function(){ btn.textContent='복사됨'; setTimeout(function(){ btn.textContent='복사'; },1600); };
    // 실패를 성공으로 위장하지 않는다 — 클립보드가 막히면 직접 고르라고 알린다(정직 원칙).
    var fail=function(){ btn.textContent='복사 실패'; try{
      var r=document.createRange(); r.selectNodeContents(pre);
      var sel=window.getSelection(); sel.removeAllRanges(); sel.addRange(r);
    }catch(e){} setTimeout(function(){ btn.textContent='복사'; },2400); };
    try{
      if(navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(pre.textContent).then(done, fail); return;
      }
    }catch(e){}
    fail();
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


def _order_sourcing(o: dict) -> dict:
    """v87-S2: 주문 행 → **v56 소싱처 역참조 재사용**(재구현 금지).

    v56 `_order_source_info`는 `items[]` 기반 주문 dict를 받는데 대시보드 행은 평면이라
    **모양만 맞춰** 넘긴다 — 카탈로그(sku→src_url) 역참조와 소싱처 주문서 복사텍스트 조립은
    거기 한 곳에만 둔다(두 벌로 갈라지면 한쪽만 고쳐지고 다른 쪽이 조용히 낡는다).

    실패(모듈 부재·카탈로그 미연결·sku 미매칭)는 **가짜로 채우지 않고** linked=False로 정직 반환 →
    화면이 '원본 미연결'로 표기한다.
    """
    fallback = {"source_url": "", "product_title": "", "copy_text": "", "linked": False, "sourced": False}
    try:
        from src.seller_console.views import _order_source_info
    except Exception:
        return fallback
    opt = o.get("option") or o.get("sku_option") or ""
    shaped = {
        "items": [{
            "sku": str(o.get("sku") or "").strip(),
            "title": str(o.get("title_ko") or o.get("title_original") or "").strip(),
            "qty": o.get("quantity", o.get("qty", 1)) or 1,
            "options": str(opt),
        }],
        "buyer_name_masked": str(o.get("customer_name") or ""),
        "notes": str(o.get("notes") or ""),
    }
    try:
        got = _order_source_info(shaped) or {}
    except Exception:
        return fallback
    # 행에 직접 실린 원본 URL이 있으면 우선(카탈로그가 끊겨도 링크는 살린다).
    if not got.get("source_url"):
        got["source_url"] = o.get("source_url") or o.get("source_link") or ""
        got["linked"] = bool(got["source_url"])
    return got


def _numeric_fx_pairs(fx: dict) -> list:
    """환율 dict에서 **수치로 읽히는 통화쌍만** 추린다.

    공급자 응답에 timestamp 등 비수치 항목이 섞이면 기존 `float(rate)`가 ValueError로 터져
    /dashboard/ 와 /dashboard/fx 가 통째로 500이 났다(게이트 계약 테스트가 실제 공급자를 물면서 드러남).
    표시 계층 방어 — 환율 계산·공급자 로직은 건드리지 않는다.
    """
    pairs = []
    for pair, rate in (fx or {}).items():
        if callable(rate):
            continue
        try:
            pairs.append((pair, float(rate)))
        except (TypeError, ValueError):
            continue
    return pairs


def _get_fx_rates() -> dict:
    try:
        from ..fx.provider import FXProvider
        return FXProvider().get_rates()
    except Exception as exc:
        logger.warning("환율 로드 실패: %s", exc)
        return {}


def _status_badge(status: str) -> str:
    """공통 상태 뱃지 — 성공=청록 / 확인필요=주황 / 실패=적 / 값없음=중립."""
    s = str(status or "").lower()
    if not s:
        return '<span class="kgp-badge kgp-badge--neutral">—</span>'
    if s in ("active", "success", "completed", "shipped"):
        tone = "ok"
    elif s in ("pending", "paid", "in_progress", "processing"):
        tone = "warn"
    else:
        tone = "err"
    return '<span class="kgp-badge kgp-badge--%s">%s</span>' % (tone, _esc(status))


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

    fx_pairs = _numeric_fx_pairs(fx)
    fx_rows = "".join(
        '<tr><td class="kgp-strong">%s</td><td class="num">%s</td></tr>'
        % (_esc(pair), _esc("{:,.4f}".format(rate)))
        for pair, rate in fx_pairs
    )
    if fx_rows:
        fx_block = ('<div class="kgp-tablewrap"><table class="kgp-table">'
                    '<thead><tr><th>통화쌍</th><th class="num">환율</th></tr></thead>'
                    '<tbody>%s</tbody></table></div>' % fx_rows)
    else:
        fx_block = ('<div class="kgp-card">%s</div>'
                    % _empty("환율 데이터가 아직 없어요.",
                             "환율 공급자에 연결되면 여기에 통화쌍별 시세가 표시됩니다.",
                             "/dashboard/fx", "환율·마진 화면으로"))

    quick = "".join(
        '<a class="kgp-btn kgp-btn--ghost" href="%s">%s</a>' % (href, _esc(label))
        for href, label, key in _NAV_ITEMS if key != "index"
    )

    body = (
        _page_head("대시보드", "한눈에 보기", "주문·수집·환율을 한 화면에 모았습니다.")
        + '<div class="kgp-kpis">'
        # 악센트는 청록 하나로 통일(강조 1색/화면). 금은 오버라인, 주황은 키스톤·주 CTA 전용.
        + ('<div class="kgp-card kgp-kpi">'
           '<div class="kgp-kpi-label">전체 주문</div>'
           '<div class="kgp-kpi-value">%s</div>'
           '<div class="kgp-kpi-sub">미처리 %s · 배송 %s · 완료 %s</div></div>'
           % (_esc("{:,}".format(total_orders)), _esc(pending), _esc(shipped), _esc(completed)))
        + ('<div class="kgp-card kgp-kpi">'
           '<div class="kgp-kpi-label">총 매출 (KRW)</div>'
           '<div class="kgp-kpi-value">%s</div>'
           '<div class="kgp-kpi-sub">취소·환불 제외</div></div>'
           % _esc("₩{:,.0f}".format(revenue)))
        + ('<div class="kgp-card kgp-kpi">'
           '<div class="kgp-kpi-label">수집 상품</div>'
           '<div class="kgp-kpi-value">%s</div>'
           '<div class="kgp-kpi-sub">Amazon %s · Taobao %s</div></div>'
           % (_esc("{:,}".format(total_products)), _esc(amazon_count), _esc(taobao_count)))
        + '</div>'
        + '<h2 class="kgp-h2">환율 현황</h2>' + fx_block
        + '<h2 class="kgp-h2">바로 가기</h2><div class="kgp-btnrow">' + quick + '</div>'
        + '<p class="kgp-meta">업데이트: %s</p>' % _esc(_now_iso())
    )
    return _render("대시보드", body, active="index")


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
        "fx": dict(_numeric_fx_pairs(fx)),
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
        translated = ('<span class="kgp-badge kgp-badge--ok">번역 완료</span>' if p.get("title_ko")
                      else '<span class="kgp-badge kgp-badge--neutral">원문</span>')
        rows += (
            '<tr><td class="kgp-strong">%s</td><td>%s</td><td>%s</td>'
            '<td class="num">%s</td><td>%s</td><td>%s</td></tr>'
            % (_esc(sku), _esc(title), _esc(marketplace), _esc(price) or "—",
               translated, _status_badge(p.get("status", "")))
        )
    if rows:
        table = ('<div class="kgp-tablewrap"><table class="kgp-table"><thead><tr>'
                 '<th>SKU</th><th>상품명</th><th>마켓</th><th class="num">가격</th>'
                 '<th>번역</th><th>상태</th></tr></thead><tbody>%s</tbody></table></div>' % rows)
    else:
        table = ('<div class="kgp-card">%s</div>'
                 % _empty("이 조건에 맞는 상품이 없어요.",
                          "필터를 바꾸거나, 수집한 상품이 아직 없다면 먼저 수집해 주세요.",
                          "/dashboard/products", "필터 초기화"))

    def _opt(value, label, current):
        sel = " selected" if current == value else ""
        return '<option value="%s"%s>%s</option>' % (_esc(value), sel, _esc(label))

    body = (
        _page_head("상품", "상품 수집", "수집한 상품을 확인하고 마켓에 올릴 준비를 합니다.")
        + '<div class="kgp-filter">'
        + ('<label class="kgp-field"><span class="kgp-label">마켓</span>'
           '<select class="kgp-select" onchange="location.search=\'?marketplace=\'+this.value">'
           + _opt("", "전체 마켓", marketplace_filter)
           + _opt("amazon", "Amazon", marketplace_filter)
           + _opt("taobao", "Taobao", marketplace_filter)
           + '</select></label>')
        + ('<label class="kgp-field"><span class="kgp-label">번역</span>'
           '<select class="kgp-select" onchange="location.search=\'?translated=\'+this.value">'
           + _opt("", "번역 전체", translation_filter)
           + _opt("yes", "번역 완료", translation_filter)
           + _opt("no", "번역 미완", translation_filter)
           + '</select></label>')
        + ('<div class="kgp-field"><span class="kgp-label">작업</span>'
           '<form action="/dashboard/collect/start" method="post">'
           '<button type="submit" class="kgp-btn kgp-btn--ghost">수집 시작</button></form></div>')
        + '<span class="kgp-count">총 %s개</span>' % _esc("{:,}".format(len(all_products)))
        + '</div>'
        + table
    )
    return _render("상품 수집 관리", body, active="products")


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

    _MARKET_KO = {"coupang": "쿠팡", "naver": "스마트스토어", "smartstore": "스마트스토어",
                  "elevenst": "11번가", "shopify": "Shopify", "woocommerce": "WooCommerce"}

    rows = ""
    for h in history[:200]:
        market = h.get("market", "")
        market_ko = _MARKET_KO.get(str(market).lower(), str(market or "—"))
        rows += (
            '<tr><td class="kgp-strong">%s</td><td>%s</td><td>%s</td>'
            '<td class="num">%s</td><td>%s</td></tr>'
            % (_esc(h.get("sku", "")), _esc(market_ko), _status_badge(h.get("status", "")),
               _esc(h.get("price_krw", "")) or "—", _esc(h.get("uploaded_at", "")) or "—")
        )
    if rows:
        table = ('<div class="kgp-tablewrap"><table class="kgp-table"><thead><tr>'
                 '<th>SKU</th><th>마켓</th><th>상태</th><th class="num">가격(KRW)</th>'
                 '<th>업로드 일시</th></tr></thead><tbody>%s</tbody></table></div>' % rows)
    else:
        table = ('<div class="kgp-card">%s</div>'
                 % _empty("업로드 이력이 아직 없어요.",
                          "상품을 마켓에 올리면 어떤 상품이 어디로 갔는지 여기에 기록됩니다.",
                          "/dashboard/products", "상품 수집으로"))

    def _opt(value, label):
        sel = " selected" if market_filter == value else ""
        return '<option value="%s"%s>%s</option>' % (_esc(value), sel, _esc(label))

    body = (
        _page_head("업로드", "업로드 이력", "어떤 상품이 어느 마켓에 올라갔는지 기록합니다.")
        + '<div class="kgp-filter">'
        + ('<label class="kgp-field"><span class="kgp-label">마켓</span>'
           '<select class="kgp-select" onchange="location.search=\'?market=\'+this.value">'
           + _opt("", "전체") + _opt("coupang", "쿠팡") + _opt("naver", "스마트스토어")
           + '</select></label>')
        + ('<div class="kgp-field"><span class="kgp-label">일괄 업로드</span>'
           '<div class="kgp-btnrow">'
           '<form action="/dashboard/upload/run" method="post">'
           '<input type="hidden" name="market" value="coupang">'
           '<button type="submit" class="kgp-btn kgp-btn--ghost">쿠팡으로 올리기</button></form>'
           '<form action="/dashboard/upload/run" method="post">'
           '<input type="hidden" name="market" value="naver">'
           '<button type="submit" class="kgp-btn kgp-btn--ghost">스마트스토어로 올리기</button></form>'
           '</div></div>')
        + '<span class="kgp-count">총 %s개</span>' % _esc("{:,}".format(len(history)))
        + '</div>'
        + table
    )
    return _render("업로드 관리", body, active="uploads")


@web_ui_bp.get("/orders")
def orders():
    """주문 현황 목록."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    # v82 STEP5: 주문 관리 화면 리모델(표면 계층만 — 라우트·데이터 구조·JSON 응답 불변).
    #   상태 탭바 + 필터 카드(기간/마켓/갱신시각) + 리모델 테이블(링크 아이콘·상세 버튼) + 상세 드로어.
    #   gogabridj 토큰(스코프 CSS 변수)·Noto Serif KR 헤드라인·상태뱃지 공통·drawer 우측 슬라이드.
    import json as _json
    from collections import Counter

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
        # v87-S2: 드로어를 **출처 축 3섹션**으로 재편([수집처][판매마켓][상세]).
        #   종전(#549)은 주문정보/상품정보/배송정보 = 정보 유형 축이었다. 구매대행은 "이 주문을 어디서
        #   사서 어디에 팔았나"가 작업 단위라, 셀러가 실제로 오가는 두 축(수집처↔판매마켓)을 먼저 세운다.
        src = _order_sourcing(o)
        if src.get("source_url") and not src_url:
            src_url = src["source_url"]
        drawer = {
            "수집처": {
                "원본 상품": src.get("product_title") or str(title),
                "원본 주소": src.get("source_url") or "",
                "소싱 상태": "소싱완료" if src.get("sourced") else ("연결됨" if src.get("linked") else "원본 미연결"),
                # 소싱처 주문서에 그대로 붙여넣는 텍스트(v56 조립본). 없으면 빈 문자열 — 지어내지 않는다.
                "주문서 붙여넣기": src.get("copy_text") or "",
            },
            "판매마켓": {
                "마켓": market, "주문번호": str(onum), "주문ID": str(oid),
                "상태": _status_ko(status), "주문시간": _fmt_dt(order_dt),
                "판매가": _fmt_price(o.get("sell_price_krw", "")),
                "마켓 주문 주소": mkt_url or "",
            },
            "상세": {
                "상품명": str(title), "옵션": str(option), "SKU": str(sku), "수량": str(qty),
                "원가": _fmt_price(o.get("buy_price", o.get("price_original", ""))),
                "마진": ("%s%%" % o.get("margin_pct")) if o.get("margin_pct") not in (None, "") else "",
                "주문자": str(customer),
                # 통관고유부호 — 개인정보라 /dashboard/* 인증 게이트(S1.5) 뒤에서만 렌더된다.
                "개인통관고유부호(PCC)": o.get("pcc") or o.get("personal_customs_code") or "",
                "국가": o.get("country") or "",
                "송장번호": o.get("tracking_no") or o.get("tracking") or "",
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
    # 동적 값은 전부 _html.escape 완료 — _render의 body 계약(호출자가 이스케이프 책임)을 만족한다.
    return _render("주문 관리", body, active="orders")


@web_ui_bp.get("/fx")
def fx_view():
    """환율 현황 + 마진 계산기."""
    disabled = _check_enabled()
    if disabled:
        return disabled

    fx = _get_fx_rates()
    fx_pairs = _numeric_fx_pairs(fx)

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
                '<div class="kgp-card kgp-kpi" style="max-width:420px;margin-top:var(--s3)">'
                '<div class="kgp-kpi-label">계산 결과</div>'
                '<div class="kgp-kpi-value">%s</div>'
                '<div class="kgp-kpi-sub">판매가 · 목표 마진 %s%%</div>'
                '<div class="kgp-note" style="margin-top:var(--s2)">'
                '매입가 %s &nbsp;·&nbsp; 마진 금액 %s</div></div>'
                % (_esc("₩{:,.0f}".format(sell_krw)), _esc(margin_pct),
                   _esc("₩{:,.0f}".format(buy_krw)), _esc("₩{:,.0f}".format(sell_krw - buy_krw)))
            )
        except (ValueError, TypeError, ZeroDivisionError):
            calc_result = ('<div class="kgp-card" style="max-width:420px;margin-top:var(--s3)">'
                           '<div class="kgp-note" style="border-left-color:var(--red)">'
                           '입력값을 확인하세요. 매입가와 마진은 숫자로, 마진은 100 미만이어야 합니다.'
                           '</div></div>')

    rate_rows = "".join(
        '<tr><td class="kgp-strong">%s</td><td class="num">%s</td></tr>'
        % (_esc(pair), _esc("{:,.4f}".format(rate)))
        for pair, rate in fx_pairs
    )
    if rate_rows:
        rates_block = ('<div class="kgp-tablewrap" style="max-width:420px">'
                       '<table class="kgp-table"><thead><tr>'
                       '<th>통화쌍</th><th class="num">환율</th></tr></thead>'
                       '<tbody>%s</tbody></table></div>' % rate_rows)
    else:
        rates_block = ('<div class="kgp-card" style="max-width:420px">%s</div>'
                       % _empty("환율 데이터가 아직 없어요.",
                                "환율 공급자에 연결되면 통화쌍별 시세가 표시됩니다."))

    def _copt(value):
        sel = " selected" if currency == value else ""
        return '<option value="%s"%s>%s</option>' % (value, sel, value)

    body = (
        _page_head("환율", "환율·마진", "오늘 환율로 판매가를 계산합니다.")
        + '<h2 class="kgp-h2" style="margin-top:0">환율 현황</h2>' + rates_block
        + '<h2 class="kgp-h2">마진 계산기</h2>'
        + '<form method="get"><div class="kgp-filter">'
        + ('<label class="kgp-field"><span class="kgp-label">매입가</span>'
           '<input class="kgp-input" type="text" name="buy_price" value="%s" placeholder="예: 100.00"></label>'
           % _esc(buy_price))
        + ('<label class="kgp-field"><span class="kgp-label">통화</span>'
           '<select class="kgp-select" name="currency">%s</select></label>'
           % "".join(_copt(c) for c in ("USD", "JPY", "CNY", "EUR")))
        + ('<label class="kgp-field"><span class="kgp-label">목표 마진(%%)</span>'
           '<input class="kgp-input" type="text" name="margin_pct" value="%s" placeholder="예: 20"></label>'
           % _esc(margin_pct))
        + '<div class="kgp-field"><button type="submit" class="kgp-btn kgp-btn--primary">계산</button></div>'
        + '</div></form>'
        + calc_result
        + '<p class="kgp-meta">업데이트: %s</p>' % _esc(_now_iso())
    )
    return _render("환율·마진 계산기", body, active="fx")


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
