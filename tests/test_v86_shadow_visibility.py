"""tests/test_v86_shadow_visibility.py — v86 STEP1: 가시성 계약(실브라우저).

오너 실측 확정: FAB는 fixed/top/right로 **존재**하는데 화면엔 안 보였다. 원인은 `all:initial !important`를
인라인에 걸면 Chrome이 250여 롱핸드로 전개해 배경·크기까지 초기화하고, 인라인 !important라 우리 시트로
복원이 원천 봉쇄되기 때문이다(width/height/transform initial 실측).

기존 계약(v84)은 `position==fixed`만 봐서 이 상태를 **전부 통과**시켰다. 그래서 "위치는 맞는데 안 보이는"
층을 따로 못박는다. 계약 3종:
  (1) shadow 내부 버튼의 computed background-color != transparent  ← 배경 초기화 감지
  (2) offsetWidth >= 40 (및 높이 >= 20)                            ← 크기 초기화 감지
  (3) 뷰포트 우측 절반 좌표                                          ← 위치 회귀 감지

추가로 **인위 회귀 검증**을 같은 실행 안에서 한다(가짜 게이트 방지): 배경 선언을 제거한 코드로 같은 페이지를
띄워 계약 (1)이 실제로 **실패**하는지 확인한다. 계약이 실패할 수 없으면 그 게이트는 의미가 없다.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

EXT = Path("extensions/chrome-collector")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))

# 사이트가 공격적인 전역 CSS를 걸어도 shadow 경계가 막아야 한다(격리 검증 포함).
PAGE_HTML = (
    "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>t</title>"
    "<style>*{background:none !important;border:0 !important;font-size:0 !important;"
    "width:auto !important;height:auto !important}</style></head>"
    "<body><h1 class='item_name'>테스트 상품</h1><div class='item_price'>3,980円</div></body></html>"
)

CHROME_STUB = """
  window.chrome = {
    runtime: { id: 'x', lastError: null, getManifest: () => ({version:'0'}), getURL: (p)=>p,
               sendMessage: (m,cb)=>{ cb && setTimeout(()=>cb({ok:false}),0); }, onMessage:{addListener(){}} },
    storage: { local: { get:(k,cb)=>cb&&cb({}), set:()=>{} }, sync:{ get:(k,cb)=>cb&&cb({}) },
               onChanged:{ addListener(){} } },
  };
"""

PROBE_JS = """() => {
    const host = document.getElementById('kgp-collect-fab');
    if (!host) return { exists: false };
    const hs = getComputedStyle(host);
    const hr = host.getBoundingClientRect();
    const inner = host.shadowRoot ? host.shadowRoot.querySelector('.w') : null;
    const is = inner ? getComputedStyle(inner) : null;
    return {
      exists: true,
      hasShadow: !!host.shadowRoot,
      hostPosition: hs.position,
      innerBg: is ? is.backgroundColor : '',
      innerW: inner ? inner.offsetWidth : 0,
      innerH: inner ? inner.offsetHeight : 0,
      innerVisibility: is ? is.visibility : '',
      innerOpacity: is ? is.opacity : '',
      hostLeft: hr.left,
    };
}"""


def _pw_ok():
    """chromium을 실제로 띄울 수 있는지 — 경로 추측이 아니라 playwright에게 직접 묻는다.

    v86 STEP2: 옛 구현은 `/opt/pw-browsers`(CI)와 `~/.cache/ms-playwright`(리눅스 기본)만 봐서
    **윈도우 기본 설치 위치(`%LOCALAPPDATA%\\ms-playwright`)를 못 찾고 조용히 스킵**했다.
    실브라우저 계약이 유일한 게이트인데 스킵되면 '그린'이 공허해지므로, 설치 여부는
    `chromium.executable_path` 실존으로 판정한다(OS·PLAYWRIGHT_BROWSERS_PATH 전부 커버).
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    if glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"):
        return True
    try:
        with sync_playwright() as pw:
            return Path(pw.chromium.executable_path).exists()
    except Exception:
        return False


# 게이트를 '스킵으로 통과'시키지 않기 위한 안전장치 — CI/릴리스에서 이 값을 켜면
# 브라우저 미설치는 스킵이 아니라 **실패**가 된다(공허한 그린 방지).
_REQUIRE_BROWSER = os.getenv("KGP_REQUIRE_BROWSER", "") == "1"


def test_browser_gate_is_live_when_required():
    """KGP_REQUIRE_BROWSER=1이면 실브라우저 계약이 반드시 실행 가능해야 한다."""
    if not _REQUIRE_BROWSER:
        pytest.skip("KGP_REQUIRE_BROWSER=1 일 때만 강제")
    assert _pw_ok(), "실브라우저 계약이 스킵된다 — chromium 미설치. 그린을 인정하지 말 것."


