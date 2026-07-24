"""tests/test_v71_sku_mapper.py — v71 STEP2: sku 매퍼 수리(버그② [object Object]+URL).

증상: 테무 옵션 값 = "[object Object]" + 이미지 URL — sku 스펙 객체를 통짜 문자열화(sv.map(String)).
수리: 스펙 객체에서 [축명·값 텍스트·값 이미지]를 필드로 추출. 값에 Object 문자열화·URL 금지, 값 이미지는
option_image 필드로 분리.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.122"


def test_source_contract():
    assert "function _collectSkuSpecs(so, axisMap, SPEC_KEY)" in EX
    # Object 문자열화·URL 값 금지 가드.
    assert 'val === "[object Object]"' in EX
    assert "/^https?:\\/\\//i.test(val)" in EX
    # 값 이미지는 option_image 필드로 분리.
    assert "opt.option_image = a.images" in EX
    # 옛 버그(sv.map(String)) 제거.
    assert "sv.map(String)" not in EX


def _fn(name):
    m = re.search(r"function " + re.escape(name) + r"\([^)]*\) \{.*?\n  \}", EX, re.S)
    assert m, name + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_sku_specs_structured_no_object_no_url_node():
    spec_key = re.search(r"var SPEC_KEY = (/.*?/i);", EX).group(1)
    deps = "\n".join([
        _fn("hiRes"),
        _fn("_optClean"),
        _fn("_isBadOptValue"),
        _fn("_isBadOptAxis"),
        _fn("_normKey"),        # v79 STEP3: _pickStrField 의존(과거엔 _optClean 과잉캡처로 딸려왔으나 명시화)
        _fn("_pickStrField"),
        _fn("_pickUrlField"),
        "var _OPT_AXIS_KEY = " + re.search(r"var _OPT_AXIS_KEY = (/.*?/i);", EX).group(1) + ";",
        "var _OPT_VAL_KEY = " + re.search(r"var _OPT_VAL_KEY = (/.*?/i);", EX).group(1) + ";",
        "var _OPT_VIMG_KEY = " + re.search(r"var _OPT_VIMG_KEY = (/.*?/i);", EX).group(1) + ";",
        _fn("_collectSkuSpecs"),
    ])
    harness = deps + "\n" + r"""
var SPEC_KEY = """ + spec_key + r""";
// 테무식 sku 배열: specs 배열(축명·값명·값이미지 객체).
var skus = [
  { skuId:1, price:"11235", specs:[
    { specKeyName:"색상", specValueName:"블랙", thumbUrl:"https://img.kwcdn.com/black._SS40_.jpg" },
    { specKeyName:"사이즈", specValueName:"L" } ] },
  { skuId:2, price:"11235", specs:[
    { specKeyName:"색상", specValueName:"화이트", thumbUrl:"https://img.kwcdn.com/white._SS40_.jpg" },
    { specKeyName:"사이즈", specValueName:"M" } ] },
  // 평면 sku(축명·값명 직접) + 값이미지.
  { skuId:3, price:"11235", specKeyName:"색상", specValueName:"레드", image:"https://img.kwcdn.com/red.jpg" }
];
var axisMap = {};
skus.forEach(function(so){ _collectSkuSpecs(so, axisMap, SPEC_KEY); });
// _fromJson과 동일하게 옵션 빌드.
var options = [];
Object.keys(axisMap).forEach(function(axis){
  var a = axisMap[axis];
  if (a.order.length >= 2) { var opt = { name:axis, values:a.order.slice(0,100) };
    if (Object.keys(a.images).length) opt.option_image = a.images; options.push(opt); }
});
process.stdout.write(JSON.stringify(options) + "\n");
"""
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        options = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    by = {o["name"]: o for o in options}
    # 색상 축: 값 텍스트(블랙/화이트/레드) — Object·URL 없음.
    assert "색상" in by, options
    assert by["색상"]["values"] == ["블랙", "화이트", "레드"], by["색상"]
    # 사이즈 축.
    assert "사이즈" in by and by["사이즈"]["values"] == ["L", "M"], by
    # 값 이미지는 option_image로 분리(values 오염 0).
    assert "option_image" in by["색상"], by["색상"]
    assert by["색상"]["option_image"]["블랙"].startswith("https://img.kwcdn.com/black")
    # 전 값에 "[object" / "http" 오염 0(브리프 계약).
    for o in options:
        for v in o["values"]:
            assert "[object" not in v and "http" not in v, (o["name"], v)
