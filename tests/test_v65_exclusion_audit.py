"""tests/test_v65_exclusion_audit.py — v65 STEP2: 제외 43 감사.

제외 사유별 카운트 분해([광고 / 카드 파싱 실패 / URL 추출 실패 / 중복 / 비상품영역]) — 확장 디버그
패널에 표기. '제외 (광고 등)' 뭉뚱그림 금지. node로 실제 어댑터 실행해 사유별 카운트 실증.
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
    assert MANIFEST["version"] == "1.5.86"


def test_source_contract():
    assert "let _kgpExcl = { ad: 0, region: 0, parse: 0, url: 0, dup: 0, reco: 0 }" in CS
    assert "function _kgpExclReset()" in CS
    assert "_kgpExclReset();" in CS                       # 스캔마다 초기화
    # kgpDetectState가 excl 노출.
    assert "excl: _kgpExcl" in CS
    # 각 사유 증가 지점.
    assert "_kgpExcl.parse++" in CS and "_kgpExcl.dup++" in CS
    assert "_kgpExcl.url++" in CS and "_kgpExcl.region++" in CS and "_kgpExcl.ad++" in CS
    # 팝업 패널이 사유 분해 표기(뭉뚱그림 금지).
    assert "파싱실패" in POPUP_JS and "URL실패" in POPUP_JS and "중복" in POPUP_JS


def _extract(fn):
    m = re.search(r"function " + fn + r"\([^)]*\) \{.*?\n\}", CS, re.S)
    assert m, fn + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_amazon_exclusion_breakdown_node():
    """실제 _kgpAmazonCards 실행 → 제외 사유별 카운트 검증(유효3 + 무효ASIN1 + 광고1 + 중복1)."""
    fns = (_extract("_kgpInBadRegion") + "\n" + _extract("_kgpAmazonSponsored") + "\n"
           + _extract("_kgpBestImg") + "\n" + _extract("_kgpPrice") + "\n" + _extract("_kgpAmazonCards") + "\n")
    harness = (
        "let _kgpScannedCount=0;\n"
        "let _kgpExcl={ad:0,region:0,parse:0,url:0,dup:0,reco:0};\n"
        "function _kgpExclReset(){_kgpExcl={ad:0,region:0,parse:0,url:0,dup:0,reco:0};}\n"
        "function _kgpIsRecoRegion(){return false;}\n"
        "global.location={origin:'https://www.amazon.com'};\n"
        "function mkImg(){return {alt:'상품',src:'https://img/x.jpg',currentSrc:'',getAttribute:function(){return null;}};}\n"
        "function card(asin, opts){opts=opts||{};\n"
        "  var img=mkImg();\n"
        "  var titleEl={innerText:opts.title!==undefined?opts.title:'제품 A',textContent:''};\n"
        "  var sponsoredEl=opts.sponsored?{}:null;\n"
        "  var anchor=asin?{href:'https://www.amazon.com/dp/'+asin}:null;\n"
        "  return {\n"
        "    getAttribute:function(k){return k==='data-asin'?(asin||''):null;},\n"
        "    parentElement:null,\n"
        "    querySelector:function(sel){\n"
        "      if(/sponsored/i.test(sel)) return sponsoredEl;\n"
        "      if(/dp\\//.test(sel)||/a-link/.test(sel)||sel==='h2 a') return anchor;\n"
        "      if(/img/.test(sel)) return img;\n"
        "      if(/h2|title|a-size/.test(sel)) return (opts.title===''?null:titleEl);\n"
        "      return null;\n"
        "    },\n"
        "    querySelectorAll:function(){return [];},\n"
        "    className:'', tagName:'DIV', id:'', innerText:'₩12,000'\n"
        "  };\n"
        "}\n"
        # 유효 상품 3(A,B,C) + 무효 ASIN 1(파싱실패) + 광고 1(유효+sponsored) + 중복 1(A 재등장).
        "var c1=card('B000000001');\n"
        "var c2=card('B000000002');\n"
        "var c3=card('B000000003');\n"
        "var cInvalid=card('SHORT');\n"                 # ASIN 형식 불량 → parse++
        "var cAd=card('B000000004',{sponsored:true});\n"  # 광고(유효) → ad++
        "var cDup=card('B000000001');\n"                # 같은 href → dup++
        "global.document={querySelectorAll:function(){return [c1,c2,c3,cInvalid,cAd,cDup];}};\n"
        + fns +
        "_kgpExclReset();\n"
        "var cards=_kgpAmazonCards();\n"
        "console.log(JSON.stringify({count:cards.length, excl:_kgpExcl}));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    # 인식: A,B,C + 광고(유효 ASIN이라 카드로 잡힘) = 4.
    assert out["count"] == 4, out
    assert out["excl"]["parse"] == 1, out    # 무효 ASIN 1
    assert out["excl"]["dup"] == 1, out      # 중복 1
    assert out["excl"]["ad"] == 1, out       # 광고 1(제외 아님·카운트만)
