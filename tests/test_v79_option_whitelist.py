"""tests/test_v79_option_whitelist.py — v79 STEP3: 옵션 값 화이트리스트.

오너 진단(1.5.108) 옵션 오염:
 · 라쿠텐: 스펙 전체(브랜드·품번 '900037'·원산지 '日本')가 옵션값으로 뭉침.
 · 아마존: '←','1','→','Product Image/Video'(캐러셀 컨트롤·미디어 탭)가 옵션값.
 · 알리: '색상: 1pcs'(축명 접두 중복).
수리: ① 오염값 배제 함수 _isBadOptValue(화살표·미디어 탭명·순수 품번 5자리+) — sku/DOM 양 경로 적용.
      ② _domOptions에서 미디어 캐러셀(#altImages·썸네일)·스펙표(table/dl/spec/attribute) 그룹 제외.
      ③ _push에서 축명 접두('색상: 1pcs'→'1pcs') 제거.
계약: 옵션 values에 숫자 품번·화살표·탭명 0.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.117"


# ── source-contract ──
def test_whitelist_source():
    assert "function _isBadOptValue(v)" in EX
    assert "if (_isBadOptValue(val)) return;" in EX                 # sku 경로 적용
    assert "!_isBadOptValue(v)" in EX                               # _push(DOM) 경로 적용
    # 미디어 캐러셀·스펙표 그룹 제외.
    assert "#altImages" in EX and '[aria-roledescription="carousel"]' in EX
    assert '[class*="attribute" i]' in EX
    # 축명 접두 중복 제거.
    assert 'var _pre = name ? new RegExp("^"' in EX


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


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


# 라쿠텐: 스펙표(브랜드·품번·원산지)가 옵션처럼 보이는 그룹 + 진짜 색상 스와치.
_RAKUTEN = (
    '<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>SyuRo 정리함</title></head><body>'
    '<h1>SyuRo 브라스 정리함</h1><div class="price">¥3,300</div>'
    # 스펙표(옵션 아님) — table 안 [class*=spec] 그룹으로 오인 유발.
    '<table class="item-spec"><tr><td class="spec-label">ブランド</td><td class="spec-value">SyuRo</td></tr>'
    '<tr><td class="spec-label">品番</td><td class="spec-value">900037</td></tr>'
    '<tr><td class="spec-label">原産地</td><td class="spec-value">日本</td></tr></table>'
    # 진짜 색상 스와치(옵션).
    '<div class="item-color-select"><span class="label">色</span>'
    '<ul class="color-swatch"><li data-color="ブラス"><img alt="ブラス"></li>'
    '<li data-color="シルバー"><img alt="シルバー"></li></ul></div>'
    '<div class="gallery"><img src="https://tshop.r10s.jp/syuro/900037/main.jpg" width="500" height="500"></div>'
    '</body></html>'
)

# 아마존: #altImages 미디어 캐러셀(Product Image/Video·←→) + 진짜 색상 트위스터.
_AMAZON = (
    '<!doctype html><html><head><meta charset="utf-8"><title>Steamer</title></head><body>'
    '<span id="productTitle">Handheld Garment Steamer</span>'
    '<div id="corePrice_desktop"><span class="a-price"><span class="a-offscreen">$25.99</span></span></div>'
    # 미디어 캐러셀(옵션 아님) — li가 옵션값으로 오인될 소지.
    '<div id="altImages" class="a-carousel"><ul class="a-carousel-viewport">'
    '<li class="a-carousel-card"><button aria-label="←"></button></li>'
    '<li class="a-carousel-card"><span>Product Image</span></li>'
    '<li class="a-carousel-card"><span>1</span></li>'
    '<li class="a-carousel-card"><span>Product Video</span></li>'
    '<li class="a-carousel-card"><button aria-label="→"></button></li></ul></div>'
    # 진짜 색상 트위스터.
    '<div id="inline-twister-row-color_name"><label class="a-form-label">Color:</label>'
    '<ul class="a-button-list"><li><img alt="White"></li><li><img alt="Pink"></li></ul></div>'
    '<div class="imgTagWrapper"><img src="https://m.media-amazon.com/images/I/71steamer.jpg" width="500" height="500"></div>'
    '</body></html>'
)


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_rakuten_spec_not_in_options():
    """라쿠텐: 브랜드·품번(900037)·원산지(日本)는 옵션 아님(스펙표 제외) — 진짜 색상만 옵션."""
    res = _extract("https://item.rakuten.co.jp/syuro/900037/", _RAKUTEN)
    vals = [v for o in (res.get("options") or []) for v in (o.get("values") or [])]
    assert "900037" not in vals, ("품번이 옵션값!", res.get("options"))
    assert "日本" not in vals and "SyuRo" not in vals, ("스펙(원산지·브랜드)이 옵션값!", res.get("options"))
    # 진짜 색상 스와치는 살아야(옵션 소실 회귀 방지).
    assert any(set(o.get("values") or []) >= {"ブラス", "シルバー"} for o in (res.get("options") or [])), res.get("options")


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_amazon_carousel_controls_not_options():
    """아마존: '←','→','1','Product Image/Video'(캐러셀·미디어 탭)는 옵션값 0 — 진짜 색상만."""
    res = _extract("https://www.amazon.com/dp/STEAMER01", _AMAZON)
    vals = [v for o in (res.get("options") or []) for v in (o.get("values") or [])]
    for bad in ("←", "→", "1", "Product Image", "Product Video"):
        assert bad not in vals, ("캐러셀 컨트롤/미디어 탭이 옵션값!", bad, res.get("options"))
    assert any(set(o.get("values") or []) >= {"White", "Pink"} for o in (res.get("options") or [])), res.get("options")


def test_bad_opt_value_unit():
    """_isBadOptValue 단위 계약: 화살표·미디어탭·품번 배제, 사이즈(S/M/38)·색상 보존."""
    import re as _re
    fn = _re.search(r"function _isBadOptValue\(v\) \{.*?\n  \}", EX, _re.S).group(0)
    import subprocess
    import tempfile
    harness = fn + "\nconst probe=(v)=>_isBadOptValue(v);\n" + (
        "process.stdout.write(JSON.stringify({"
        "arrow:probe('←'),arrow2:probe('→'),tab:probe('Product Image'),vid:probe('Product Video'),"
        "img:probe('이미지'),num:probe('900037'),"
        "sizeS:probe('S'),size38:probe('38'),color:probe('베이지'),colorEn:probe('White')"
        "})+'\\n');"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        c = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert c["arrow"] and c["arrow2"] and c["tab"] and c["vid"] and c["img"] and c["num"]     # 배제
    assert not c["sizeS"] and not c["size38"] and not c["color"] and not c["colorEn"]         # 보존
