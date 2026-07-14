"""tests/test_v70_option_variants.py — v70 STEP2: 옵션 수량 제외 + 트위스터 변형 수집(현행범 버그②).

증상: 옵션 = "Quantity 1~30"(수량 드롭다운을 옵션으로 오인) + 색상 변형(twister) 미수집.
수리: ①수량(Quantity/수량/qty) 셀렉터·라벨·순수 1..N 정수열 명시 제외
②아마존 twister(#inline-twister·variation_) 색·사이즈를 img[alt]/aria-label로 수집(Click to select 접두 제거).
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
    assert MANIFEST["version"] == "1.5.80"


def test_source_contract():
    # 수량 제외 규약.
    assert "var QTY_RE =" in EX
    assert "function _looksLikeQty(vals)" in EX
    assert "if (QTY_RE.test(lbl) || QTY_RE.test(selId) || _looksLikeQty(vals)) continue;" in EX
    # 트위스터 값 정제(img[alt]·aria-label 우선, Click to select 접두 제거) + 구형 variation_ 지원.
    assert "var _twVal = function (el)" in EX and "var _twClean = function (s)" in EX
    assert 'el.querySelector("img[alt]")' in EX
    assert '[id^="variation_"]' in EX
    assert "click to select" in EX.lower()


def _fn(name):
    m = re.search(r"function " + re.escape(name) + r"\([^)]*\) \{.*?\n  \}", EX, re.S)
    assert m, name + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_quantity_excluded_color_collected_node():
    """수량 드롭다운(1~30)은 옵션 아님 + 색상 트위스터 4값(BENKS류)은 색상=4값 수집."""
    opt_label = re.search(r"var OPT_LABEL = (/.*/i);", EX).group(1)
    qty_re = re.search(r"var QTY_RE = (/.*/i);", EX).group(1)
    deps = "\n".join([
        "var OPT_LABEL = " + opt_label + ";",
        "var QTY_RE = " + qty_re + ";",
        _fn("_looksLikeQty"),
        "function _nonProdRegion(){return false;}",
        "function _galleryExcluded(){return false;}",
        _fn("_domOptions"),
    ])
    harness = deps + "\n" + r"""
function mkEl(o){
  o.getAttribute = o.getAttribute || function(k){ return (o.attrs && o.attrs[k]) || null; };
  o.querySelector = o.querySelector || function(){ return null; };
  o.querySelectorAll = o.querySelectorAll || function(){ return []; };
  o.closest = o.closest || function(){ return null; };
  o.id = o.id || "";
  return o;
}
// 수량 select: aria-label "Quantity", options 1..30.
var qtyOpts = [];
for (var i=1;i<=30;i++) qtyOpts.push({ textContent: String(i) });
var qtySelect = mkEl({ id:"quantity", options:qtyOpts,
  getAttribute:function(k){ return k==="aria-label" ? "Quantity" : (k==="name"?"quantity":null); } });

// 색상 트위스터 row: id inline-twister-row-color_name, 4개 스와치(img alt).
function swatch(color){
  return mkEl({
    querySelector:function(s){ return /img/.test(s) ? { getAttribute:function(k){ return k==="alt"?color:null; } } : null; },
    getAttribute:function(k){ return k==="title" ? ("Click to select " + color) : null; },
    innerText:"", textContent:""
  });
}
var swatches = ["Black","Navy","Red","Green"].map(swatch);
var colorRow = mkEl({ id:"inline-twister-row-color_name",
  querySelector:function(s){ return /form-label|label/.test(s) ? { innerText:"Color:", textContent:"Color:" } : null; },
  querySelectorAll:function(s){ return /swatch|li|radio|asin|button|toggle/.test(s) ? swatches : []; } });

global.document = {
  querySelectorAll:function(sel){
    if (sel === "select") return [qtySelect];
    if (sel.indexOf("inline-twister-row-") >= 0 || sel.indexOf("variation_") >= 0) return [colorRow];
    return [];
  },
  querySelector:function(){ return null; }
};
var out = _domOptions();
process.stdout.write(JSON.stringify(out) + "\n");
"""
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    by = {o["name"]: o["values"] for o in out}
    # 수량은 어떤 옵션에도 안 들어감(정직 — 옵션 아님).
    assert "수량" not in by, out
    assert not any(o["values"] == [str(i) for i in range(1, 31)] for o in out), out
    # 색상 트위스터 4값 수집(Click to select 접두 제거된 순수 색상명).
    assert "색상" in by, out
    assert by["색상"] == ["Black", "Navy", "Red", "Green"], out


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_looks_like_qty_node():
    deps = _fn("_looksLikeQty")
    harness = deps + "\n" + r"""
var cases = {
  seq30: _looksLikeQty(["1","2","3","4"]),      // 수량
  from0: _looksLikeQty(["0","1","2"]),           // 수량(0시작)
  colors: _looksLikeQty(["Black","Navy"]),       // 색상(비수량)
  sizes: _looksLikeQty(["S","M","L"]),           // 사이즈(비수량)
  gap: _looksLikeQty(["1","3","5"]),             // 비연속(수량 아님)
  single: _looksLikeQty(["1"])                    // 1개(무의미)
};
process.stdout.write(JSON.stringify(cases) + "\n");
"""
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        c = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert c["seq30"] is True and c["from0"] is True
    assert c["colors"] is False and c["sizes"] is False
    assert c["gap"] is False and c["single"] is False