def _isolated_code() -> str:
    scripts = [
        j
        for cs in MANIFEST["content_scripts"]
        if (cs.get("world") or "ISOLATED") == "ISOLATED"
        for j in cs["js"]
    ]
    return ";\n".join((EXT / s).read_text(encoding="utf-8") for s in scripts)


def _measure(code: str) -> dict:
    """주어진 content_script 코드로 페이지를 띄우고 FAB 가시성 지표를 실측한다."""
    from playwright.sync_api import sync_playwright

    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    opts = {"executable_path": hits[0]} if hits else {}
    proxy = os.environ.get("HTTPS_PROXY")
    if proxy:
        opts["proxy"] = {"server": proxy, "bypass": "127.0.0.1,localhost"}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**opts)
        page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
        page.route(
            "**/*",
            lambda route: (
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=PAGE_HTML)
                if route.request.url.startswith("https://item.rakuten.co.jp/")
                else route.abort()
            ),
        )
        page.goto("https://item.rakuten.co.jp/x/y/", wait_until="domcontentloaded")
        page.evaluate(CHROME_STUB)
        page.evaluate(code)
        page.wait_for_timeout(300)
        got = page.evaluate(PROBE_JS)
        browser.close()
    return got


TRANSPARENT = ("", "rgba(0, 0, 0, 0)", "transparent")


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_fab_visible_three_contracts():
    got = _measure(_isolated_code())
    assert got["exists"], "FAB 미주입 — 화면에 수집 버튼이 없다"
    assert got["hasShadow"], "shadow 호스트가 아니다(all:initial 라이트 DOM 경로 잔존)"
    assert got["hostPosition"] == "fixed", got
    # (1) 배경 — all:initial 전개로 초기화되면 여기서 잡힌다.
    assert got["innerBg"] not in TRANSPARENT, ("배경이 투명 — 비가시", got)
    # (2) 크기 — 사이트의 width/height !important 전역 규칙에도 shadow 안은 살아 있어야 한다.
    assert got["innerW"] >= 40, ("너비 초기화 — 비가시", got)
    assert got["innerH"] >= 20, ("높이 초기화 — 비가시", got)
    assert got["innerVisibility"] != "hidden", got
    assert float(got["innerOpacity"] or "1") > 0, got
    # (3) 위치 — 뷰포트 우측 절반.
    assert got["hostLeft"] > 640, ("우측 절반에 있어야 한다", got)


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_visibility_contract_actually_fails_on_regression():
    """인위 회귀 — 배경 선언을 제거하면 계약 (1)이 **실패해야** 한다.

    실패할 수 없는 계약은 게이트가 아니다(가짜 그린 방지). v84에서 CI 브랜치로 증명했던 절차를
    같은 실행 안으로 들여와 상시 자동화한다.
    """
    code = _isolated_code()
    broken = code.replace("background:#1a1714;", "")
    assert broken != code, "회귀 주입 실패 — FAB shadow CSS의 배경 선언을 찾지 못했다"
    got = _measure(broken)
    assert got["exists"] and got["hasShadow"], got
    assert got["innerBg"] in TRANSPARENT, ("배경을 지웠는데도 투명이 아니다 = 계약이 회귀를 못 잡는다", got)


# ── v86 STEP2: 벌크바(리스팅) 가시성 + all:initial 잔존 0 ──────────────────────
#   STEP1은 FAB만 Shadow로 옮겼다. 타일 호버 버튼·벌크바·뱃지는 여전히 `_KGP_RESET`(all:initial 인라인)을
#   써서 같은 유령이 재발할 수 있는 표면으로 남아 있었다 → 전부 Shadow로 이전하고 계약으로 못박는다.

_IMG = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'>"
    "<rect width='240' height='240' fill='%23ccc'/></svg>"
)
_CARD = (
    # href는 _kgpIsProductHref가 인정하는 상품 상세 패턴(/item/<숫자>/)이어야 타일로 채택된다.
    "<div class='item'><a href='https://item.rakuten.co.jp/shop/item/1000{n}/'>"
    "<img src=\"" + _IMG + "\" width='240' height='240'>"
    "<span class='name'>상품 {n}</span><span class='price'>3,980円</span></a></div>"
)
LISTING_HTML = (
    "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>list</title>"
    # 사이트가 전역으로 때리는 공격적 규칙 — shadow 경계가 막아야 한다.
    "<style>*{background:none !important;border:0 !important;font-size:0 !important}"
    "button{all:unset !important}</style></head><body>"
    + "".join(_CARD.replace("{n}", str(i)) for i in range(1, 7))
    + "</body></html>"
)

