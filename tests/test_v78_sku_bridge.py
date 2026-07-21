"""tests/test_v78_sku_bridge.py — v78 STEP1: sku→옵션 브리지.

실기기 진단(테무 skus:8·options:0) 근본: sku 스펙 키가 underscore(spec_key/spec_value)라 speckey/specvalue
패턴에 안 걸려 변환 단절. 수리: 키 정규화(_normKey — _·-·공백 제거 후 매칭) + 단일 변환 함수 _skusToOptions
(하네스·확장 경로 통일). 계약: skus에 스펙 변형이 있으면 options>0.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
HT = Path("fixtures/realpages/temu-sku-underscore.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.109"


# ── source-contract: 키 정규화 + 단일 변환 함수 ──
def test_sku_bridge_source():
    assert "function _normKey(k)" in EX
    assert 'replace(/[_\\-\\s]/g, "")' in EX
    assert "re.test(_normKey(k))" in EX                       # _pickStrField/_pickUrlField 정규화 적용
    assert "function _skusToOptions(axisMap, skus)" in EX
    assert "res.options = _skusToOptions(axisMap, res.skus);" in EX   # 단일 변환 경로


# ── node: underscore 키 sku → 옵션(색상·사이즈) ──
@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_normkey_underscore_node():
    def grab(sig, end="\n  }"):
        i = EX.index(sig); j = EX.index(end, i) + len(end); return EX[i:j]
    src = (grab("function _optClean(") + "\n" +
           "var _OPT_AXIS_KEY = " + _re_of("_OPT_AXIS_KEY") + ";\n" +
           "var _OPT_VAL_KEY = " + _re_of("_OPT_VAL_KEY") + ";\n" +
           grab("function _normKey(k)") + "\n" +
           grab("function _pickStrField(") + "\n")
    harness = (src +
        "var so={sku_id:1, spec_key:'색상', spec_value:'베이지'};\n"
        "var nm=_pickStrField(so,_OPT_AXIS_KEY,null); var vl=_pickStrField(so,_OPT_VAL_KEY, nm?nm.k:null);\n"
        "console.log(JSON.stringify({axis:nm&&nm.v, val:vl&&vl.v}));\n")
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["axis"] == "색상", out          # underscore 키 spec_key 인식
    assert out["val"] == "베이지", out          # spec_value 인식


def _re_of(name):
    import re
    m = re.search(r"var " + name + r" = (/[^\n]+/i);", EX)
    assert m, name
    return m.group(1)


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_temu_underscore_skus_yield_options():
    """실 kgp-extractor: 테무 underscore sku(skus>0) → options>0(색상·사이즈) + 가격 40603 KRW."""
    from playwright.sync_api import sync_playwright
    url = "https://www.temu.com/kr/cat-tower-g-1.html"
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
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=HT)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(url, wait_until="domcontentloaded")
        res = page.evaluate("(ex)=>{ (0,eval)(ex); return window.kgpExtractProduct(); }", EX)
        b.close()

    # 계약: skus>0 → options>0.
    assert len(res.get("skus") or []) >= 8, res.get("skus")
    opts = {o["name"]: o["values"] for o in (res.get("options") or [])}
    assert opts, ("skus>0인데 options=0(변환 단절)!", res.get("skus"), res.get("options"))
    assert "색상" in opts and set(opts["색상"]) == {"베이지", "그레이", "브라운", "화이트"}, opts
    assert "사이즈" in opts and set(opts["사이즈"]) == {"대형", "중형"}, opts
    # 옵션 값 오염 금지(URL·Object).
    for vals in opts.values():
        for v in vals:
            assert "[object" not in v and "http" not in v, v
    assert res.get("price") == "40603" and res.get("currency") == "KRW", res
