"""tests/test_v79_desc_filler.py — v79 STEP6: desc_text 재배선 확인(SEO/필러 거부).

오너 진단(1.5.108): v78 STEP3(어댑터>ldjson>meta 사다리) 반영에도 테무 'Temu에서…'·아마존 'Buy …'가
desc_text에 저장. 근본: 사다리의 Tier1(state description)·meta 후보가 마켓 SEO/필러여도 거부 없이 채택.
수리: _isFillerDesc(서버 _FILLER_DESC_RE 미러)로 Tier1·meta 후보가 필러면 거부(빈 상세 + 편집 AI 초안, 정직).
어댑터 상세(실 DOM)는 신뢰(필터 안 함). 계약: desc_text 접두 'Temu에서'/'Buy ' 금지.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.131"


# ── source-contract: 배포 감사(코드가 번들에 실렸는지) + 필러 거부 ──
def test_deploy_audit_and_filler_source():
    # v78 STEP3 사다리가 번들에 실존(배포 감사).
    assert "function _adapterDetailText()" in EX
    assert 'description = _ad; descSource = "adapter";' in EX
    # v79 STEP6: Tier1·meta 후보 필러 거부.
    assert "function _isFillerDesc(s)" in EX
    assert "!_isFillerDesc(j.description)" in EX
    assert "if (_m && !_isFillerDesc(_m))" in EX


def test_is_filler_desc_unit():
    """필러 판정 단위: 마켓 SEO/필러 → true, 실제 상세 → false(오탐 0)."""
    fn = re.search(r"function _isFillerDesc\(s\) \{.*?\n  \}", EX, re.S).group(0)
    cases = [
        ("Temu에서 이 캣타워를 확인하세요. 가구 제품도 좋아할 수 있습니다.", True),
        ("Buy BENKS 3-in-1 Wireless Charger online at the best price.", True),
        ("Shop cat towers and save big today!", True),
        ("이 제품은 원목으로 제작되어 튼튼합니다. 조립이 간편합니다.", False),
        ("· 소재: 원목\n· 무게: 5kg", False),
        ("조립 방법을 확인하세요", False),   # '확인하세요'만으론 필러 아님(오탐 0)
    ]
    harness = fn + "\nvar C=" + json.dumps([c[0] for c in cases]) + ";\n" \
        + "process.stdout.write(JSON.stringify(C.map(function(s){return _isFillerDesc(s);}))+'\\n');"
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        got = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    for (s, exp), g in zip(cases, got):
        assert g == exp, ("필러 판정 불일치", s[:30], g, exp)


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


# 테무: state.description=필러 + 스펙표 + 상세 텍스트 없음(이미지형). desc_text는 필러 금지(스펙 병합만).
_TEMU = (
    '<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>테무 캣타워</title>'
    '<meta property="og:description" content="Temu에서 이 캣타워를 확인하세요. 최저가로 쇼핑하세요.">'
    '<script>window.__INITIAL_STATE__={store:{goods:{title:"다층 원목 캣타워",price_str:"40,603원",'
    'description:"Temu에서 이 캣타워를 확인하세요. 가구 제품도 좋아할 수 있습니다."}}};</script></head><body>'
    '<h1>다층 원목 캣타워</h1><div class="price">40,603원</div>'
    '<table class="goods-spec"><tr><td>소재</td><td>원목</td></tr><tr><td>층수</td><td>5층</td></tr></table>'
    '<div class="gallery"><img src="https://img.kwcdn.com/product/main.jpg" width="400" height="400"></div>'
    '</body></html>'
)

# 아마존: meta 'Buy …' + feature-bullets(어댑터 상세) → 어댑터가 이겨 'Buy ' 접두 금지.
_AMZ = (
    '<!doctype html><html><head><meta charset="utf-8"><title>Charger</title>'
    '<meta name="description" content="Buy BENKS 3-in-1 Wireless Charger online, best price, free shipping.">'
    '</head><body><span id="productTitle">BENKS 3-in-1 Wireless Charger</span>'
    '<div id="corePrice_desktop"><span class="a-price"><span class="a-offscreen">$29.99</span></span></div>'
    '<div id="feature-bullets"><h2>About this item</h2><ul>'
    '<li><span class="a-list-item">15W fast wireless charging for phone, watch, earbuds</span></li>'
    '<li><span class="a-list-item">Foldable travel-friendly design</span></li></ul></div>'
    '<div class="imgTagWrapper"><img src="https://m.media-amazon.com/images/I/71c.jpg" width="500" height="500"></div>'
    '</body></html>'
)


def _extract(url, body):
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
            if r.request.url.split("#")[0] == url:
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(url, wait_until="domcontentloaded")
        res = page.evaluate("(ex)=>{ (0,eval)(ex); return window.kgpExtractProduct(); }", EX)
        b.close()
    return res


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_temu_desc_not_filler():
    """테무: state·meta가 'Temu에서…' 필러여도 desc_text에 접두 'Temu에서' 금지(스펙 병합 or 빈 상세)."""
    res = _extract("https://www.temu.com/kr/cat-tower-g-1.html", _TEMU)
    desc = (res.get("desc_text") or res.get("description") or "")
    assert not desc.lstrip().startswith("Temu에서"), ("desc_text가 필러!", desc[:60], res.get("desc_source"))
    assert "제품도 좋아할 수 있습니다" not in desc[:80], ("추천 필러 꼬리!", desc[:80])
    # 스펙 병합은 살아야(정직 — 스펙표는 desc에 반영).
    assert "소재: 원목" in desc, ("스펙 병합 소실!", desc[:120])


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_amazon_desc_adapter_beats_buy_meta():
    """아마존: meta 'Buy …' 존재해도 feature-bullets 어댑터가 이겨 desc_text 접두 'Buy ' 금지 + 불릿."""
    res = _extract("https://www.amazon.com/dp/BENKSV79", _AMZ)
    desc = (res.get("desc_text") or res.get("description") or "")
    assert not desc.lstrip().startswith("Buy "), ("desc_text가 meta 'Buy …'!", desc[:60])
    assert "Buy " not in desc[:20], desc[:60]
    assert "15W fast wireless charging" in desc, ("어댑터 불릿 소실!", desc[:120])
    assert res.get("desc_source") == "adapter", res.get("desc_source")
