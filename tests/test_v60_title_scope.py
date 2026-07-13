"""tests/test_v60_title_scope.py — v60 STEP1: 제목 추출 오염 차단.

오너 캡처: 아마존 수집 제목='Chat history' — 삽입 UI(사이드패널/오버레이·우리 확장 kgp-*)의 h1을 상품명으로
오인. 수리: 추출 스코프에서 우리 확장 주입 DOM + 사이드패널/챗/네비 제외 + 어댑터 지정 셀렉터 우선.

우선순위: 어댑터 셀렉터(아마존 #productTitle 등) → ld+json/state name → 본문 h1(UI 제외) → og:title → document.title.
"""
from __future__ import annotations

import glob
import os
import re
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")


def _playwright_ok() -> bool:
    try:
        import playwright  # noqa: F401
        return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    except Exception:
        return False


# ── source-contract ──
def test_injected_ui_exclusion_and_adapter_source():
    assert "function _isInjectedUI" in EX
    assert "function _adapterTitle" in EX and "function _cleanH1" in EX
    assert "#productTitle" in EX                        # 아마존 하드매핑
    # kgp-* 우리 UI + 사이드패널/챗/어시스턴트 제외
    for tok in ("kgp-", "assistant", "chat", "sidebar", "complementary"):
        assert tok in EX
    # 우선순위: 어댑터 → j.title(tier1) → cleanH1(tier2) → og → document.title(tier3).
    #   v65 STEP1: 순수 사이트명(_isBareSiteName)은 후보에서 배제하며 이 순서로 첫 유효값 채택.
    assert "function _isBareSiteName" in EX
    cands = re.search(r"var _cands = \[(.*?)\];", EX, re.S).group(1)
    assert cands.index('s: "adapter"') < cands.index('s: "tier1"') < cands.index('s: "tier2"') < cands.index('s: "tier3"')


# ── behavioral: 삽입 UI 존재 상태에서 제목 오염 차단 ──
@pytest.mark.skipif(not _playwright_ok(), reason="Playwright 미설치")
def test_title_ignores_injected_chat_and_our_ui():
    from playwright.sync_api import sync_playwright
    CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    # 상품 h1(#productTitle) 앞에 'Chat history' 사이드패널 + 우리 확장 FAB h1이 존재하는 상태.
    mock = """<!doctype html><html><head><title>Amazon.com: andobil Phone Grip</title></head><body>
<aside class="side-panel assistant" role="complementary"><h1>Chat history</h1></aside>
<div id="kgp-collect-fab"><h1>고가수집기</h1></div>
<div id="dp"><h1 id="title"><span id="productTitle">andobil [2026 Ultra-Thin] Magnetic Phone Grip Ring Holder</span></h1>
<div class="price">$12.99</div></div></body></html>"""
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        p = b.new_context().new_page()
        p.set_content(mock, wait_until="load")
        r = p.evaluate(
            """(a)=>{const[EX,CS]=a;window.chrome={runtime:{id:'x',onMessage:{addListener(){}},sendMessage(){},getURL:u=>u},storage:{local:{get:(k,cb)=>cb&&cb({}),set(){},onChanged:{addListener(){}}},sync:{get:(k,cb)=>cb&&cb({}),set(){},onChanged:{addListener(){}}}}};try{(0,eval)(EX);(0,eval)(CS);}catch(e){return{__err:String(e)}}try{return extractProductMeta();}catch(e){return{__err:String(e)}}}""",
            [EX, CS],
        )
        b.close()
    title = r.get("title") or ""
    assert "andobil" in title, f"상품명 미추출: {title!r}"
    assert "Chat history" not in title and "고가수집기" not in title, f"삽입 UI 오염: {title!r}"
