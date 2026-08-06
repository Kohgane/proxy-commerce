"""tests/test_v86_c_tile_independence.py — v86-C: 타일 버튼 독립 · 호버 노출 회귀 · 지연 타일 재스캔.

■ 오너 확정 UX (STEP4.1의 '상시 노출' 승인은 **철회**됨)
  - 타일 개별 수집버튼은 벌크바와 **완전 독립**. 목록이 감지되면 항상 주입되고,
    마우스를 올리면 뜨고 떼면 사라진다(퍼센티식 호버 노출). 상시 표시 금지.
  - 벌크바는 **체크박스(chk) 표시/숨김만** 관장한다. 닫아도 호버 수집버튼은 계속 작동한다.

■ 무엇이 잘못돼 있었나(오너 1.5.133 실측)
  라쿠텐 검색: merged 37 · tile_quick_n 0 · bar false — 주입이 벌크바 오픈에 **결합**돼 있었다.
  코드상 근거: 바가 닫히면(_kgpClosed) `.kgp-card-chk`뿐 아니라 `.kgp-card-quick`까지 함께 지우고
  early return 했다. 알리·아마존에서 버튼이 보였던 건 그 세션에서 바가 열려 있었기 때문이다.

  아마존: 스캔 72 · parse-fail 33 · 추천 카운트 1→23 널뜀 — 지연 로드 타일이 주입 **이후** 렌더돼
  버튼을 못 받았다. 재스캔 옵저버는 있었으나 `if (_kgpClosed) return;`으로 역시 바에 묶여 있었다.

■ 계약 반전 주의
  이전 계약은 'rest가 0이면 red'였다. 지금은 **rest가 0이어야 green**이다(오너 철회 반영).
  기존 v86 가시성·v79 호버 계약도 같은 방향으로 뒤집었다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import _pw

EXT = Path("extensions/chrome-collector")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
CS = (EXT / "content_script.js").read_text(encoding="utf-8")
_SNAP = "kgp-snapshot-search-rakuten-co-jp-search-mall-*.html"
_URL = "https://search.rakuten.co.jp/search/mall/x/"


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.138"


def _pw_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(_pw.chromium_hits())


CHROME_STUB = """
  window.chrome = {
    runtime: { id: 'x', lastError: null, getManifest: () => ({version:'0'}), getURL: (p)=>p,
               sendMessage: (m,cb)=>{ cb && setTimeout(()=>cb({ok:false}),0); }, onMessage:{addListener(){}} },
    storage: { local: { get:(k,cb)=>cb&&cb({}), set:()=>{} }, sync:{ get:(k,cb)=>cb&&cb({}) },
               onChanged:{ addListener(){} } },
  };
