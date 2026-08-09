"""tests/test_v70_price_precision.py — v70 STEP1: 가격 정밀도(현행범 버그①).

증상: 아마존 광고 위젯의 정가(a-price a-text-price) 32.99가 실판매가(buybox priceToPay) 29.99를 이김.
근원: 취소선 제외가 a-text-price 클래스를 안 거름 + 폰트 크기 우선순위로 큰 폰트 광고가 buybox를 이김.
수리: ①어댑터 buybox 스코프(#apex_desktop·corePrice·priceToPay) 최우선 ②a-text-price(정가) 배제
③광고·추천 컨테이너(sims/multi-brand/video) 제외 ④전역 휴리스틱 폰트크기는 동률 보조로 강등.
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
    assert MANIFEST["version"] == "1.5.137"


def test_source_contract():
    # buybox 스코프 최우선 함수 + 스코프 셀렉터.
    assert "function _buyboxPrice()" in EX
    assert "#apex_desktop" in EX and "corePrice_desktop" in EX and ".priceToPay" in EX
    assert "var bx = _buyboxPrice();" in EX and "if (bx) return bx;" in EX
    # a-text-price(아마존 정가) 배제.
    assert "function _isListPriceNode(el)" in EX
    assert "a-text-price" in EX
    assert "if (_isListPriceNode(el)) continue;" in EX
    # 광고·추천 컨테이너 패턴(sims/multi-brand/video) 추가.
    assert "sims" in EX and "multi[-_ ]?brand" in EX
    # 폰트크기 강등: 문서 순서(ord) 우선, 폰트는 동률 보조.
    assert "(a.ord - b.ord) || (b.fs - a.fs)" in EX


def _fn(name):
    m = re.search(r"function " + re.escape(name) + r"\([^)]*\) \{.*?\n  \}", EX, re.S)
    assert m, name + " 추출 실패"
    return m.group(0)


def _const(pattern):
    m = re.search(pattern, EX, re.S)
    assert m, pattern + " 상수 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_buybox_wins_over_ad_text_price_node():
    """실아마존 구조 재현: sims 광고 위젯의 a-text-price 32.99 vs buybox priceToPay 29.99 → 29.99 채택."""
    deps = "\n".join([
        _const(r"var CODE = \{.*?\};"),
        "var PRICE_RE = " + re.search(r"var PRICE_RE = (/.*/i);", EX).group(1) + ";",
        _fn("_sym"),
        _fn("parsePriceStr"),
        _fn("_clsId"),
        _fn("_isListPriceNode"),
        _fn("_nonProdRegion"),
        _fn("_priceOriginal"),
        "var NONPRICE = " + re.search(r"var NONPRICE = (/.*/i);", EX).group(1) + ";",
        _fn("_nonPriceCtx"),
        _fn("_nodePath"),
        _fn("_inCartScope"),      # v84.1 STEP A: 장바구니/사이드 위젯 가격 배제(_domPrice 의존)
        _fn("_composedPrice"),
        _fn("_buyboxPrice"),
        _fn("_domPrice"),
    ])
    harness = deps + "\n" + r"""
// ── mock DOM 헬퍼 ──
function mkEl(o){
  o.className = o.className || "";
  o.id = o.id || "";
  o.tagName = o.tagName || "SPAN";
  o.textContent = (o.textContent == null ? "" : o.textContent);
  o.parentElement = o.parentElement || null;
  o.getAttribute = o.getAttribute || function(k){ return (o.attrs && o.attrs[k]) || null; };
  o.querySelectorAll = o.querySelectorAll || function(){ return []; };
  return o;
}
global.getComputedStyle = function(el){ return { fontSize: (el.fs||0)+"px", textDecorationLine: el.deco||"none" }; };
global.console = { log: function(){} };

// buybox 스코프: #corePrice_desktop > span.priceToPay "$29.99"
var buyboxPrice = mkEl({ className:"a-price priceToPay", textContent:"$29.99", fs:28 });
var buyboxScope = mkEl({ id:"corePrice_desktop", className:"corePrice",
  querySelectorAll:function(sel){ return [buyboxPrice]; } });
buyboxPrice.parentElement = buyboxScope;

// 광고 위젯: #sims-consolidated ... span.a-price.a-text-price "$32.99" (정가, 큰 폰트)
var adScope = mkEl({ id:"sims-consolidated-2_feature_div", className:"sims-consolidated" });
var adPrice = mkEl({ className:"a-price a-text-price", textContent:"$32.99", fs:40, parentElement:adScope });

// 일반(스코프 밖) 실판매가 노드: span.a-price "$29.99" (문서 뒤쪽·작은 폰트)
var plainScope = mkEl({ id:"corePriceDisplay", className:"corePrice" });
var plainPrice = mkEl({ className:"a-price", textContent:"$29.99", fs:22, parentElement:plainScope });

function makeDoc(scopes, globalNodes){
  return {
    querySelectorAll:function(sel){
      if (/apex_desktop|corePrice_desktop|buybox|priceblock|Accordion|qualifiedBuybox/.test(sel)) return scopes;
      // 전역 휴리스틱 가격 셀렉터
      return globalNodes;
    },
    querySelector:function(){ return null; }
  };
}

// 케이스1: buybox 스코프 성공 → 29.99 (광고 32.99 무시).
global.document = makeDoc([buyboxScope], [adPrice, plainPrice]);
var r1 = _domPrice();

// 케이스2: buybox 스코프 없음(빈) → 전역 휴리스틱. a-text-price 32.99 배제 + sims 광고 제외 → 29.99.
global.document = makeDoc([], [adPrice, plainPrice]);
var r2 = _domPrice();

console.log = function(){};
process.stdout.write(JSON.stringify({ r1:r1, r2:r2 }) + "\n");
"""
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    # 케이스1: buybox 스코프가 29.99 채택(광고 32.99 무시).
    assert out["r1"] and out["r1"]["price"] == "29.99", out
    assert out["r1"].get("scope") is True, out
    # 케이스2: 전역 폴백도 a-text-price 32.99 배제 → 29.99.
    assert out["r2"] and out["r2"]["price"] == "29.99", out
