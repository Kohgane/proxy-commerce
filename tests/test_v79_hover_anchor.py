"""tests/test_v79_hover_anchor.py — v79 STEP1: hover 버튼 소멸 루프 수리.

오너 1순위: 아마존·테무 목록에서 [수집] 버튼이 커서 위치(이미지 중앙)에 나타나며 타일 mouseleave 유발
→ 숨김 → 재hover 반복(깜빡임). 버튼을 클릭할 수가 없다.

수리: hover 판정을 [타일 ∪ 버튼] 공통으로(버튼도 hover 유지 대상 → mouseenter/leave를 버튼에도 바인딩)
+ 숨김에 200ms 유예(재진입 시 취소). 계약: 버튼 위로 마우스를 옮기면 버튼이 유지(사라지지 않음)·클릭 가능.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
DETECT = Path("extensions/chrome-collector/kgp-detect.js").read_text(encoding="utf-8")
SEARCH_FIXTURE = Path("fixtures/realpages/amazon-search.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.124"


# ── source-contract: [타일∪버튼] 공통 hover + 200ms 유예 ──
def test_hover_grace_source():
    # 숨김 200ms 유예(setTimeout).
    assert '_hoverTimer = setTimeout(() => { _apply(false); _hoverTimer = null; }, 200);' in CS
    # 재진입 시 취소(_show가 타이머 clear).
    assert 'const _show = () => { if (_hoverTimer) { clearTimeout(_hoverTimer); _hoverTimer = null; } _apply(true); };' in CS
    # 타일 + 버튼 둘 다 hover 유지 대상(버튼에도 mouseenter/leave 바인딩).
    assert 'c.el.addEventListener("mouseenter", _show);' in CS
    assert 'c.el.addEventListener("mouseleave", _hide);' in CS
    assert 'q.addEventListener("mouseenter", _show);' in CS
    assert 'q.addEventListener("mouseleave", _hide);' in CS


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


_INJECT = """(a) => {
  const [detect, cs] = a;
  window.chrome = {
    runtime: { id: 'x', onMessage: { addListener(){} }, sendMessage(){}, getURL: u => u, lastError: null,
               getManifest: () => ({ version: '1.5.120' }) },
    storage: {
      local: { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } },
      sync:  { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } }
    }
  };
  (0, eval)(detect);
  (0, eval)(cs);
}"""

AMZ_SEARCH_URL = "https://www.amazon.com/s?k=ultraslim+phone+grip"


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_hovering_button_keeps_it_and_grace_hides():
    """타일 hover→버튼 등장 / 버튼 위로 옮기면 유지(루프 차단) / 버튼 이탈 후 200ms 유예 뒤 숨김."""
    from playwright.sync_api import sync_playwright
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()

        def h(r):
            if r.request.url.split("#")[0] == AMZ_SEARCH_URL:
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=SEARCH_FIXTURE)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(AMZ_SEARCH_URL, wait_until="domcontentloaded")
        page.evaluate(_INJECT, [DETECT, CS])
        page.wait_for_timeout(1200)

        seq = page.evaluate("""async () => {
            const sleep = (ms) => new Promise(r => setTimeout(r, ms));
            const q = document.querySelector('.kgp-card-quick');
            if (!q) return { err: 'no-button' };
            // 이 버튼이 속한 타일(c.el) — 배지의 형제 컨테이너를 못 찾으면 closest로.
            const card = q.closest('[data-kgp="done"]') || q.parentElement;
            const op = () => parseFloat(getComputedStyle(q).opacity || '1');
            const fire = (el, type) => el.dispatchEvent(new MouseEvent(type, { bubbles: false }));

            const before = op();                                 // 기본: 숨김(0)
            fire(card, 'mouseenter'); await sleep(180);          // >transition(.12s)
            const onCardHover = op();                            // 타일 hover → 등장(1)
            // 깜빡임 시뮬: 타일 leave 직후 버튼 enter(커서가 버튼 위로) — 유지돼야(루프 차단).
            fire(card, 'mouseleave'); fire(q, 'mouseenter'); await sleep(180);
            const onButtonHover = op();                          // 버튼 위 → 유지(1)
            fire(card, 'mouseleave'); await sleep(120);          // leave 직후(유예 200ms 내)=아직 보임
            const withinGrace = op();
            // 버튼도 이탈 → 200ms 유예 경과 후 숨김.
            fire(q, 'mouseleave'); await sleep(360);
            const afterGrace = op();                             // 유예 후 → 숨김(0)
            return { before, onCardHover, onButtonHover, withinGrace, afterGrace };
        }""")
        b.close()

    assert "err" not in seq, seq
    assert seq["before"] < 0.1, ("기본 상시 노출(호버 아닌데 보임)!", seq)
    assert seq["onCardHover"] > 0.9, ("타일 hover에 버튼 미등장!", seq)
    assert seq["onButtonHover"] > 0.9, ("버튼 위로 옮겼는데 사라짐(깜빡임 루프)!", seq)
    assert seq["withinGrace"] > 0.9, ("mouseleave 즉시 숨김(200ms 유예 없음)!", seq)
    assert seq["afterGrace"] < 0.1, ("유예 경과 후에도 안 숨음!", seq)
