"""tests/test_v60_desc_translate_draft.py — v60 STEP2(상세) + STEP3(번역) + STEP4(AI 초안 키워드).

STEP2: 상세설명(desc_text)을 가격/이미지와 독립 수집(needDom 게이트 우회) + 아마존 About this item 불릿 구조화.
STEP3: OpenAI 번역 프롬프트를 이커머스 특화(브랜드/모델 원문 보존·음차 금지·자연 판매 문체)로 재작성.
STEP4: AI 초안·키워드에서 오염어(Chat history·수집기·도메인) 차단 + 후킹/특징/옵션/배송·구매대행 구조.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
TR = Path("src/seller_console/ai/translator.py").read_text(encoding="utf-8")

os.environ.setdefault("ADAPTER_DRY_RUN", "1")


def _playwright_ok() -> bool:
    try:
        import playwright  # noqa: F401
        return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
    except Exception:
        return False


# ── STEP2 상세설명 독립 수집 ──
def test_desc_captured_independently_source():
    # v78 STEP3: 상세설명 소스 사다리(어댑터>ldjson>meta) — 가격/이미지와 독립 수집(needDom 무관).
    assert "function _adapterDetailText()" in EX
    assert 'description = _ad; descSource = "adapter";' in EX      # 어댑터 우선(독립 수집)
    assert "desc_text: description, desc_images: detailImages" in EX
    # About this item 불릿 구조화
    assert "#feature-bullets" in EX and "a-list-item" in EX


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright 미설치")
def test_amazon_about_this_item_captured_when_tier1_full():
    from playwright.sync_api import sync_playwright
    CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    # JSON-LD가 price+images 채워 needDom=false여도 About this item 불릿이 desc_text에 담겨야.
    mock = """<!doctype html><html><head>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"andobil Phone Grip","image":["https://m/i1.jpg","https://m/i2.jpg"],"offers":{"@type":"Offer","price":"12.99","priceCurrency":"USD"}}</script>
</head><body><h1><span id="productTitle">andobil Phone Grip</span></h1>
<div id="feature-bullets"><h2>About this item</h2><ul>
<li><span class="a-list-item">2026 Ultra-Thin magnetic design, only 2.5mm thick</span></li>
<li><span class="a-list-item">Strong N52 magnets, MagSafe compatible</span></li></ul></div></body></html>"""
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")[0]
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
    dt = r.get("desc_text") or ""
    assert "Ultra-Thin" in dt and "MagSafe" in dt, f"About this item 미수집: {dt!r}"
    assert r.get("source") == "json"          # Tier1 full인데도 desc 독립 수집됨


# ── STEP3 번역 프롬프트 ──
def test_translate_prompt_is_ecommerce_specialized():
    assert "이커머스 특화" in TR or "전문 상품 번역가" in TR
    assert "원문 그대로 보존" in TR and "음차" in TR       # 브랜드/모델 보존·음차 금지
    assert "단위 변환 금지" in TR
    assert '"role": "system"' in TR                        # system 프롬프트 추가


# ── STEP4 오염어 차단 + 구조 ──
def test_draft_blocks_contamination_and_structure():
    from src.seller_console.ai.translator import _structured_draft, _is_contaminated
    assert _is_contaminated("Chat history") and _is_contaminated("고가수집기")
    assert not _is_contaminated("MagSafe 호환")
    d = _structured_draft("andobil 초슬림 폰그립", "DIG",
                          ["MagSafe 호환", "Chat history", "360도 회전", "고가수집기"],
                          [], [{"name": "색상", "values": ["블랙", "화이트"]}], "andobil")
    assert "Chat history" not in d and "고가수집기" not in d      # 오염어 0
    assert "MagSafe 호환" in d and "360도 회전" in d              # 실 키워드 유지
    assert "■ 특징" in d and "■ 배송·구매대행 안내" in d          # 고정 구조
    assert "국내 배송" in d                                       # 후킹 1줄
