"""tests/test_v43_2_bulk_accuracy.py — v43-2: 벌크 수집 정확도(27중16 누락 복구).

E-4(아마존)에 이어 제네릭 어댑터도 강화: 가격이 없어도 '상품 상세 링크'면 인식(가격만 필수였던
옛 규칙이 27중16 누락 유발). 정직: 제외 수는 벌크바에 표기.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


def test_generic_price_optional_with_detail_link():
    assert "function _kgpIsProductHref" in CS
    # v74 STEP1: 자격 = 가격 or 엄격 상품 URL(_kgpIsProductHref) — 카테고리 URL 오탐 봉인(느슨한 _kgpIsDetailHref 폐기).
    # v81 STEP4 STEP C: keep-gate 동일(둘 다 없을 때만 제외), 사유만 no-item-url/no-price로 분리.
    assert "if (!pr.price && !_kgpIsProductHref(href)) {" in CS
    assert '_kgpMarkSkip(card, _kgpIsProductHref(href) ? "no-price" : "no-item-url")' in CS
    assert "if (!pr.price) continue;" not in CS   # 옛 '가격 필수' 제거


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_generic_recovers_priceless_detail_cards():
    """27개(16 유가 + 11 무가·상세링크) → 27 인식(옛날엔 16)."""
    def fn(n):
        i = CS.index("function " + n + "(")
        j = CS.index("\n}\n", i) + 2
        return CS[i:j]
    deps = "\n".join([
        "let _kgpScannedCount=0;",
        "let _kgpExcl={ad:0,region:0,parse:0,url:0,dup:0,reco:0};function _kgpExclReset(){};function _kgpMarkSkip(){};function _kgpClearSkip(){};function _kgpSkipReset(){};var _kgpSkipStats={};",
        "const _KGP_ORIG_PRICE_RE=/x^/;const _KGP_NONPROD_RE=/(recommend|related|footer|review)/i;",
        "const _KGP_RECO_HEADING_RE=/(閲覧した商品からのおすすめ|あなたにおすすめ)/;",
        fn("_kgpInBadRegion"), fn("_kgpIsRecoRegion"), fn("_kgpPrice"), fn("_kgpBestImg"),
        fn("_kgpIsDetailHref"), fn("_kgpIsCategoryHref"), fn("_kgpIsProductHref"), fn("_kgpInNavRegion"), fn("_kgpInRecommendWidget"), fn("_kgpGenericCards"),
    ])
    harness = deps + r"""
    function mkSpec(o){
      const card={tagName:'DIV',getAttribute(){return null;},get className(){return '';},get id(){return '';},parentElement:null,
        innerText:(o.price?o.price+' ':'')+o.title, querySelector(sel){ if(/h1|h2|h3|h4|title|name/.test(sel)) return {innerText:o.title}; return null; }};
      const anchor={href:o.href, closest:(s)=>card};
      return {naturalWidth:200,naturalHeight:200,alt:o.title,src:'x.jpg',currentSrc:'',getAttribute(){return null;},
        closest:(sel)=> sel.indexOf('a[href]')>=0 ? anchor : card};
    }
    const imgs=[];
    for(let i=0;i<16;i++) imgs.push(mkSpec({title:'Priced '+i, price:'₩'+(10000+i), href:'https://temu.com/g-'+(100000+i)+'.html'}));
    for(let i=0;i<11;i++) imgs.push(mkSpec({title:'NoPrice '+i, price:'', href:'https://temu.com/g-'+(200000+i)+'.html'}));
    global.document={querySelectorAll:(s)=>s==='img'?imgs:[]};
    const out=_kgpGenericCards();
    console.log(JSON.stringify({products:out.length, priced:out.filter(c=>c.price).length}));
    """
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    import json
    o = json.loads(res.stdout.strip())
    assert o["products"] == 27      # 옛날 16 → 27
    assert o["priced"] == 16


def test_non_product_links_still_excluded():
    """가격도 상세링크도 아닌 타일은 계속 제외(오탐 방지)."""
    def fn(n):
        i = CS.index("function " + n + "(")
        j = CS.index("\n}\n", i) + 2
        return CS[i:j]
    import shutil as _sh
    if _sh.which("node") is None:
        pytest.skip("node 미설치")
    deps = "\n".join([
        "let _kgpScannedCount=0;",
        "let _kgpExcl={ad:0,region:0,parse:0,url:0,dup:0,reco:0};function _kgpExclReset(){};function _kgpMarkSkip(){};function _kgpClearSkip(){};function _kgpSkipReset(){};var _kgpSkipStats={};",
        "const _KGP_ORIG_PRICE_RE=/x^/;const _KGP_NONPROD_RE=/(recommend|related|footer|review)/i;",
        "const _KGP_RECO_HEADING_RE=/(閲覧した商品からのおすすめ|あなたにおすすめ)/;",
        fn("_kgpInBadRegion"), fn("_kgpIsRecoRegion"), fn("_kgpPrice"), fn("_kgpBestImg"),
        fn("_kgpIsDetailHref"), fn("_kgpIsCategoryHref"), fn("_kgpIsProductHref"), fn("_kgpInNavRegion"), fn("_kgpInRecommendWidget"), fn("_kgpGenericCards"),
    ])
    harness = deps + r"""
    function mkSpec(o){
      const card={tagName:'DIV',getAttribute(){return null;},get className(){return '';},get id(){return '';},parentElement:null,
        innerText:o.title, querySelector(){return {innerText:o.title};}};
      const anchor={href:o.href, closest:(s)=>card};
      return {naturalWidth:200,naturalHeight:200,alt:o.title,src:'x.jpg',currentSrc:'',getAttribute(){return null;},
        closest:(sel)=> sel.indexOf('a[href]')>=0 ? anchor : card};
    }
    // 가격 없음 + 상세링크 아님(카테고리/브랜드 배너 링크) → 제외.
    const imgs=[mkSpec({title:'브랜드관 배너', href:'https://temu.com/category/home'}),
               mkSpec({title:'이벤트 페이지', href:'https://temu.com/event/sale'})];
    global.document={querySelectorAll:(s)=>s==='img'?imgs:[]};
    console.log(JSON.stringify({products:_kgpGenericCards().length}));
    """
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    import json
    assert json.loads(res.stdout.strip())["products"] == 0
