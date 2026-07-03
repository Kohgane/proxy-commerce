"""tests/test_v44_img_detail_extract.py — 이미지·상세 클릭시점 추출(가격과 동일 방식).

서버 사후 크롤 금지 → 확장이 렌더 DOM에서 직접. 아마존: #imgTagWrapperId 고해상·#altImages 원본·
#feature-bullets·#productDescription·#aplus. Temu: 캐러셀·상세. 갤러리/상세 2버킷.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


def test_source_has_site_pdp_and_hires():
    assert "function _kgpSitePdp" in CS
    assert "function _kgpAmazonHiRes" in CS
    # 아마존 셀렉터
    for sel in ("#imgTagWrapperId", "data-old-hires", "data-a-dynamic-image", "#altImages",
                "#feature-bullets", "#productDescription", "#aplus"):
        assert sel in CS, sel
    # 통합: 사이트 갤러리/상세를 버킷에 병합 + 상세는 사이트 우선.
    assert "const _site = _kgpSitePdp();" in CS
    assert "_site.gallery.forEach" in CS and "_site.detail.forEach" in CS
    assert "_site.description" in CS


def test_hires_strips_amazon_size_token():
    i = CS.index("function _kgpAmazonHiRes")
    j = CS.index("\n}\n", i) + 2
    assert ".replace(/\\._[A-Za-z0-9,_-]+_\\.(jpg|jpeg|png|gif|webp)/i" in CS[i:j]


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_amazon_pdp_extraction_behavioral():
    """mock 아마존 PDP → 갤러리(고해상·크기토큰 제거)·상세(A+)·불릿 상세."""
    i = CS.index("function _kgpAmazonHiRes")
    j = CS.index("function extractProductMeta")
    block = CS[i:j]   # _kgpAmazonHiRes + _kgpSitePdp
    harness = block + r"""
    const HR = 'https://m.media-amazon.com/images/I/OHSNAP-hires.jpg';
    const dyn = JSON.stringify({'https://m.media-amazon.com/images/I/OHSNAP._AC_SX679_.jpg':[679,679]});
    function el(props){ return Object.assign({getAttribute:(k)=>props[k]||null, querySelectorAll:()=>[], currentSrc:props.currentSrc||'', src:props.src||'', innerText:props.innerText||'', textContent:props.innerText||''}, props); }
    const main = el({'data-old-hires':HR, 'data-a-dynamic-image':dyn, src:'https://m.media-amazon.com/images/I/OHSNAP._AC_SX466_.jpg'});
    const alt1 = el({src:'https://m.media-amazon.com/images/I/thumb1._SS40_.jpg'});
    const alt2 = el({src:'https://m.media-amazon.com/images/I/thumb2._SS40_.jpg'});
    const aplus1 = el({src:'https://m.media-amazon.com/images/aplus/A1._SL500_.jpg'});
    const b1 = el({innerText:'강력 접착 — 최대 3kg 지지'});
    const b2 = el({innerText:'열·물 저항 · 잔여물 없이 제거'});
    const pd = el({innerText:'OHSNAP 접착 패드는 벽면 손상 없이 부착됩니다.'});
    const map = {
      '#imgTagWrapperId img, #landingImage, #imgBlkFront, #main-image': main,
      '#productDescription': pd,
    };
    const mapAll = {
      '#altImages img, #imageBlockThumbs img, li.imageThumbnail img': [alt1, alt2],
      '#aplus img, #aplus_feature_div img, #productDescription img': [aplus1],
      '#feature-bullets li span.a-list-item, #feature-bullets li': [b1, b2],
    };
    global.location = { hostname: 'www.amazon.com' };
    global.document = {
      querySelector: (s) => map[s] || null,
      querySelectorAll: (s) => mapAll[s] || [],
    };
    const out = _kgpSitePdp();
    console.log(JSON.stringify(out));
    """
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    o = json.loads(res.stdout.strip())
    # 갤러리: 고해상(data-old-hires) 포함 + 썸네일 원본(크기토큰 제거)
    assert any("OHSNAP-hires.jpg" in u for u in o["gallery"])
    assert any(u.endswith("thumb1.jpg") for u in o["gallery"])      # ._SS40_ 제거됨
    assert all("_SS40_" not in u for u in o["gallery"])             # 썸네일 크기토큰 제거
    # 상세: A+ 이미지
    assert any("aplus/A1" in u for u in o["detail"])
    # 상세설명: 불릿 + productDescription
    assert "접착" in o["description"] and "·" in o["description"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_temu_pdp_extracts_text_and_spec():
    """Temu: 상세 영역 텍스트 + 스펙표(속성) + 본문 이미지 추출."""
    i = CS.index("function _kgpAmazonHiRes")
    j = CS.index("function extractProductMeta")
    block = CS[i:j]
    harness = block + r"""
    function el(p){return Object.assign({getAttribute:(k)=>p[k]||null,querySelectorAll:(s)=>p['_all_'+s]||[],currentSrc:p.currentSrc||'',src:p.src||'',innerText:p.innerText||'',textContent:p.innerText||''},p);}
    const trs=[el({innerText:'소재 폴리에스터'}),el({innerText:'사이즈 200x90cm'})];
    const dimg=[el({src:'https://temu.com/detail1.jpg'})];
    const specSel = "table tr, dl > dt, dl > dd, [class*='spec' i] li, [class*='attribute' i] li, [class*='param' i] li";
    const det=el({innerText:'린넨 3인 소파. 소재 폴리에스터 사이즈 200x90cm', _all_img:dimg}); det['_all_'+specSel]=trs;
    const gal=el({_all_img:[el({src:'https://temu.com/g1.jpg'})]});
    global.location={hostname:'www.temu.com'};
    global.document={querySelector:(s)=> (s.indexOf('gallery')>=0||s.indexOf('mainImage')>=0||s.indexOf('swiper')>=0)?gal:((s.indexOf('detail')>=0||s.indexOf('Description')>=0||s.indexOf('goods-desc')>=0)?det:null), querySelectorAll:()=>[]};
    const o=_kgpSitePdp();
    console.log(JSON.stringify({gallery:o.gallery.length, detail:o.detail.length, spec: o.description.includes('소재 폴리에스터') && o.description.includes('사이즈')}));
    """
    res = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, res.stderr
    o = json.loads(res.stdout.strip())
    assert o["gallery"] >= 1 and o["detail"] >= 1
    assert o["spec"] is True   # 상세 텍스트 + 스펙표 포함
