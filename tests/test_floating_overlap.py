"""tests/test_floating_overlap.py — 떠 있는 요소는 누를 것을 덮지 않는다 (오너 계약 6-f-4 → Y12-A 결정 d).

6-f-4: 「처음이신가요?」 버블이 마지막 카드의 액션 버튼을 영구히 덮었다(orders `CSV 내보내기` 1872px²) —
그때는 본문 아래에 버블 자리를 예약해 막았다(하단 132/84px).

**Y12-A(오너 2026-10-17 d): 떠 있는 「처음이신가요?」 버튼은 모든 페이지에서 뺐다.** 시작 가이드는 사이드바
「시작 가이드」 한 곳. 버블이 없으니 예약 공간도 뺐다(빈 여백도 결함이다).

계약은 두 겹으로 남긴다 — ① 버블·예약이 다시 들어오지 않는다 ② **어떤 떠 있는 요소도**(다음에 누가 붙이든)
최하단까지 내렸을 때 누를 것을 덮지 않는다(렌더 실측).
"""
from __future__ import annotations

import glob
import os
import re
import tempfile
from pathlib import Path

import pytest

CSS = Path("src/seller_console/static/console.css")
BASE = Path("src/seller_console/templates/_base.html")


def test_bubble_is_gone_from_every_page():
    base = BASE.read_text(encoding="utf-8")
    for gone in ('id="fbWrap"', 'id="fbReopen"', 'id="fbBtn"', "kgp_fb_hidden"):
        assert gone not in base, gone
    assert 'href="/seller/start"' in base and "시작 가이드" in base       # 사이드바 한 곳


def test_reserve_for_the_bubble_is_gone_too():
    css = CSS.read_text(encoding="utf-8")
    assert "pc-fb-hidden" not in css and ".fb-wrap" not in css and "#fbWrap" not in css
    assert "padding-bottom: 132px" not in css and "padding-bottom: 84px" not in css


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


# 6-h 보강: **좌표만 보면 안 보이는 것까지 덮였다고 센다.**
#   내부 스크롤 카드가 생기자(6-h 반려 감시) `getBoundingClientRect()`가 스크롤 밖으로 잘린 행의
#   좌표를 그대로 돌려줬다 — 화면엔 없는 버튼이 '버블에 가려졌다'고 잡혔다(면적 2840px²).
#   잘려서 안 보이는 것은 가려질 수도 없다. 조상들의 클립 박스로 **보이는 사각형**을 먼저 구한다.
#   계약을 무르게 하는 게 아니다 — 없는 겹침을 지우고 진짜만 남긴다.
PROBE = """() => {
  function visibleRect(e) {                    // 조상 클립을 모두 통과한 뒤 남는 사각형
    let r = e.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    let p = e.parentElement;
    while (p && p !== document.documentElement) {
      const cs = getComputedStyle(p);
      if (/(auto|scroll|hidden)/.test(cs.overflowY + ' ' + cs.overflowX)) {
        const q = p.getBoundingClientRect();
        const n = {left: Math.max(r.left, q.left), top: Math.max(r.top, q.top),
                   right: Math.min(r.right, q.right), bottom: Math.min(r.bottom, q.bottom)};
        if (n.right <= n.left || n.bottom <= n.top) return null;   // 완전히 잘렸다 = 안 보인다
        r = n;
      }
      p = p.parentElement;
    }
    return r;
  }
  // 떠 있는 요소 = position fixed/sticky가 아닌 fixed 중 보이는 것(사이드바·상단바·닫힌 오버레이 제외)
  const out = {floating: []};
  document.querySelectorAll('body *').forEach(function (el) {
    const s = getComputedStyle(el);
    if (s.position !== 'fixed' || s.display === 'none' || s.visibility === 'hidden' || s.pointerEvents === 'none') return;
    if (el.closest('.sidebar, .console-sidebar, .console-topbar, .mobile-topbar, .modal, .kgp-drawer, .kgp-drawer-backdrop, .sidebar-overlay')) return;
    if (parseFloat(s.opacity || '1') === 0) return;
    const b = el.getBoundingClientRect();
    if (!b.width || !b.height) return;
    const hits = [];
    document.querySelectorAll('a.btn, button.btn, input, select, textarea, summary, a[href], [role=button]')
      .forEach(function (e) {
        if (el.contains(e) || e.closest('.sidebar, .console-sidebar')) return;
        const cs = getComputedStyle(e);
        if (cs.display === 'none' || cs.visibility === 'hidden') return;
        const r = visibleRect(e);
        if (!r) return;
        const ov = Math.max(0, Math.min(b.right, r.right) - Math.max(b.left, r.left))
                 * Math.max(0, Math.min(b.bottom, r.bottom) - Math.max(b.top, r.top));
        if (ov > 0) hits.push({t: (e.textContent || e.value || e.tagName).replace(/\\s+/g, ' ').trim().slice(0, 30),
                               area: Math.round(ov)});
      });
    if (hits.length) out.floating.push({el: (el.id || el.className || el.tagName).toString().slice(0, 40), hits: hits});
  });
  const main = document.querySelector('main');
  out._pad = main ? getComputedStyle(main).paddingBottom : '';
  return out;
}"""


