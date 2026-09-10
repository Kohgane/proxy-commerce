"""tests/test_v40s6i_sourcing.py — 디자인 v3 Stage 6-i: AI 소싱 허브.

수리 전 실측: 1920×940에서 **1368px**(428 초과) · v2 `.card` 6 / `op-card` 0 · 잔재 99.

그런데 본론은 높이가 아니었다. **화면이 자기 순서를 거꾸로 놓고 있었다** —
부제가 "키워드 → 국내에서 뭐가 팔리나 → 소싱처 찾기 → 수집·등록"이라고 선언해 놓고,
정작 맨 위 세 장이 전부 **마지막 단계(수집 경로)**였고 첫 단계(키워드)는 네 번째 카드,
스크롤 아래에 있었다. 세로로만 쌓으면 순서가 뒤집혀도 눈에 안 띈다.

수리 후: 0건 888 · 실데이터 908 (뷰포트 940, 여유 32~52). 내부 스크롤은 **열마다 하나, 둘**.
※ 840은 오너 지시 치수(검색창 54px·타일 280px/1.12rem)를 되돌리기 **전** 값이라 폐기한다 —
  낡은 실측치를 문서에 남겨 두면 다음 사람이 그 숫자를 기준으로 판단한다.
"""
from __future__ import annotations

import glob
import os
import re
import tempfile
from pathlib import Path

import pytest

TPL = Path("src/seller_console/templates/sourcing.html")
CSS = Path("src/static/app.css")
VIEWPORT = (1920, 940)


def _body(p: Path = TPL) -> str:
    """주석만 지운다. **`<script>`는 안 지운다** — 지웠더니 계약이 그린인데 화면은 v2를 그렸다.

    지울 것과 안 지울 것의 기준은 '노이즈인가'가 아니라 **'사용자가 보게 되는가'**다.
    주석은 화면에 안 나오지만 JS 문자열은 **화면이 된다**([[계약이 script를 지우고 검사한다]]).
    """
    s = p.read_text(encoding="utf-8")
    return re.sub(r"\{#.*?#\}|<!--.*?-->", "", s, flags=re.S)


def _slice_css() -> str:
    """6-i 슬라이스만(주석 제외 — 내가 쓴 설명문이 내 계약을 통과시키면 안 된다)."""
    block = CSS.read_text(encoding="utf-8").split("Stage 6-i: AI 소싱 허브")[1]
    return re.sub(r"/\*.*?\*/", "", block, flags=re.S)


# ── 순서: 화면이 선언한 대로 흐르나 ──────────────────────────────────────────
def test_the_first_step_comes_first():
    """★ 이 슬라이스의 본론 — 키워드 검색이 **수집 경로보다 앞**에 온다.

    수리 전에는 URL 수집·확장·등록소가 먼저 나오고 키워드가 네 번째였다. 화면이 스스로 적어 둔
    순서(부제)와 정반대다. 세로로 쌓으면 그 모순이 안 보이는데, 좌/우로 가르면 바로 드러난다.
    """
    # 구획 표시가 HTML 주석이라 여기선 **원문**을 본다(`_body`는 주석을 지운다 — 그게 이 스캐너의 함정이었다).
    b = TPL.read_text(encoding="utf-8")
    assert b.index('id="keywordInput"') < b.index('id="quickCollectUrl"'), "키워드가 수집 경로 뒤에 있다"
    # 검색은 **머리**에 있다(좌열 카드가 아니라) — 첫 단계이자 화면에서 제일 넓어야 할 것.
    head = b[b.index('class="ch-head si-head"'):b.index("<!-- ── 좌")]
    assert 'id="keywordInput"' in head


def test_left_is_means_right_is_results():
    """좌 = 수단(담는 법·소싱처) / 우 = 결과(팔리는 것). 5-f·6-h 문법 승계."""
    b = TPL.read_text(encoding="utf-8")
    left = b[b.index("<!-- ── 좌"):b.index("<!-- ── 우")]
    right = b[b.index("<!-- ── 우"):]
    assert 'id="quickCollectUrl"' in left and 'id="registryDomainInput"' in left
    assert "국내에서 팔리는 상품" in right and "추천 후보" in right
    assert "국내에서 팔리는 상품" not in left


# ── 합격 기준: 한 화면 ───────────────────────────────────────────────────────
def _pw_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    if glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"):
        return True
    cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or (Path.home() / ".cache" / "ms-playwright"))
    return cache.is_dir() and any(cache.glob("chromium-*"))