TOOLBAR_PROBE = """() => {
    const host = document.getElementById('kgp-listing-toolbar');
    if (!host) return { exists: false };
    const hs = getComputedStyle(host);
    const root = host.shadowRoot;
    const bar = root ? root.querySelector('.bar') : null;
    const bs = bar ? getComputedStyle(bar) : null;
    const btn = root ? root.querySelector('.kgp-tb-btn[data-act="collect-all"]') : null;
    const bts = btn ? getComputedStyle(btn) : null;
    return {
      exists: true,
      hasShadow: !!root,
      hostPosition: hs.position,
      barBg: bs ? bs.backgroundColor : '',
      barW: bar ? bar.offsetWidth : 0,
      barH: bar ? bar.offsetHeight : 0,
      btnBg: bts ? bts.backgroundColor : '',
      btnW: btn ? btn.offsetWidth : 0,
      btnColor: bts ? bts.color : '',
    };
}"""


def _measure_listing(code: str, probe: str = TOOLBAR_PROBE) -> dict:
    """카드가 있는 목록 페이지를 띄워 벌크바 지표를 실측한다."""
    from playwright.sync_api import sync_playwright

    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    opts = {"executable_path": hits[0]} if hits else {}
    proxy = os.environ.get("HTTPS_PROXY")
    if proxy:
        opts["proxy"] = {"server": proxy, "bypass": "127.0.0.1,localhost"}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**opts)
        page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
        page.route(
            "**/*",
            lambda route: (
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=LISTING_HTML)
                if route.request.url.startswith("https://item.rakuten.co.jp/")
                else route.abort()
            ),
        )
        page.goto("https://item.rakuten.co.jp/list/", wait_until="domcontentloaded")
        page.evaluate(CHROME_STUB)
        page.evaluate(code)
        page.wait_for_timeout(600)
        got = page.evaluate(probe)
        browser.close()
    return got


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_bulkbar_visible_contracts():
    """벌크바 = shadow + 배경 살아있음 + 크기 살아있음(사이트 전역 규칙에도)."""
    got = _measure_listing(_isolated_code())
    assert got["exists"], "벌크바 미주입 — 목록 페이지에서 바가 없다"
    assert got["hasShadow"], "벌크바가 shadow 호스트가 아니다(all:initial 인라인 경로 잔존)"
    assert got["hostPosition"] == "fixed", got
    assert got["barBg"] not in TRANSPARENT, ("바 배경이 투명 — 비가시", got)
    assert got["barW"] >= 40, ("바 너비 초기화 — 비가시", got)
    assert got["barH"] >= 20, ("바 높이 초기화 — 비가시", got)
    # 내부 버튼도 사이트의 `button{all:unset !important}`를 shadow 경계가 막아야 한다.
    assert got["btnBg"] not in TRANSPARENT, ("'전체 수집' 버튼 배경이 투명 — 유령 버튼", got)
    assert got["btnW"] >= 40, ("'전체 수집' 버튼 너비 초기화", got)


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_bulkbar_contract_fails_on_all_initial_reinjection():
    """인위 회귀 — 가시 요소(.bar)에 all:initial이 되살아나면 계약이 **실패해야** 한다.

    주의: 이제 *호스트*에 all:initial을 걸어도 계약은 깨지지 않는다 — 가시 UI가 shadow 안으로 들어갔으니
    호스트 초기화가 무해해진 것이 이번 이전의 성과다. 따라서 게이트가 실제로 잡아야 하는 것은
    **가시 요소 자체에 all:initial이 다시 붙는 경우**이고, 그 경로로 회귀를 주입해 검증한다.
    """
    code = _isolated_code()
    anchor = '".bar{box-sizing:border-box;'
    assert anchor in code, "회귀 주입 지점(벌크바 shadow CSS)을 찾지 못했다"
    # 원래 사고와 같은 형태로 주입한다: `!important`가 붙어야 뒤따르는 비-!important 선언(배경·크기)을 이긴다.
    broken = code.replace(anchor, '".bar{all:initial !important;box-sizing:border-box;', 1)
    got = _measure_listing(broken)
    assert got["exists"], got
    broke = got["barW"] < 40 or got["barH"] < 20 or got["barBg"] in TRANSPARENT
    assert broke, ("가시 요소에 all:initial을 되돌렸는데 계약이 통과한다 = 게이트가 무의미", got)


