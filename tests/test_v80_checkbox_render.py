"""tests/test_v80_checkbox_render.py — v80 STEP1: 선택 체크박스 투명 렌더 수리(P0).

오너 진단(1.5.114): 좌상단 선택 UI가 기능은 작동(선택 성공)하나 시각적으로 미표시 — I빔 커서·무스타일
텍스트. 근본: light-DOM 텍스트 배지가 all:initial(비-!important cursor/box-shadow 스트립)·사이트 CSS 오염에
취약. 수리: 체크박스를 shadow DOM에 자체 그림(먹 반투명 원+금 체크) + 스타일 이중 주입(adoptedStyleSheets +
<style> 인라인 폴백). 계약: 미선택/선택 두 상태가 육안 구분(shadow .b / .b.on)·22px·cursor pointer.
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
    assert MANIFEST["version"] == "1.5.120"


# ── source-contract: shadow DOM + 이중 주입 + 자체 그린 체크박스 ──
def test_shadow_checkbox_source():
    assert "function _kgpBuildCheckbox(host, selected)" in CS
    assert 'host.attachShadow({ mode: "open" })' in CS
    # 이중 주입: adoptedStyleSheets + <style> 인라인 폴백.
    assert "new CSSStyleSheet()" in CS and "root.adoptedStyleSheets = [sh]" in CS
    assert 'document.createElement("style")' in CS and "root.appendChild(st)" in CS
    assert "adoptedStyleSheets 미지원" in CS               # 실패 시 콘솔 경고
    # 자체 그린 체크박스(먹 반투명 + 금 체크) + 미선택/선택 클래스.
    assert "background:rgba(26,23,20,.82)" in CS and "border:1.6px solid #c9a24b" in CS
    assert ".b.on{background:#119a8e" in CS
    assert "stroke=\"#f0d68a\"" in CS                       # 금 체크 마크
    # 텍스트 배지 폐기(‘선택’/‘✓ 선택’ textContent 제거).
    assert 'badge.textContent = sel ? "✓ 선택" : "선택";' not in CS
    # 호스트 스타일에 cursor:pointer !important(I빔 근원 봉인).
    assert 'cursor:pointer !important' in CS


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
def test_checkbox_renders_visible_both_states():
    """shadow 체크박스가 실제로 그려짐: 미선택=먹 박스(체크 숨김), 선택=청록 박스+금 체크 표시. 22px·cursor pointer."""
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

        info = page.evaluate("""() => {
            const b = document.querySelector('.kgp-card-chk');
            if (!b) return { err: 'no-badge' };
            const cs = getComputedStyle(b);
            const hasShadow = !!b.shadowRoot;
            const box = b.shadowRoot && b.shadowRoot.querySelector('.b');
            const boxCS = box ? getComputedStyle(box) : null;
            // 스타일 주입 성공: shadow .b 박스 배경이 투명 아님(그려짐).
            const boxBg = boxCS ? boxCS.backgroundColor : '';
            const checkHiddenUnsel = box ? getComputedStyle(box.querySelector('.c')).display : '?';
            // 선택 상태로 토글 → .b.on + 체크 표시.
            b.click();
            const boxSel = b.shadowRoot.querySelector('.b');
            const onClass = boxSel.className.indexOf('on') >= 0;
            const checkShownSel = getComputedStyle(boxSel.querySelector('.c')).display;
            const boxBgSel = getComputedStyle(boxSel).backgroundColor;
            return {
                hasShadow, w: cs.width, h: cs.height, cursor: cs.cursor,
                boxBg, checkHiddenUnsel, onClass, checkShownSel, boxBgSel,
            };
        }""")
        b.close()

    assert "err" not in info, info
    assert info["hasShadow"] is True, ("shadow root 미생성!", info)
    assert info["w"] == "22px" and info["h"] == "22px", ("호스트 22px 아님", info)
    assert info["cursor"] == "pointer", ("cursor I빔(pointer 아님)!", info)
    # 미선택: 박스 배경이 투명/none 아님(스타일 주입 성공·육안 표시) + 체크 숨김.
    assert info["boxBg"] not in ("", "rgba(0, 0, 0, 0)", "transparent"), ("체크박스 무스타일(투명 렌더)!", info)
    assert info["checkHiddenUnsel"] == "none", ("미선택인데 체크 표시", info)
    # 선택: .b.on + 체크 표시 + 배경 청록.
    assert info["onClass"] is True, ("선택인데 .on 클래스 없음", info)
    assert info["checkShownSel"] != "none", ("선택인데 체크 미표시", info)
    assert info["boxBgSel"] == "rgb(17, 154, 142)", ("선택 배경 청록 아님", info)