# 부트스트랩은 앱이 CDN으로 싣는 **실제 스타일시트**다. 없이 재면 다른 화면을 재는 것이고,
# 그 숫자로 "한 화면에 들어간다"를 말할 수 없다(6-h CI 실측: 없으면 940 대신 1161).
_BS = next((p for p in ("node_modules/bootstrap/dist/css/bootstrap.min.css",
                        "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css")
            if Path(p).exists()), None)
CSS_FILES = tuple(x for x in (_BS, "src/static/app.css", "src/seller_console/static/seller.css",
                              "src/seller_console/static/console.css") if x)

PROBE = """() => {
  // scrollHeight는 뷰포트보다 작아지지 않는다(clamp) — '넘쳤나'만 알려주고 **여유는 못 보여준다.**
  //   여유를 재려면 콘텐츠의 실제 바닥을 본다(6-h에서 이걸 몰라 로컬 940 정확을 CI가 깼다).
  const main = document.querySelector('main').getBoundingClientRect();
  const sc = [];
  document.querySelectorAll('.si-page, .si-page *').forEach(function (e) {
    const s = getComputedStyle(e);
    if (/(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 4)
      sc.push((e.className || '').toString().slice(0, 30));
  });
  return {contentBottom: Math.round(main.bottom), vh: window.innerHeight,
          overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          scrollers: sc,
          v2cards: document.querySelectorAll('.card').length,
          opcards: document.querySelectorAll('.op-card').length};
}"""

_SRC = [{"domain": f"brand{i}.com", "label": f"브랜드몰 {i}", "openness_status": o, "adapter_name": a,
         "created_at": "2026-08-11",
         "diag": {"fields": {"title": True, "price": i % 2 == 0, "image": True,
                             "options": False, "description": i % 3 == 0}, "core3_ok": i % 2 == 0}}
        for i, (o, a) in enumerate([("open", "generic_og"), ("partial", "generic_og"),
                                    ("restricted", "generic_og"), ("open", "large_platform"),
                                    ("partial", "generic_og"), ("open", "generic_og")])]
_PROD = [{"title": f"요가 레깅스 하이웨스트 {i}단 스판 운동복 세트", "price": 19800 + i * 3300,
          "mall": "네이버쇼핑", "link": "https://example.com/p", "image": ""} for i in range(6)]
_REC = [{"title": f"추천 후보 {i}", "source": "keyword-trend", "reason": "검색 상승",
         "margin_hint": "예상 마진 32%", "cta_href": "/seller/collect", "cta_label": "수집하기",
         "secondary_href": "/seller/keywords", "secondary_label": "키워드 보기"} for i in range(3)]


def _render(*, data: bool):
    from flask import render_template

    from src.order_webhook import app
    from src.seller_console import views as V
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    app.jinja_env.cache.clear()
    kw = "요가 레깅스" if data else ""
    kc = ({"rows": [{"keyword": f"요가 레깅스 {i}", "search_volume": 12000 - i * 1700} for i in range(5)],
           "query_text": kw} if data else {})
    src, prod, rec = (_SRC, _PROD, _REC) if data else ([], [], [])
    with app.test_request_context("/seller/sourcing"):
        html = render_template(
            "sourcing.html", page="sourcing", keyword=kw, period="30d",
            period_options=V._KEYWORD_PERIOD_LABELS, keyword_context=kc, recommendations=rec,
            my_sources=src, registry_sources=src, domestic_products=prod, domestic_enabled=data,
            sourcing_search_links=V._sourcing_search_links(kw),
            amazon_search_countries=V._AMAZON_SEARCH_COUNTRIES,
            analysis=V._build_sourcing_analysis(prod, kc, kw, domestic_total=8421 if data else None),
            collect_url="", notice="", admin_ok=False)
    style = "".join(f"<style>{Path(p).read_text(encoding='utf-8')}</style>"
                    for p in CSS_FILES if Path(p).exists())
    return html.replace("</head>", style + "</head>", 1)


def _measure(*, data: bool, width: int = VIEWPORT[0], height: int = VIEWPORT[1]):
    from playwright.sync_api import sync_playwright
    exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome") or [None])[0]
    tmp = Path(tempfile.gettempdir()) / f"kgp6i_{int(data)}_{width}.html"
    tmp.write_text(_render(data=data), encoding="utf-8")
    with sync_playwright() as pw:
        br = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = br.new_page(viewport={"width": width, "height": height})
        pg.set_default_timeout(15000)
        pg.route("**/*", lambda r: (r.continue_() if r.request.url.startswith("file://") else r.abort()))
        pg.goto(tmp.as_uri(), wait_until="domcontentloaded")
        pg.wait_for_timeout(400)
        r = pg.evaluate(PROBE)
        br.close()
    return r


