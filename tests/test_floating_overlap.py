"""tests/test_floating_overlap.py — 고정 플로팅 요소는 인터랙티브 요소를 덮지 않는다 (오너 계약 6-f-4).

**겹침은 z-order 문제가 아니다.** 플로팅 버블이 위에 뜨는 건 맞다 — 문제는 그 밑에
**아무 자리도 예약돼 있지 않다는 것**이다. 그래서 마지막 카드의 액션 버튼이 영구히 깔린다.
스크롤을 끝까지 내려도 안 드러난다. 페이지가 거기서 끝나기 때문이다.

실측(수리 전, 1920×940 · 최하단 스크롤):
- orders `CSV 내보내기` — 1872px² (페이지가 아예 안 스크롤되는 높이라 **탈출구가 없다**)
- reject-watch `처방 실행` — 619px² (오너가 신고한 그 버튼)
- 모바일 390은 겹침 0 — v36이 이미 `padding-bottom: 84px`를 비워 뒀다.
  **데스크톱만 빠져 있었다.** 한쪽만 고쳐 놓고 잊은 이 프로젝트의 단골 결함.

계약은 두 겹이다. 계산값(예약 폭)과 **렌더**(실제 교차)를 같이 본다 —
계산값만 보면 [[flex는 text-align을 무시한다]]를 또 만난다.
"""
from __future__ import annotations

import glob
import os
import re
import threading
import time
from pathlib import Path

import pytest

CSS = Path("src/seller_console/static/console.css")
BASE = Path("src/seller_console/templates/_base.html")

# 버블 실측(1920×940): 152×95 @(1750,827) — 하단 18px 띄움 → 바닥에서 113px를 차지한다.
BUBBLE_OCCUPIES = 113
MINI_OCCUPIES = 62                       # 재오픈 미니 44 + 하단 18


def _rule(css: str, selector: str) -> str | None:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else None


def _px(decls: str, prop: str) -> float | None:
    m = re.search(prop + r"\s*:\s*([\d.]+)px", decls)
    return float(m.group(1)) if m else None


# ── 예약 공간이 CSS에 있나 (브라우저 없이도 도는 층) ─────────────────────────
def test_desktop_reserves_space_for_the_bubble():
    """★ 데스크톱 본문이 버블 높이만큼 바닥을 비운다."""
    css = CSS.read_text(encoding="utf-8")
    block = css.split("@media (min-width: 768px)")[1].split("\n}")[0]
    pad = _px(block, "padding-bottom")
    assert pad is not None, "데스크톱 예약 규칙이 없다"
    assert pad >= BUBBLE_OCCUPIES, f"예약 {pad}px < 버블 점유 {BUBBLE_OCCUPIES}px"


def test_mobile_reserve_is_still_there():
    """v36의 모바일 예약을 데스크톱 수리가 지우지 않았는지 — **양쪽을 한 번에 본다.**

    이 프로젝트가 반복해 온 실수가 '이중 구현, 한쪽만 수리'다. 다음엔 반대로 모바일이
    지워질 수 있으니 두 층을 같은 계약이 붙든다.
    """
    css = CSS.read_text(encoding="utf-8")
    # 모바일 블록은 여러 개다 — 어느 블록에 있든 인정하되, **모바일 미디어 안**이어야 한다.
    mobile = "".join(css.split("max-width: 767.98px")[1:])
    assert re.search(r"\.console-content\s*\{\s*padding-bottom:\s*84px", mobile), "모바일 예약이 사라졌다"


def test_reserve_is_the_default_not_a_js_grant():
    """★ 기본값이 '버블 있음'이다 — JS가 죽어도 자리는 비어 있어야 한다.

    반대로 짜면(JS가 클래스를 **붙여야** 자리가 생김) 스크립트 하나 깨질 때 결함이 되살아난다.
    """
    css = CSS.read_text(encoding="utf-8")
    block = css.split("@media (min-width: 768px)")[1].split("\n}")[0]
    default = _rule(block, ".console-content")
    assert default and "padding-bottom" in default, "예약이 조건부 클래스 뒤에 숨어 있다"
    hidden = _rule(block, "body.pc-fb-hidden .console-content")
    assert hidden, "숨김 상태 축소 규칙이 없다"
    assert MINI_OCCUPIES <= (_px(hidden, "padding-bottom") or 0) < (_px(default, "padding-bottom") or 0)


def test_hidden_state_toggles_the_reserve():
    """숨기면 예약도 같이 줄어든다 — 숨겼는데 큰 여백이 남으면 그건 그것대로 결함이다."""
    js = BASE.read_text(encoding="utf-8")
    fn = js.split("function apply()")[1].split("\n  }")[0]
    assert "classList.toggle('pc-fb-hidden', hidden)" in fn
    # 표시 토글과 **같은 함수**에서 — 두 곳으로 갈라지면 언젠가 어긋난다.
    assert "wrap.style.display" in fn and "reopen.style.display" in fn


