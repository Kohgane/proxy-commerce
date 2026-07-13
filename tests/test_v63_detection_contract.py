"""tests/test_v63_detection_contract.py — v63 STEP3: 회귀 자물쇠.

STEP1·2 결과를 계약으로 고정한다. 어댑터/제네릭 셀렉터·필드 세트가 무단 변경되면 이 계약이
깨져 CI 게이트가 막는다(어댑터 셀렉터 변경 시 계약 테스트 필수 갱신). 카드 감지 스냅샷은
node로 실제 detection 파이프라인을 mock DOM에 돌려 고정한다.
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

# ── 필드 계약(파이썬) — 필드 세트 무단 변경 방지 ──


def test_collect_status_field_contract():
    from src.collectors.collect_status import FIELDS, TOTAL
    keys = [k for k, _, _ in FIELDS]
    assert keys == ["price", "images", "options", "detail", "reviews"], keys
    assert TOTAL == 5


def test_gate_field_contract():
    from src.collectors.field_loss_matrix import GATE_FIELDS, COMPLETE_THRESHOLD, DEFAULT_MARKET_DOMAINS
    assert GATE_FIELDS == ["title", "price", "images3", "options", "detail"], GATE_FIELDS
    assert COMPLETE_THRESHOLD == 0.90
    assert {"amazon", "temu"} <= DEFAULT_MARKET_DOMAINS


# ── 셀렉터 계약(소스 핀) — 변경 시 의도적으로 이 테스트를 갱신해야 함 ──


def test_adapter_selector_contract():
    # 아마존 어댑터 셀렉터(유효 ASIN 카드).
    assert '[data-component-type="s-search-result"], div[data-asin]:not([data-asin=""])' in CS
    # 제네릭 앵커 폴백 컨테이너 셀렉터(테무 SPA).
    assert "[class*='card' i],[class*='item' i],[class*='product' i],[class*='goods' i]" in CS
    # 상세 URL 판정(가격 없는 카드의 대체 신호).
    assert "function _kgpIsDetailHref(href)" in CS
    for tok in ["/dp/", "goods", "product"]:
        assert tok in CS


def test_generic_first_ordering_contract():
    fc = re.search(r"function kgpFindCards\(\) \{.*?\n\}", CS, re.S).group(0)
    assert fc.index("_kgpGenericCards()") < fc.index("_kgpAmazonCards()")
    assert "_kgpMergeCards(generic, adapter)" in fc


def _extract(fn):
    m = re.search(r"function " + fn + r"\([^)]*\) \{.*?\n\}", CS, re.S)
    assert m, fn + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_detection_snapshot_node():
    """실 detection 파이프라인(kgpFindCards)을 mock DOM에 돌려 스냅샷 고정.

    카드1=테무식(이미지가 <a> 미포함 → 카드 컨테이너 상세앵커로 폴백), 카드2=요시다식(정상).
    둘 다 감지 = STEP1 앵커 폴백 + 제네릭-first가 실제로 동작함을 못박음.
    """
    fns = "".join(_extract(f) + "\n" for f in [
        "_kgpCardKey", "_kgpMergeCards", "_kgpIsDetailHref",
        "_kgpInBadRegion", "_kgpBestImg", "_kgpPrice", "_kgpGenericCards", "kgpFindCards",
    ])
    harness = (
        "let _kgpScannedCount = 0;\n"
        "let _kgpLastDetect = { generic:0, adapter:0, merged:0, adapterMatched:false };\n"
        "function _kgpAmazonCards(){ return []; }\n"           # temu 호스트라 미호출(안전 스텁)
        "function mk(p){p=p||{};p.getAttribute=p.getAttribute||function(){return null;};"
        "p.querySelector=p.querySelector||function(){return null;};"
        "p.querySelectorAll=p.querySelectorAll||function(){return [];};"
        "p.closest=p.closest||function(){return null;};"
        "if(!('parentElement' in p))p.parentElement=null;"
        "if(!('className' in p))p.className='';if(!('tagName' in p))p.tagName='DIV';if(!('id' in p))p.id='';return p;}\n"
        # 카드1: 테무식 — 이미지가 <a>로 안 감싸임, 컨테이너에 상세 앵커.
        "var anchor1=mk({href:'https://www.temu.com/g-123456.html'});\n"
        "var card1=mk({tagName:'DIV',className:'goods-card',innerText:'무선 이어폰 \\u20a912,000'});\n"
        "card1.querySelectorAll=function(sel){return /a\\[href\\]/.test(sel)?[anchor1]:[];};\n"
        "card1.querySelector=function(sel){return /h1|h2|h3/.test(sel)?mk({innerText:'무선 이어폰'}):null;};\n"
        "var img1=mk({naturalWidth:200,naturalHeight:200,width:200,height:200,alt:'무선 이어폰',src:'https://img.temu.com/a.jpg',currentSrc:''});\n"
        "img1.closest=function(sel){if(/a\\[href\\]/.test(sel))return null;return card1;};\n"
        # 카드2: 요시다식 — 정상(이미지가 앵커에 감싸임).
        "var anchor2=mk({href:'https://yoshidakaban.com/products/bag-1'});\n"
        "var card2=mk({tagName:'DIV',className:'product-item',innerText:'가방 \\u00a58,000'});\n"
        "anchor2.closest=function(sel){return /li,article,div/.test(sel)?card2:null;};\n"
        "card2.querySelectorAll=function(sel){return /a\\[href\\]/.test(sel)?[anchor2]:[];};\n"
        "card2.querySelector=function(sel){return /h1|h2|h3/.test(sel)?mk({innerText:'가죽 숄더백'}):null;};\n"
        "var img2=mk({naturalWidth:300,naturalHeight:300,width:300,height:300,alt:'가죽 숄더백',src:'https://img.yoshida.com/b.jpg',currentSrc:''});\n"
        "img2.closest=function(sel){if(/a\\[href\\]/.test(sel))return anchor2;return card2;};\n"
        "global.document={querySelectorAll:function(sel){return sel.trim()==='img'?[img1,img2]:[];},querySelector:function(){return null;}};\n"
        "global.location={hostname:'www.temu.com',href:'https://www.temu.com/search?q=x',origin:'https://www.temu.com'};\n"
        + fns +
        "var cards=kgpFindCards();\n"
        "console.log(JSON.stringify({count:cards.length,urls:cards.map(function(c){return c.url;}),"
        "currencies:cards.map(function(c){return c.currency;}),detect:_kgpLastDetect}));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    # 스냅샷: 두 카드 모두 감지(테무식 앵커폴백 포함), 제네릭 경로, 어댑터 미스.
    assert out["count"] == 2, out
    assert "https://www.temu.com/g-123456.html" in out["urls"], out    # 앵커 폴백으로 잡힘
    assert "https://yoshidakaban.com/products/bag-1" in out["urls"], out
    assert "KRW" in out["currencies"] and "JPY" in out["currencies"], out
    assert out["detect"]["generic"] == 2 and out["detect"]["adapterMatched"] is False, out
