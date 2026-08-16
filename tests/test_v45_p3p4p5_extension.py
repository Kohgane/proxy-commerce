"""tests/test_v45_p3p4p5_extension.py — v45 P3·P4·P5 확장 오버레이 견고화.

P3: 수집 버튼이 카드마다 있다 없다 → 아마존 셀렉터를 유효 data-asin 카드 전부로 넓히고
    스폰서 상품도 포함(태깅만). 비-상품 미디어(ASIN 없음)는 여전히 제외.
P4: 벌크바 위치 고정 → position:fixed top:12px left:50% translateX(-50%) z-index max +
    <html> 직속 마운트(body transform 간섭 회피).
P5: 우측 FAB 깜빡임 → <html> 직속 마운트(본문 재렌더 생존) + MutationObserver 재부착(디바운스).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

EXT = Path("extensions/chrome-collector")
CS = (EXT / "content_script.js").read_text(encoding="utf-8")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))


# ── P3 ────────────────────────────────────────────────────────────────────────
def test_p3_selector_broadened_and_sponsored_tagged():
    assert 'div[data-asin]:not([data-asin=""])' in CS          # 셀렉터 확장
    assert "if (_kgpAmazonSponsored(el)) return" not in CS      # 스폰서 제외 제거
    assert "sponsored: sponsored" in CS                         # 태깅
    assert "/^[A-Z0-9]{10}$/.test(asin)" in CS                  # 비-상품(ASIN 없음) 여전히 제외


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_p3_amazon_cards_includes_sponsored_excludes_media():
    """mock 검색 DOM: 유효 ASIN 상품(일반+변형레이아웃+스폰서) 전부 인식, ASIN 없는 미디어 제외."""
    i = CS.index("function _kgpAmazonSponsored")
    j = CS.index("function _kgpIsDetailHref")
    block = CS[i:j]   # _kgpAmazonSponsored + _kgpAmazonCards
    harness = block + r"""
    let _kgpScannedCount = 0;
    let _kgpExcl={ad:0,region:0,parse:0,url:0,dup:0,reco:0};function _kgpExclReset(){};function _kgpMarkSkip(){};function _kgpClearSkip(){};function _kgpSkipReset(){};var _kgpSkipStats={};
    function _kgpInBadRegion(el){ return !!el.__bad; }
    function _kgpIsRecoRegion(el){ return !!el.__reco; }
    function _kgpPrice(t){ return t && /\d/.test(t) ? {price:'10.00',currency:'USD'} : {price:'',currency:''}; }
    function _kgpBestImg(img){ return img ? img.src : ''; }
    function mkCard(o){
      return {
        __bad: !!o.bad,
        getAttribute: (k)=> k==='data-asin' ? (o.asin||'') : null,
        parentElement: { closest: ()=> null },
        querySelector: (sel)=>{
          if (/sponsored|Sponsored/.test(sel)) return o.sponsored ? {} : null;
          if (/a-price/.test(sel)) return o.price ? {textContent:o.price, querySelector:()=>({textContent:o.price})} : null;
          if (/\/dp\/|h2 a|a-link-normal/.test(sel)) return {href:'https://www.amazon.com/dp/'+(o.asin||'x')};
          if (/img/.test(sel)) return o.img===false ? null : {alt:o.title, src:'https://img/'+(o.asin||'x')+'.jpg', currentSrc:'', getAttribute:()=>null};
          if (/h2|title|a-size/.test(sel)) return {innerText:o.title, textContent:o.title};
          return null;
        }
      };
    }
    const cards = [];
    for (let k=0;k<16;k++) cards.push(mkCard({asin:'B0'+String(k).padStart(8,'0'), title:'상품 '+k, price:'$10'}));   // 일반 16
    for (let k=0;k<3;k++)  cards.push(mkCard({asin:'B1'+String(k).padStart(8,'0'), title:'변형 '+k}));                 // 변형(가격 없음) 3
    for (let k=0;k<2;k++)  cards.push(mkCard({asin:'B2'+String(k).padStart(8,'0'), title:'스폰서 '+k, sponsored:true, price:'$9'})); // 스폰서 2
    cards.push(mkCard({asin:'', title:'Amazon Music'}));       // 미디어(ASIN 없음)
    cards.push(mkCard({asin:'amazon-app', title:'App'}));      // 위젯(비정상 ASIN)
    global.location = { origin:'https://www.amazon.com', hostname:'www.amazon.com' };
    global.document = {
      querySelectorAll: (sel)=> (sel.indexOf('data-asin')>=0 || sel.indexOf('s-search-result')>=0) ? cards : [],
    };
    const out = _kgpAmazonCards();
    console.log(JSON.stringify({ total: out.length, sponsored: out.filter(c=>c.sponsored).length, scanned: _kgpScannedCount,
                                 media: out.filter(c=>/Music|App/.test(c.title)).length }));
    """
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    o = json.loads(res.stdout.strip())
    assert o["total"] == 21, o          # 16 일반 + 3 변형 + 2 스폰서 (미디어 2 제외)
    assert o["sponsored"] == 2, o       # 스폰서 상품 포함
    assert o["media"] == 0, o           # ASIN 없는 미디어/위젯 제외
    assert o["scanned"] == 23, o        # 전체 스캔(정직 카운트)엔 미디어 포함


# ── P4 ────────────────────────────────────────────────────────────────────────
def test_p4_bulk_bar_fixed_top_center_max_z():
    i = CS.index("function kgpBuildToolbar")
    blk = CS[i:i + 1200]
    assert "position:fixed" in blk and "top:12px" in blk
    assert "left:50%" in blk and "transform:translateX(-50%)" in blk
    assert "z-index:2147483647" in blk       # 최상위
    assert "_kgpMount(bar)" in CS             # <html> 직속


def test_p4p5_mount_helper_uses_documentElement():
    assert "function _kgpMount" in CS
    assert "document.documentElement || document.body" in CS


# ── P5 ────────────────────────────────────────────────────────────────────────
def test_p5_fab_documentElement_and_observer_reattach():
    assert "_kgpMount(btn)" in CS                              # FAB <html> 직속
    # FAB z-index 최상위 — v84/v86: 위치 고정 핀(_kgpPinFixed)이 mount 시 top z-index를 !important로 박고,
    #   shadow 호스트 _fabCss에도 z-index:2147483647이 있다(shadow DOM 격리 전환).
    assert '_kgpPos(el, "z-index", "2147483647")' in CS       # 핀이 최상위 z-index 강제
    assert "z-index:2147483647" in CS                          # FAB/바 스타일에 최상위 z-index 존재
    # MutationObserver가 오버레이 사라짐 감지 시 디바운스 재부착(v55 STEP5: 재판정 아닌 '재마운트 전용').
    assert "new MutationObserver" in CS
    assert "const gone =" in CS and "_remountIfGone" in CS


def test_manifest_version_bumped():
    assert MANIFEST["version"] == "1.5.146"