# 순서는 **프로덕션과 같아야 한다**(_base.html: bootstrap → app → seller → console).
# 순서가 다르면 `!important`끼리 붙었을 때 승자가 바뀌어, 캡처가 라이브와 다른 화면이 된다.
_BS_CANDIDATES = ("node_modules/bootstrap/dist/css/bootstrap.min.css",
                  "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css")
CSS_FILES = tuple([p for p in _BS_CANDIDATES if Path(p).exists()][:1]
                  + ["src/static/app.css", "src/seller_console/static/seller.css",
                     "src/seller_console/static/console.css"])


def _page_html(route: str) -> str:
    """실 라우트 HTML + CSS 인라인 — **소켓을 열지 않는다.**

    처음엔 로컬 서버를 띄워 실 URL로 열었다(62초). `test_client`로 같은 HTML을 받고
    CSS만 넣으면 잴 것은 다 잰다(devshot 관행) — 9초로 줄었고, 서버·CDN·서비스워커가
    끼어들 자리도 없앴다.
    """
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    html = app.test_client().get(route).get_data(as_text=True)
    style = "".join(f"<style>{Path(p).read_text(encoding='utf-8')}</style>"
                    for p in CSS_FILES if Path(p).exists())
    return html.replace("</head>", style + "</head>", 1)


def _measure(route: str, width: int = 1920, height: int = 940):
    from playwright.sync_api import sync_playwright
    exe = (glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome") or [None])[0]
    slug = route.strip("/").replace("/", "-") + f"-{width}"
    tmp = Path(tempfile.gettempdir()) / f"kgp_overlap_{slug}.html"
    tmp.write_text(_page_html(route), encoding="utf-8")
    with sync_playwright() as pw:
        br = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = br.new_page(viewport={"width": width, "height": height})
        pg.set_default_timeout(15000)
        # `file://`로 연다: 이름을 풀 것도, 붙을 곳도 없다(DNS 0 · 소켓 0). 그러면서도 출처가
        # 있어서 localStorage가 살아 있다 — `about:`나 `set_content`면 던져서 숨김 토글이 안 돈다.
        pg.route("**/*", lambda r: (r.continue_() if r.request.url.startswith("file://")
                                    else r.abort()))     # 외부는 전부 끊는다
        pg.goto(tmp.as_uri(), wait_until="domcontentloaded")
        pg.wait_for_timeout(300)
        for _ in range(3):                        # 지연 렌더로 높이가 자라면 한 번 더 내린다
            pg.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
            pg.wait_for_timeout(200)
        r = pg.evaluate(PROBE)
        br.close()
    return r


@pytest.mark.skipif(not _pw_ok(), reason="크로미움 없음 — 정직하게 skip")
@pytest.mark.parametrize("route", ["/seller/dashboard", "/seller/collect/history", "/seller/diagnostics",
                                   "/seller/sourcing/reject-watch", "/seller/orders", "/seller/catalog"])
@pytest.mark.parametrize("size", [(1920, 940), (390, 844)])
def test_nothing_floating_covers_anything(route, size):
    """★ 최하단까지 내렸을 때 **떠 있는 어떤 요소도** 누를 것을 덮지 않는다(데스크톱·폰)."""
    r = _measure(route, *size)
    assert r["floating"] == [], f"{route} {size}: {r['floating']}"