@pytest.mark.skipif(not _pw_ok(), reason="크로미움 없음 — 정직하게 skip")
@pytest.mark.parametrize("data,label", [(False, "0건"), (True, "실데이터")])
def test_fits_one_viewport(data, label):
    """★ 1920×940에 들어간다. 데이터가 붙어도 넘치지 않는다(내부 스크롤이 흡수).

    부트스트랩이 없으면 **다른 화면을 재는 것**이라 그 숫자는 근거가 못 된다 —
    조용히 통과시키지 않고 부재 자체를 실패로 만든다([[CI에 없는 CSS는 다른 화면을 잰다]]).
    """
    assert _BS, "부트스트랩 CSS 없음 — 라이브와 다른 화면을 재게 된다(CI 설치 누수)"
    m = _measure(data=data)
    assert m["contentBottom"] <= m["vh"] - 20, f"[{label}] 콘텐츠 바닥 {m['contentBottom']} > 여유선"
    assert m["overflowX"] == 0, f"[{label}] 가로 스크롤 {m['overflowX']}px"


@pytest.mark.skipif(not _pw_ok(), reason="크로미움 없음 — 정직하게 skip")
def test_exactly_two_inner_scrollers_one_per_column():
    """★ 내부 스크롤은 **열마다 하나, 둘**(6-h가 세운 규율 승계).

    카드마다 상한을 걸었더니 스크롤이 셋이 됐고, 카드가 제 몸을 줄여 내용을 못 보여 줬다(실측).
    카드 몸통에 걸었더니 등록 입력창 한가운데가 잘렸다(캡처 실측). 열이 스크롤하는 게 답이었다.
    """
    assert _BS, "부트스트랩 CSS 없음"
    m = _measure(data=True)
    assert len(m["scrollers"]) == 2, f"내부 스크롤 {len(m['scrollers'])}곳: {m['scrollers']}"
    assert all("si-col" in c for c in m["scrollers"]), f"열이 아닌 것이 스크롤한다: {m['scrollers']}"


@pytest.mark.skipif(not _pw_ok(), reason="크로미움 없음 — 정직하게 skip")
def test_mobile_390_has_no_horizontal_scroll_and_no_column_scroll():
    """모바일에선 **열 스크롤을 푼다** — 페이지가 스크롤하는 게 정상이고, 열 안에 갇히면 더 못 본다."""
    assert _BS, "부트스트랩 CSS 없음"
    m = _measure(data=True, width=390, height=844)
    assert m["overflowX"] == 0, f"가로 스크롤 {m['overflowX']}px"
    assert not m["scrollers"], f"모바일에서 열이 갇혔다: {m['scrollers']}"


@pytest.mark.skipif(not _pw_ok(), reason="크로미움 없음 — 정직하게 skip")
def test_v2_card_grammar_is_gone():
    """v2 `.card` 0 / `op-card`만. 문법이 반만 바뀌면 두 문법이 한 화면에 공존한다."""
    assert _BS, "부트스트랩 CSS 없음"
    m = _measure(data=True)
    assert m["v2cards"] == 0, f"v2 카드 {m['v2cards']}장 잔존"
    assert m["opcards"] >= 3


# ── 잔재·규칙 ────────────────────────────────────────────────────────────────
def test_bootstrap_color_utilities_are_gone():
    """부트스트랩 컬러 유틸은 우리 팔레트 밖이다 — 상태색은 `pc-badge` 변형이 진다."""
    b = _body()
    for pat in ("text-bg-", "alert alert-", "btn-outline-secondary", "btn-outline-success",
                "btn-outline-primary", "btn-outline-danger", "bg-warning", "bg-danger", "bg-light"):
        assert pat not in b, f"v2 잔재: {pat}"


def test_no_new_badge_names_invented():
    """★ 넷째를 만들지 않았다(6-g 교훈) — 상태 뱃지는 **기존 `pc-badge` 변형**만 쓴다."""
    b = _body()
    # 기본 클래스(`pc-badge`)와 변형(`pc-badge-x`)만 인정한다. 예전 정규식은
    #   `class="pc-badge pc-badge-on"`에서 가운데 `pc`를 변형으로 잡았다(스캐너 자해).
    used = set(re.findall(r"\bpc-badge(?:-(\w+))?\b", b))
    assert used <= {"", "on", "off", "danger", "muted"}, f"새 뱃지 이름: {used}"
    assert "pc-badge-on" in b and "pc-badge-danger" in b


