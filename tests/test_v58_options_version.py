"""tests/test_v58_options_version.py — v58 STEP2(옵션 수집) + STEP3(버전 스탬프).

STEP2: 라디오·버튼 그룹(색상/사이즈/1팩·2팩) 옵션 수집(select 없는 SPA 대응) + 드로어 옵션 탭 누락 배지.
STEP3: 북마클릿 토스트 버전 스탬프(bm-vN, 채택 시 +run-vM) + 확장 토스트 버전 + 페이지 '전부 삭제' 경고.
"""
from __future__ import annotations

import glob
import importlib.util
import os
from pathlib import Path

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
BM = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")


def _playwright_ok() -> bool:
    try:
        import playwright  # noqa: F401
        return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))
    except Exception:
        return False


def _views():
    from src.seller_console import views as v
    return v


# ── STEP2 옵션 수집 ──
def test_options_source_has_radio_button_groups():
    seg = EX.split("function _domOptions")[1].split("function _domSpecs")[0]
    assert 'role="radiogroup"' in seg
    assert '[class*="sku" i]' in seg and '[class*="option" i]' in seg
    assert "button" in seg and "radio" in seg


def test_options_missing_badge_in_drawer():
    assert "옵션 미수집" in PREVIEW           # 누락 시 정직 배지
    assert 'data-etab="options"' in PREVIEW


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright 미설치")
def test_button_group_options_extracted():
    from playwright.sync_api import sync_playwright
    mock = """<!doctype html><html><head><meta property="og:title" content="접이식 책상"></head><body>
<h1>접이식 책상</h1><div class="buy-box"><span class="price-current">61,144원</span></div>
<div class="sku-color"><span class="label">색상</span><button aria-label="블랙">블랙</button><button aria-label="화이트">화이트</button></div>
<div class="variant-size"><span class="label">사이즈</span><button>S</button><button>M</button><button>L</button></div>
<div class="option-pack"><span class="label">수량</span><label><input type="radio">1팩</label><label><input type="radio">2팩</label></div>
</body></html>"""
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
    opts = {o["name"]: o["values"] for o in (r.get("options") or [])}
    assert "색상" in opts and set(opts["색상"]) == {"블랙", "화이트"}
    assert "사이즈" in opts and set(opts["사이즈"]) == {"S", "M", "L"}
    # v70 STEP2: '수량' 라벨 그룹은 옵션(변형) 아님 → 명시 제외(색상·사이즈만 변형).
    assert "수량" not in opts


# ── STEP3 버전 스탬프 ──
def test_bookmarklet_toast_version_stamp():
    v = _views()
    js = v._bookmarklet_js("https://x.com", "T", True)
    assert "BMV='bm-v72'" in js
    assert "K('수집 중… ('+BMV+')',true)" in js       # 즉시 토스트에 bm-vN
    assert "BMV+'+'+rv" in js                          # 채택 시 (bm-vN+run-vM)
    run = v._bookmarklet_run_js()
    assert "ext_version='run-v62'" in run   # v62: 래퍼가 공유 추출기 결과에 버전 스탬프


def test_extension_toast_has_version():
    assert "getManifest().version" in CS
    assert "ext v" in CS


def test_bookmarklet_page_delete_all_warning_and_shortcut():
    assert "전부 삭제" in BM
    assert "Ctrl+Shift+O" in BM                        # 북마크 관리자 단축키
    assert "bm-v72" in BM                              # 설치 후 확인 토스트 버전 안내
