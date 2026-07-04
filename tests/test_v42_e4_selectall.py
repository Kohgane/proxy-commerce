"""tests/test_v42_e4_selectall.py — v42 E-4: 전체선택 누락(24 중 16) 정확도.

증상: 벌크바 '전체 24개 중 상품 16개' — 8개를 상품으로 인식 못함(가격 없는 카드·앵커 변형).
수리: 유효 ASIN(비스폰서)이면 상품 — href ASIN 폴백, 제목/이미지 셀렉터 확장, 가격 선택.
정직: 제외(광고 등) 수를 눈에 보이게.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


def test_href_falls_back_to_asin():
    assert 'location.origin + "/dp/" + asin' in CS


def test_price_is_optional_title_or_image_required():
    # 가격 필수 제거 → 제목·이미지 둘 다 없을 때만 제외.
    assert "if (!title && !img) return;" in CS
    assert "if (!img || !titleEl || !pr.price) return;" not in CS   # 옛 엄격 조건 제거


def test_title_selectors_broadened():
    assert 'data-cy="title-recipe"' in CS
    assert ".a-size-base-plus" in CS


def test_honest_excluded_count_shown():
    assert "제외 ${miss}(광고 등)" in CS


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_amazon_adapter_recovers_priceless_cards():
    """24개(가격 있는 16 + 가격 없는 8) → 전부 상품 인식(8개 누락 복구). 스폰서는 제외."""
    def fn(name):
        i = CS.index("function " + name + "(")
        j = CS.index("\n}\n", i) + 2
        return CS[i:j]
    deps = "\n".join([
        "let _kgpScannedCount = 0;",
        "const _KGP_ORIG_PRICE_RE=/x^/; const _KGP_NONPROD_RE=/(recommend|related|footer|review)/i;",
        fn("_kgpInBadRegion"), fn("_kgpAmazonSponsored"), fn("_kgpPrice"),
        fn("_kgpBestImg"), fn("_kgpAmazonCards"),
    ])
    # 최소 DOM 스텁 — Amazon 검색결과 24개(16 유가 + 8 무가) + 2 스폰서.
    harness = deps + r"""
    function mkEl(spec){
      return {
        _asin: spec.asin, _sponsored: spec.sponsored, _price: spec.price, _title: spec.title,
        tagName: 'DIV',
        getAttribute(k){ return k==='data-asin'? this._asin : (k==='class'||k==='id'? '' : null); },
        get className(){ return ''; }, get id(){ return ''; }, parentElement: null,
        querySelector(sel){
          if (this._sponsored && sel.indexOf('sponsored')>=0) return {};
          if (sel.indexOf('sponsored')>=0) return null;
          if (sel.indexOf('/dp/')>=0 || sel.indexOf('h2 a')>=0) return { href: 'https://www.amazon.com/dp/'+this._asin+'/ref=x' };
          if (sel.indexOf('img')>=0) return { src:'https://m.media-amazon.com/img/'+this._asin+'.jpg', getAttribute(){return null;}, alt:this._title, currentSrc:'' };
          if (sel.indexOf('h2')>=0 || sel.indexOf('title')>=0 || sel.indexOf('a-size')>=0) return { innerText:this._title, textContent:this._title };
          if (sel.indexOf('a-price')>=0) return this._price? { textContent: this._price } : null;
          return null;
        },
      };
    }
    const cards = [];
    for (let i=0;i<16;i++) cards.push(mkEl({asin:'B0PRC'+String(i).padStart(5,'0'), price:'$'+(10+i)+'.00', title:'Priced Item '+i}));
    for (let i=0;i<8;i++) cards.push(mkEl({asin:'B0NON'+String(i).padStart(5,'0'), price:'', title:'No-Price Item '+i}));
    for (let i=0;i<2;i++) cards.push(mkEl({asin:'B0SPN'+String(i).padStart(5,'0'), price:'$9.99', title:'Ad '+i, sponsored:true}));
    global.location = { origin: 'https://www.amazon.com' };
    global.document = { querySelectorAll: (sel) => sel.indexOf('s-search-result')>=0 ? cards : [] };
    const out = _kgpAmazonCards();
    console.log(JSON.stringify({ scanned:_kgpScannedCount, products: out.length,
      priced: out.filter(c=>c.price).length }));
    """
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    import json
    o = json.loads(res.stdout.strip())
    assert o["scanned"] == 26           # 전체(16+8+2)
    # v45 P3(최신 우선): 스폰서 상품도 포함 → 26. (E-4의 '무가 8 복구'는 유지, 스폰서 제외만 반전.)
    assert o["products"] == 26          # 유가16 + 무가8 복구 + 스폰서2 포함
    assert o["priced"] == 18            # 가격 있는 건 유가16 + 스폰서2(가격 있음)
