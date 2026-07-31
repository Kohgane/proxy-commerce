"""tests/test_v74_ali_adapter.py — v74 STEP4: 알리 상세 어댑터 완성 + 숫자 정규화 공통 유틸.

증상: 알리 상세 가격 '6620.'(후행 점)·갤러리 3장 과소·옵션 0(sources: options=none). 근본:
(1) STATE_KEYS에 알리 초기상태 키 runParams 없음 → 이미지/옵션 미파싱, (2) sku 값 키 propertyValueDisplayName
미매치 → 옵션 0, (3) 후행 점 정규화 부재. 수리: runParams 추가 + _OPT_VAL_KEY 확장 + 부모 축명 상속 +
숫자 정규화 공통 유틸 _normNum(항상 \d+(\.\d+)?). 계약: price=6620·KRW·img≥6·options≥1.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.133"


# ── source-contract: 알리 어댑터 + 정규화 유틸 ──
def test_ali_adapter_source():
    assert '"runParams"' in EX                      # 알리 초기상태 키
    assert "function _normNum(s)" in EX             # 숫자 정규화 공통 유틸
    assert "price = _normNum(price)" in EX          # 최종 가격에 적용(전 어댑터 공통)
    assert "propertyvalue|valuedisplayname" in EX   # 알리 sku 값 키
    assert "var parentAxis = fnm ? fnm.v : \"\";" in EX   # 중첩 값에 부모 축명 상속


# ── node: 숫자 정규화 계약(price가 \d+(\.\d+)? 불일치 시 실패) ──
@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_normnum_contract_node():
    m = re.search(r"function _normNum\(s\) \{.*?\n  \}", EX, re.S)
    assert m, "_normNum 추출 실패"
    harness = (
        m.group(0) + "\n"
        "var C = /^\\d+(\\.\\d+)?$/;\n"
        "var cases = {a:_normNum('6,620.'), b:_normNum('₩6,620.'), c:_normNum('6620'), "
        "d:_normNum('6620.00'), e:_normNum('1 234'), f:_normNum(''), g:_normNum('abc'), h:_normNum('12.5')};\n"
        "var ok = ['a','b','c','d','e','h'].every(function(k){return C.test(cases[k]);});\n"  # 유효값은 계약 부합
        "console.log(JSON.stringify({cases:cases, contractOk:ok}));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    c = out["cases"]
    assert c["a"] == "6620", c        # 6,620. → 6620 (후행 점·콤마 제거)
    assert c["b"] == "6620", c        # ₩6,620. → 6620 (통화기호 제거)
    assert c["c"] == "6620" and c["d"] == "6620.00" and c["h"] == "12.5", c
    assert c["e"] == "1234", c        # 공백 천단위
    assert c["f"] == "" and c["g"] == "", c   # 빈/비숫자 → ''(가짜값 0)
    assert out["contractOk"] is True, out


# ── 알리 상세 추출 계약(Playwright, 실 kgp-extractor) ──
def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


ALI_HTML = Path("fixtures/realpages/ali-detail.html").read_text(encoding="utf-8")
ALI_URL = "https://www.aliexpress.com/item/1005006620123.html"


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_ali_detail_extraction_contract():
    from playwright.sync_api import sync_playwright
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()

        def handler(route):
            if route.request.url.split("#")[0] == ALI_URL:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=ALI_HTML)
            else:
                route.abort()
        page.route("**/*", handler)
        page.goto(ALI_URL, wait_until="domcontentloaded")
        r = page.evaluate("""(ex) => {
            (0, eval)(ex);
            const o = window.kgpExtractProduct();
            return {
                price: o.price, currency: o.currency,
                imgs: (o.images || o.gallery_images || []).length,
                options: (o.options || []).map(x => ({name: x.name, values: x.values})),
                priceMatchesContract: /^\\d+(\\.\\d+)?$/.test(o.price || ''),
            };
        }""", EX)
        b.close()
    assert r["price"] == "6620", r                          # 후행 점 정규화(6,620.→6620)
    assert r["currency"] == "KRW", r
    assert r["priceMatchesContract"] is True, r             # \d+(\.\d+)? 계약
    assert r["imgs"] >= 6, ("갤러리 과소(3장) 해소 실패", r)
    assert len(r["options"]) >= 1, ("옵션 0(options=none) 회귀", r)
    opts = {x["name"]: x["values"] for x in r["options"]}
    assert "Color" in opts and "White" in opts["Color"], ("알리 sku 옵션 추출 실패", r)