def test_no_hardcoded_hex_or_px_inline():
    """토큰 단일 소스 — 인라인 하드코딩 0. 수리 전 실측 15개(px/hex)."""
    bad = [x for x in re.findall(r'style="([^"]*)"', _body())
           if re.search(r"#[0-9a-fA-F]{3,6}|\d+px", x)]
    assert not bad, f"인라인 하드코딩 잔존: {bad[:3]}"
    assert "<style" not in _body(), "스타일 블록이 되살아났다"


def test_one_orange_cta_on_screen():
    """★ 주황은 화면당 하나다. 타일마다 주황을 달면 N개가 되어 **강조가 강조를 죽인다**.

    실측(캡처): 타일 CTA가 `btn-cta`라 국내 상품 3장 + 검색 = 주황 4개가 동시에 보였다.
    타일의 주 행동은 청록으로 내리고, 주황은 이 화면의 첫 행동(키워드 검색) 하나만 쓴다.
    """
    b = _body()
    assert b.count("btn-cta") == 1, f"주황 CTA {b.count('btn-cta')}개 — 화면당 하나"
    assert "AI 상품 추천받기" in b[b.index("btn-cta"):b.index("btn-cta") + 400]


def test_table_grammar_and_numeric_rule_not_copied_here():
    """★ 규칙을 슬라이스에 **복사하지 않는다** — 6-h-3에서 자릿수를 복사했다가 단일 소스를 깼다."""
    css = _slice_css()
    assert "tabular-nums" not in css and "text-overflow: ellipsis" not in css


def test_js_hooks_survive_the_rewrite():
    """★ 로직 변경 0 — JS가 잡는 자리(id·class·form action)는 하나도 안 바뀌었다."""
    b = TPL.read_text(encoding="utf-8")
    for hook in ('id="quickCollectBtn"', 'id="quickCollectUrl"', 'id="quickCollectResult"',
                 'id="registryDomainInput"', 'id="registryLabelInput"', 'id="registrySubmitBtn"',
                 'id="registrySearchInput"', 'id="registryList"', 'id="keywordInput"',
                 "registry-item", "registry-detail-btn", "registry-recollect-btn",
                 "registry-diag-btn", "registry-detail", 'action="/seller/sourcing/my-sources"'):
        assert hook in b, f"JS 훅 소실: {hook}"


def test_nothing_was_deleted_only_moved():
    """★ 없앤 정보 0 — 자리만 바꿨다. 옮긴 문장이 **어디에 살아 있는지**를 못 박는다.

    행선지: 화면 설명 3문단 → 머리 부제의 접힘(부제 한 줄이 이미 있던 자리라 높이 0원) ·
            소싱처 등록소 → 수집 경로 카드 안(둘 다 "어떻게 담나"다) ·
            소싱 분석 6칸 카드 → 한 줄 스트립 · 키워드 스냅샷 카드 → 추천 카드 각주.
    """
    b = _body()
    for kept in ("URL 붙여넣기", "크롬 확장", "북마클릿", "소싱처", "국내에서 팔리는 상품",
                 "추천 후보", "키워드 스냅샷", "소싱 분석", "가짜 수치는 표시하지 않습니다",
                 "자가진단", "수동 보완 필요", "아마존에서 검색"):
        assert kept in b, f"문장 소실: {kept}"
    # 등록소가 다른 화면으로 도망가지 않았다 — `/sourcing/my-sources` GET은 **이 화면으로 되돌리는
    #   리다이렉트**라, 여기가 그 목록의 유일한 집이다(실측). 그래서 줄이지 않고 담는다.
    assert 'id="registryList"' in b


def test_empty_state_has_one_call_to_action():
    """★ 0건인데 강조가 둘이었다(6-g에서 잡은 그 유형) — 등록 폼 버튼과 빈 상태 CTA가 같은 곳으로 갔다."""
    b = _body()
    empty = b[b.index("op-empty"):b.index("op-empty") + 400]
    assert "소싱처 등록 시작" not in empty, "같은 곳으로 가는 두 번째 CTA가 남았다"
    assert "btn" not in empty, "빈 상태가 또 버튼을 들었다"