QUICK_PROBE = """() => {
    const host = document.querySelector('.kgp-card-quick');
    if (!host) return { exists: false };
    const root = host.shadowRoot;
    const pill = root ? root.querySelector('.p') : null;
    const ps = pill ? getComputedStyle(pill) : null;
    const lbl = root ? root.querySelector('.l') : null;
    return {
      exists: true,
      hasShadow: !!root,
      hostPosition: getComputedStyle(host).position,
      pillBg: ps ? ps.backgroundColor : '',
      pillW: pill ? pill.offsetWidth : 0,
      pillH: pill ? pill.offsetHeight : 0,
      pillColor: ps ? ps.color : '',
      label: lbl ? lbl.textContent : '',
    };
}"""


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_tile_hover_button_visible_contracts():
    """타일 호버 수집 버튼 — shadow 안 알약이 배경·크기·라벨을 갖는다.

    사이트가 `*{background:none!important;font-size:0!important}`를 때려도 shadow 경계 안은 살아야 한다
    (옛 구조에서는 버튼과 자식 span에 all:initial 인라인을 박아 이 층이 통째로 유령이 됐다).
    """
    got = _measure_listing(_isolated_code(), QUICK_PROBE)
    assert got["exists"], "타일에 호버 수집 버튼이 부착되지 않았다"
    assert got["hasShadow"], "호버 버튼이 shadow 호스트가 아니다"
    assert got["hostPosition"] == "absolute", got
    assert got["pillBg"] not in TRANSPARENT, ("알약 배경이 투명 — 비가시", got)
    assert got["pillW"] >= 40, ("알약 너비 초기화 — 비가시", got)
    assert got["pillH"] >= 20, ("알약 높이 초기화 — 비가시", got)
    assert got["label"].strip(), ("라벨이 비었다 — 무스타일/빈 버튼", got)


def test_no_all_initial_inline_in_visible_ui():
    """가시 UI에 `all:initial` 인라인 잔존 0.

    허용되는 유일한 형태는 shadow 스타일시트의 `:host{all:initial}`(호스트 자신만 초기화 — 내부 요소엔
    영향 없음). 인라인 style 문자열에 all:initial이 다시 등장하면 v86이 잡은 유령이 그대로 재발한다.
    """
    cs = (EXT / "content_script.js").read_text(encoding="utf-8")
    assert "_KGP_RESET" not in cs.replace("옛 `_KGP_RESET`", ""), "all:initial 인라인 리셋 상수가 부활했다"
    offenders = []
    for ln, line in enumerate(cs.splitlines(), 1):
        code = line.split("//")[0]                      # 주석은 역사 설명이라 제외
        if "all:initial" not in code.replace(" ", "").replace("all: initial", "all:initial"):
            continue
        if ":host{all:initial}" in code.replace(" ", ""):
            continue                                     # 허용 형태
        offenders.append((ln, line.strip()))
    assert not offenders, f"가시 UI에 all:initial 인라인 잔존: {offenders}"


def test_migrated_surfaces_use_shadow():
    """타일 호버 버튼·벌크바·뱃지가 실제로 shadow 경로를 쓴다(소스 계약)."""
    cs = (EXT / "content_script.js").read_text(encoding="utf-8")
    assert "_kgpBuildQuick" in cs and "_kgpShadowHost(host, _kgpQuickShadowCss()" in cs, "호버 버튼 shadow 미적용"
    assert "_kgpShadowHost(bar, css, html)" in cs, "벌크바 shadow 미적용"
    assert "_kgpBuildCheckbox" in cs, "선택 뱃지 shadow 미적용"
    # 벌크바 내부 조회가 document.getElementById로 되돌아가면 shadow를 못 뚫어 조용히 죽는다.
    for dead in ('getElementById("kgp-tb-count")', 'getElementById("kgp-tb-status")', 'getElementById("kgp-tb-retry")'):
        assert dead not in cs, f"shadow를 못 뚫는 조회로 복귀: {dead}"


def test_fab_source_uses_shadow_not_all_initial():
    """소스 계약: FAB 생성부가 all:initial 리셋 경로로 되돌아가지 않는다."""
    cs = (EXT / "content_script.js").read_text(encoding="utf-8")
    i = cs.index("btn.id = KGP_BTN_ID")
    j = cs.index("_kgpMount(btn)", i)
    block = cs[i:j]
    assert "_kgpShadowHost(btn" in block, "FAB가 shadow 호스트로 만들어지지 않는다"
    assert "_KGP_RESET" not in block, "FAB가 all:initial 리셋 경로로 복귀했다"
    # 공용 헬퍼는 :host 에만 initial을 건다(내부 요소까지 초기화하면 같은 사고 재발).
    assert '":host{all:initial}"' in cs
