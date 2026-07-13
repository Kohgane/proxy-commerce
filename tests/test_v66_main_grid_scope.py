"""tests/test_v66_main_grid_scope.py — v66 STEP1: 감지 분모를 메인 그리드로 한정.

카드 감지·카운트 대상을 메인 검색결과 그리드(.s-main-slot)로 스코프 — 추천 캐러셀·frequently-viewed·
배너 타일(메인 밖 유효 ASIN)은 분모에서 빼고 별도 카운트(_kgpExcl.reco '추천영역 n 제외'). 분모 뻥튀기 금지.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
POPUP_JS = Path("extensions/chrome-collector/popup.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.73"


def test_source_contract():
    assert "reco: 0" in CS                                    # 추천영역 카운터
    assert ".s-main-slot" in CS                               # 메인 그리드 스코프
    assert "_kgpExcl.reco++" in CS
    # 스코프를 메인 슬롯으로 한정(scope.querySelectorAll).
    assert "scope.querySelectorAll" in CS
    # 팝업/툴바에 추천 제외 표기.
    assert "추천영역 제외" in POPUP_JS
    assert "추천 제외" in CS


def _extract(fn):
    m = re.search(r"function " + fn + r"\([^)]*\) \{.*?\n\}", CS, re.S)
    assert m, fn + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_main_slot_scope_excludes_reco_node():
    """메인 슬롯 안 3 상품 + 밖(추천) 2 유효 ASIN → 감지 3, reco 2(분모 제외)."""
    fns = (_extract("_kgpInBadRegion") + "\n" + _extract("_kgpAmazonSponsored") + "\n"
           + _extract("_kgpBestImg") + "\n" + _extract("_kgpPrice") + "\n" + _extract("_kgpAmazonCards") + "\n")
    harness = (
        "let _kgpScannedCount=0;\n"
        "let _kgpExcl={ad:0,region:0,parse:0,url:0,dup:0,reco:0};\n"
        "function _kgpExclReset(){_kgpExcl={ad:0,region:0,parse:0,url:0,dup:0,reco:0};}\n"
        "global.location={origin:'https://www.amazon.com'};\n"
        "function mkImg(){return {alt:'상품',src:'https://img/x.jpg',currentSrc:'',getAttribute:function(){return null;}};}\n"
        "function card(asin){\n"
        "  var img=mkImg(); var anchor={href:'https://www.amazon.com/dp/'+asin};\n"
        "  return { getAttribute:function(k){return k==='data-asin'?asin:null;}, parentElement:null,\n"
        "    querySelector:function(sel){ if(/sponsored/i.test(sel))return null;\n"
        "      if(/dp\\//.test(sel)||sel==='h2 a')return anchor; if(/img/.test(sel))return img;\n"
        "      if(/h2|title|a-size/.test(sel))return {innerText:'제품 '+asin,textContent:''}; return null; },\n"
        "    querySelectorAll:function(){return [];}, className:'', tagName:'DIV', id:'', innerText:'$10' };\n"
        "}\n"
        "var main1=card('B000000001'), main2=card('B000000002'), main3=card('B000000003');\n"
        "var reco1=card('B00RECO001'), reco2=card('B00RECO002');\n"
        "var mainSlot={ contains:function(e){return e===main1||e===main2||e===main3;},\n"
        "  querySelectorAll:function(){return [main1,main2,main3];} };\n"
        "global.document={\n"
        "  querySelector:function(sel){ return /s-main-slot|s-search-results/.test(sel)?mainSlot:null; },\n"
        "  querySelectorAll:function(sel){ return /data-asin/.test(sel)?[main1,main2,main3,reco1,reco2]:[]; }\n"
        "};\n"
        + fns +
        "_kgpExclReset();\n"
        "var cards=_kgpAmazonCards();\n"
        "console.log(JSON.stringify({count:cards.length, scanned:_kgpScannedCount, reco:_kgpExcl.reco}));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["count"] == 3, out       # 메인 그리드 3 상품만 감지
    assert out["scanned"] == 3, out     # 분모 = 메인 3(추천 2 미포함, 뻥튀기 금지)
    assert out["reco"] == 2, out        # 추천영역 2 별도 카운트