"""

COUNT_PROBE = """() => {
    const q = document.querySelectorAll('.kgp-card-quick');
    return {
      tile_quick_n: q.length,
      tile_chk_n: document.querySelectorAll('.kgp-card-chk').length,
      bar: !!document.getElementById('kgp-listing-toolbar'),
      rest_inline: q.length ? q[0].style.opacity : null,
    };
}"""


def _isolated_code():
    return ";\n".join(
        (EXT / j).read_text(encoding="utf-8")
        for cs in MANIFEST["content_scripts"]
        if (cs.get("world") or "ISOLATED") == "ISOLATED" for j in cs["js"])


def _run(probe, code=None, bar_closed=False, pre=None):
    """오너 실측 스냅샷을 그대로 띄운다(합성 픽스처 금지)."""
    from playwright.sync_api import sync_playwright

    hits = sorted(Path("fixtures/realpages/diag").glob(_SNAP))
    if not hits:
        pytest.skip(f"스냅샷 미커밋: {_SNAP}")
    body = hits[0].read_text(encoding="utf-8", errors="ignore")
    ph = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
          '<rect fill="#ccc" width="200" height="200"/></svg>')
    with sync_playwright() as pw:
        b = pw.chromium.launch(**_pw.launch_opts())
        page = b.new_context(viewport={"width": 1400, "height": 900}).new_page()

        def route(r):
            u = r.request.url.split("#")[0]
            if u == _URL:
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
            elif r.request.resource_type == "image":
                r.fulfill(status=200, content_type="image/svg+xml", body=ph)
            else:
                r.abort()
        page.route("**/*", route)
        page.goto(_URL, wait_until="domcontentloaded")
        page.evaluate(CHROME_STUB)
        if bar_closed:
            # '수동' 설정 = 새 목록 페이지를 접힌(배지) 상태로 시작 → 바 미오픈 재현.
            page.evaluate("() => localStorage.setItem('kgp_bar_auto', '0')")
        page.evaluate(code or _isolated_code())
        page.wait_for_timeout(1500)
        if pre:
            page.evaluate(pre)
        got = page.evaluate(probe)
        b.close()
    return got


# ── 소스 계약 ────────────────────────────────────────────────────────────────

def test_injection_decoupled_from_bar_source():
    """바 닫힘 경로가 chk만 걷고 호버 버튼은 계속 주입한다."""
    seg = CS.split("if (_kgpClosed) {")[1].split("return;")[0]
    assert "_kgpEnsureTileQuick" in seg, "바 닫힘 경로에서 호버 버튼을 주입하지 않는다"
    assert ".kgp-card-quick" not in seg, "바를 닫을 때 호버 버튼까지 지운다(옛 결합 부활)"


def test_rescan_not_gated_by_bar_source():
    """재스캔 옵저버가 바 상태로 막히지 않는다(지연 타일이 바 때문에 버튼을 못 받으면 안 된다)."""
    seg = CS.split("function kgpRescanTiles()")[1].split("}, 300);")[0]
    assert "_kgpClosed" not in seg, "재스캔이 여전히 바 상태에 묶여 있다"
    assert "kgpInjectListing()" in seg


def test_rest_opacity_is_zero_source():
    """오너 철회 반영 — rest는 0. 상시 노출 상수가 되살아나면 red."""
    assert "var KGP_QUICK_REST_OPACITY = 0;" in CS


def test_reveal_uses_js_setproperty_not_sheet():
    """노출 전환은 전부 JS setProperty — 시트 의존 금지(STEP4 원칙 유지)."""
    seg = CS.split("function _kgpBindQuickReveal")[1].split("\n}")[0]
    assert 'setProperty("opacity"' in seg
    assert "classList" not in seg, "시트 클래스 토글로 노출을 제어한다(시트 의존)"


def test_touch_two_tap_source():
    """터치 폴백: 첫 탭 노출 · 둘째 탭 실행(안 보이는 버튼이 바로 수집되면 사고)."""
    seg = CS.split("function _kgpBindQuickReveal")[1].split("\n}")[0]
    assert "if (KGP_TOUCH) {" in seg
    assert 'q.dataset.revealed = "0"' in seg
    assert "touchstart" in seg
    click = CS.split('q.addEventListener("click", (e) => {')[1].split("});")[0]
    assert 'KGP_TOUCH && q.dataset.revealed !== "1"' in click, "첫 탭이 바로 수집을 실행한다"


# ── 실브라우저: 오너 실측 스냅샷 ──────────────────────────────────────────────

@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_tile_buttons_exist_without_opening_bar():
    """계약① 라쿠텐 재현 — 벌크바를 열지 않아도 타일 버튼이 붙는다(오너 실측 0건 → 회복)."""
    got = _run(COUNT_PROBE, bar_closed=True)
    assert got["bar"] is False, ("바가 열려버려 재현 조건이 아니다", got)
    assert got["tile_quick_n"] > 0, ("바 미오픈 상태에서 타일 버튼 0 — 결합 잔존", got)
    assert got["tile_chk_n"] == 0, ("바를 안 열었는데 체크박스가 보인다", got)
    assert got["rest_inline"] == "0", ("rest에서 버튼이 보인다 — 호버 노출 위반", got)


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_bar_toggle_controls_chk_only():
    """계약④ 바를 열면 chk가 뜨고, 닫으면 chk만 사라진다 — 호버 버튼은 생존."""
    opened = _run(COUNT_PROBE, bar_closed=False)
    assert opened["bar"] is True, opened
    assert opened["tile_chk_n"] > 0, ("바를 열었는데 체크박스가 없다", opened)
    assert opened["tile_quick_n"] > 0, opened

    closed = _run(COUNT_PROBE, bar_closed=True)
    assert closed["tile_chk_n"] == 0, ("바를 닫았는데 체크박스가 남았다", closed)
    assert closed["tile_quick_n"] == opened["tile_quick_n"], \
        ("바 상태에 따라 호버 버튼 수가 달라진다 = 아직 결합", {"open": opened, "closed": closed})


HOVER_PROBE = """async () => {
    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
    const q = document.querySelector('.kgp-card-quick');
    if (!q) return { err: '버튼 없음' };
    const card = q.closest('[data-kgp="done"]') || q.parentElement;
    const rest = q.style.opacity;
    card.dispatchEvent(new MouseEvent('mouseenter', { bubbles: false }));
    await sleep(350);                       // transition(.12s)보다 넉넉히 — 즉시 읽으면 옛 값이 나온다
    const after = q.style.opacity;
    card.dispatchEvent(new MouseEvent('mouseleave', { bubbles: false }));
    q.dispatchEvent(new MouseEvent('mouseleave', { bubbles: false }));
    await sleep(400);                       // 숨김 유예 200ms 경과
    return { rest: rest, after: after, leave: q.style.opacity };
}"""


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_hover_cycle_zero_one_zero():
    """계약② rest 0 → mouseenter 후 1 → leave 후 0. 판정은 **인라인** 값(시트 아님)."""
    got = _run(HOVER_PROBE)
    assert "err" not in got, got
    assert got["rest"] == "0", ("rest가 0이 아니다 — 상시 노출 잔존", got)
    assert got["after"] == "1", ("호버해도 안 뜬다 — 노출 경로 사망", got)
    assert got["leave"] == "0", ("마우스를 뗐는데 남아 있다 — 화면을 가린다", got)


LAZY_PROBE = """async () => {
    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
    const before = document.querySelectorAll('.kgp-card-quick').length;
    const anchor = document.querySelector('[data-kgp="done"]');
    const host = (anchor && anchor.parentElement) || document.body;
    for (let i = 0; i < 10; i++) {
      const d = document.createElement('div');
      d.innerHTML = '<a href="https://item.rakuten.co.jp/lazyshop/LZ' + i + '/">'
        + '<img src="x.jpg" width="200" height="200" alt="지연상품 ' + i + '"></a><span>2,500円</span>';
      d.style.cssText = 'width:220px;height:300px;display:block';
      host.appendChild(d);
    }
    await sleep(900);                       // 디바운스 300ms + 여유
    return { before: before, after: document.querySelectorAll('.kgp-card-quick').length };
}"""


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_lazy_tiles_get_buttons():
    """계약③ 주입 이후 렌더된 타일 10개도 자동으로 버튼을 받는다(아마존 카운트 널뜀의 원인)."""
    got = _run(COUNT_PROBE, pre=LAZY_PROBE)
    lazy = _run(LAZY_PROBE)
    assert lazy["before"] > 0, ("기준 타일이 0 — 계약이 공허", lazy)
    assert lazy["after"] >= lazy["before"] + 10, ("지연 타일이 버튼을 못 받았다", lazy)
    assert got["tile_quick_n"] > 0


# ── 인위회귀 ─────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_contract_fails_when_injection_recoupled_to_bar():
    """인위회귀 — 주입을 다시 바 오픈에 결합하면 계약①이 실패해야 한다."""
    code = _isolated_code()
    anchor = "    cards.forEach((c) => _kgpEnsureTileQuick(c, null));"
    assert anchor in code, "회귀 주입 지점을 찾지 못했다"
    broken = code.replace(anchor, '    document.querySelectorAll(".kgp-card-quick").forEach((b) => b.remove());', 1)
    got = _run(COUNT_PROBE, code=broken, bar_closed=True)
    assert got["tile_quick_n"] == 0, ("바에 재결합했는데도 버튼이 남는다 = 게이트가 무의미", got)