def test_editor_drawer_leaves_no_dead_space():
    """드로어는 버블 자체를 숨긴다(app.css `.kgp-editor`) → 빈 자리를 남길 이유가 없다."""
    assert ".kgp-editor #fbWrap" in Path("src/static/app.css").read_text(encoding="utf-8")
    assert "body.kgp-editor .console-content" in CSS.read_text(encoding="utf-8")


# ── 실제로 안 겹치나 (헤드리스) ──────────────────────────────────────────────
def _pw_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    if glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"):
        return True
    cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or (Path.home() / ".cache" / "ms-playwright"))
    return cache.is_dir() and any(cache.glob("chromium-*"))


PROBE = """(ids) => {
  const out = {};
  for (const id of ids) {
    const el = document.getElementById(id);
    const s = el && getComputedStyle(el);
    if (!el || s.display === 'none' || s.visibility === 'hidden') { out[id] = null; continue; }
    const b = el.getBoundingClientRect();
    const hits = [];
    document.querySelectorAll('a.btn, button.btn, input, select, textarea, summary, a[href], [role=button]')
      .forEach(function (e) {
        if (e.closest('#fbWrap, #fbReopen, .sidebar, .console-sidebar')) return;
        const cs = getComputedStyle(e);
        if (cs.display === 'none' || cs.visibility === 'hidden') return;
        const r = e.getBoundingClientRect();
        if (!r.width || !r.height) return;
        const ov = Math.max(0, Math.min(b.right, r.right) - Math.max(b.left, r.left))
                 * Math.max(0, Math.min(b.bottom, r.bottom) - Math.max(b.top, r.top));
        if (ov > 0) hits.push({t: (e.textContent || e.value || e.tagName).replace(/\\s+/g, ' ').trim().slice(0, 30),
                               area: Math.round(ov)});
      });
    out[id] = hits;
  }
  const main = document.querySelector('main');
  out._pad = main ? getComputedStyle(main).paddingBottom : '';
  return out;
}"""


@pytest.fixture(scope="module")
def live_server():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    import urllib.request

    from src.order_webhook import app
    port = 8911
    threading.Thread(target=lambda: app.run(port=port, threaded=True, use_reloader=False),
                     daemon=True).start()
    for _ in range(80):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/seller/dashboard", timeout=1)
            return f"http://127.0.0.1:{port}"
        except Exception:                                        # noqa: BLE001
            time.sleep(0.25)
    pytest.skip("로컬 서버가 안 떴다")


@pytest.mark.skipif(not _pw_ok(), reason="크로미움 없음 — 정직하게 skip")
@pytest.mark.parametrize("route", ["/seller/sourcing/reject-watch", "/seller/dashboard", "/seller/orders"])
def test_nothing_interactive_sits_under_the_bubble(live_server, route):
    """★ 최하단까지 내렸을 때 **버블 밑에 눌러야 할 것이 하나도 없다.**

    최하단으로 재는 이유: 페이지 중간이라면 더 스크롤해서 버튼을 꺼낼 수 있다.
    끝이면 못 꺼낸다 — 그게 이 결함의 본체다.
    """
    from playwright.sync_api import sync_playwright
    exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome") or [None])[0]
    bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    with sync_playwright() as pw:
        br = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = br.new_page(viewport={"width": 1920, "height": 940})
        pg.goto(live_server + route, wait_until="load")
        if os.path.exists(bs):                    # CDN은 샌드박스 프록시가 막는다 — 로컬 주입
            pg.add_style_tag(path=bs)
        pg.wait_for_timeout(400)
        for _ in range(3):                        # 지연 렌더로 높이가 자라면 한 번 더 내린다
            pg.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
            pg.wait_for_timeout(250)
        r = pg.evaluate(PROBE, ["fbWrap", "fbReopen"])
        br.close()
    assert r["fbWrap"] == [], f"{route}: 버블이 {r['fbWrap']}를 덮는다"
    assert float(r["_pad"].rstrip("px")) >= BUBBLE_OCCUPIES, f"{route}: 예약 {r['_pad']}"


@pytest.mark.skipif(not _pw_ok(), reason="크로미움 없음 — 정직하게 skip")
def test_hidden_mini_button_also_clears(live_server):
    """숨김 상태(미니 버튼)도 같은 잣대 — 자리를 줄였으니 그만큼은 여전히 비어 있어야 한다."""
    from playwright.sync_api import sync_playwright
    exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome") or [None])[0]
    bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    with sync_playwright() as pw:
        br = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = br.new_page(viewport={"width": 1920, "height": 940})
        pg.goto(live_server + "/seller/orders", wait_until="load")
        if os.path.exists(bs):
            pg.add_style_tag(path=bs)
        pg.wait_for_timeout(400)
        pg.evaluate("() => document.getElementById('fbHide').click()")
        for _ in range(3):
            pg.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
            pg.wait_for_timeout(250)
        r = pg.evaluate(PROBE, ["fbWrap", "fbReopen"])
        br.close()
    assert r["fbWrap"] is None, "숨겼는데 버블이 남아 있다"
    assert r["fbReopen"] == [], f"미니 버튼이 {r['fbReopen']}를 덮는다"
    assert float(r["_pad"].rstrip("px")) >= MINI_OCCUPIES
