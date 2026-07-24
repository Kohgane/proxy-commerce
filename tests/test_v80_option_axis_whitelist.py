"""tests/test_v80_option_axis_whitelist.py — v80 STEP4: 옵션 축(이름) 화이트리스트 잔여 봉합(마감 2).

오너 진단(1.5.114): 라쿠텐 '日本'·'タイ'(原産地)·아마존 잔여 1건 — sku diff 기반 옵션 추출이 원산지·브랜드 등
**공통축(스펙 속성)**을 값이 2개 이상이면 옵션으로 통과. v79 STEP3(값 화이트리스트)는 원산지 '값'(日本)이
숫자/화살표/탭명 아니라 못 걸렀다. 수리: **축명(_isBadOptAxis)** 으로 원산지·브랜드·제조사·품번·모델·JAN 등
스펙 축을 sku/DOM 양경로에서 배제. 색상·사이즈 등 진짜 옵션은 보존. 계약: opt오염 지표 전 픽스처 0.
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
    assert MANIFEST["version"] == "1.5.122"


# ── source-contract: 축명 화이트리스트 sku/DOM 양경로 ──
def test_axis_whitelist_source():
    assert "function _isBadOptAxis(name)" in EX
    assert "if (_isBadOptAxis(axis)) return;" in EX      # sku 경로
    assert "if (_isBadOptAxis(name)) return;" in EX      # DOM(_push) 경로


def test_is_bad_opt_axis_unit():
    """스펙 축(원산지·브랜드·품번·모델·JAN) 배제 / 색상·사이즈 등 진짜 옵션 보존(오탐 0)."""
    fn = re.search(r"function _isBadOptAxis\(name\) \{.*?\n  \}", EX, re.S).group(0)
    bad = ["原産地", "원산지", "原産国", "品番", "型番", "ブランド", "브랜드", "Brand", "Made in",
           "メーカー", "제조사", "Manufacturer", "Model Number", "JAN", "ASIN"]
    ok = ["색상", "사이즈", "컬러", "Color", "Size", "수량", "옵션", "종류", "타입", "스타일", "용량"]
    harness = fn + "\nvar B=" + json.dumps(bad) + ",G=" + json.dumps(ok) + ";\n" \
        + "process.stdout.write(JSON.stringify({bad:B.map(function(n){return _isBadOptAxis(n);}),ok:G.map(function(n){return _isBadOptAxis(n);})})+'\\n');"
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        c = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert all(c["bad"]), ("스펙 축 미배제", [b for b, v in zip(bad, c["bad"]) if not v])
    assert not any(c["ok"]), ("진짜 옵션 오배제", [g for g, v in zip(ok, c["ok"]) if v])


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


# 라쿠텐식 sku: 原産地(日本/タイ 2값=공통 스펙축) + 색상(ブラス/シルバー 2값=진짜 옵션).
_STATE = """
window.__INITIAL_STATE__ = { item: { name: "SyuRo トレー", price: "3300円",
  skus: [
    { skuId: 1, price: "3300", specs: [ { specKeyName: "色", specValueName: "ブラス" }, { specKeyName: "原産地", specValueName: "日本" } ] },
    { skuId: 2, price: "3300", specs: [ { specKeyName: "色", specValueName: "シルバー" }, { specKeyName: "原産地", specValueName: "タイ" } ] }
  ] } };
"""
_BODY = (
    '<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>SyuRo</title>'
    "<script>" + _STATE + "</script></head><body>"
    '<h1>SyuRo トレー</h1><div class="price">3,300円</div>'
    '<div class="gallery"><img src="https://tshop.r10s.jp/syuro/cabinet/main.jpg" width="500" height="500"></div>'
    "</body></html>"
)

RAKUTEN_URL = "https://item.rakuten.co.jp/syuro/tray-900037/"


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
def test_origin_axis_not_option_but_color_is():
    """原産地(日本/タイ 2값 diff)는 옵션 아님(공통 스펙축), 色(ブラス/シルバー)은 옵션 유지."""
    res = _extract(RAKUTEN_URL, _BODY)
    opts = res.get("options") or []
    names = {o.get("name") for o in opts}
    vals = [v for o in opts for v in (o.get("values") or [])]
    # 原産地 축·값(日本·タイ) 옵션 0.
    assert "原産地" not in names, ("원산지가 옵션 축!", opts)
    assert "日本" not in vals and "タイ" not in vals, ("원산지 값이 옵션값!", opts)
    # 色(색상) 옵션은 유지(ブラス/シルバー).
    assert any(set(o.get("values") or []) >= {"ブラス", "シルバー"} for o in opts), ("색상 옵션 소실!", opts)
