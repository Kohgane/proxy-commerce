"""tests/test_v53_button_context.py — v53 STEP1: 확장 수집 버튼 컨텍스트 자동 감지.

증상: 단일 상품 페이지에 중앙(벌크) 버튼이 떠 수집·선택 불가(옛 판정=카드 3개+면 목록).
점수제 감지기: URL 어댑터 매치 최우선 + DOM 휴리스틱(h1·갤러리·ld+json·카드 그리드). 단일→우측 단건,
목록→중앙 벌크, 불능→우측(안전 기본값). 두 버튼 동시 표시 금지. 롱프레스 수동 오버라이드.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CS = (ROOT / "extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
MANIFEST = json.loads((ROOT / "extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_source_contract():
    assert "function kgpDetectPageType" in CS
    assert "KGP_DETAIL_URL_RE" in CS and "KGP_LIST_URL_RE" in CS
    assert "kgpAttachOverride" in CS and "kgp_pt_ov:" in CS          # 롱프레스/우클릭 오버라이드
    assert "cards.length >= 3" not in CS                             # 옛 카드-3-개 판정 제거
    # v55 STEP5: SPA 재판정을 URL 변경 한정으로, DOM변이 재판정/500ms 디바운스 제거(점멸) → 캐시 판정.
    assert "function kgpPageType" in CS and "KGP_PT_CACHE" in CS
    # 목록/단일 상호배타(동시 표시 금지): list → RemoveFab+Listing, else RemoveListing+FAB
    assert "kgpRemoveFab();" in CS and "kgpRemoveListing();" in CS


def test_url_adapter_patterns_node():
    # URL 어댑터 정규식이 상품상세/목록을 올바로 가른다(node 실증).
    m1 = re.search(r"const KGP_DETAIL_URL_RE = (/.*/i);", CS)
    m2 = re.search(r"const KGP_LIST_URL_RE = (/.*/i);", CS)
    assert m1 and m2
    harness = (
        "const D=" + m1.group(1) + ";const L=" + m2.group(1) + ";\n"
        "const out={};\n"
        "out.temu_detail = D.test('https://www.temu.com/kr/xyz-g-601099.html');\n"
        "out.coupang_detail = D.test('https://www.coupang.com/vp/products/12345');\n"
        "out.amazon_detail = D.test('https://www.amazon.com/dp/B0ABC12345');\n"
        "out.temu_search = L.test('https://www.temu.com/kr/search_result.html?search_key=desk') && !D.test('https://www.temu.com/kr/search_result.html?search_key=desk');\n"
        "out.amazon_search = L.test('https://www.amazon.com/s?k=desk');\n"
        "console.log(JSON.stringify(out));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        d = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(f.name)
    assert d["temu_detail"] and d["coupang_detail"] and d["amazon_detail"]   # 상품상세 매치
    assert d["temu_search"] and d["amazon_search"]                           # 검색/목록 매치(상세 아님)


def test_detector_scoring_node():
    # kgpDetectPageType 점수제를 mock document로 실증: 단일(Product ld+json) vs 목록(카드 6개).
    m = re.search(r"function kgpDetectPageType\(\) \{.*?\n\}", CS, re.S)
    assert m, "kgpDetectPageType 함수 추출 실패"
    detail_re = re.search(r"const KGP_DETAIL_URL_RE = (/.*/i);", CS).group(1)
    list_re = re.search(r"const KGP_LIST_URL_RE = (/.*/i);", CS).group(1)
    harness = (
        "const KGP_DETAIL_URL_RE=" + detail_re + ";const KGP_LIST_URL_RE=" + list_re + ";\n"
        "let _cardN=0; function kgpFindCards(){return new Array(_cardN);}\n"
        "let _lds=[], _h1=0, _gallery=false;\n"
        "global.location={href:'',pathname:'/p'};\n"
        "global.sessionStorage={_d:{},getItem(k){return this._d[k]||null;},setItem(k,v){this._d[k]=v;}};\n"
        "global.document={querySelectorAll(sel){ if(sel==='h1')return new Array(_h1); if(sel.indexOf('ld+json')>=0)return _lds.map(t=>({textContent:t})); return [];},"
        "querySelector(sel){ return _gallery && /gallery|swiper|carousel/.test(sel) ? {} : null; }};\n"
        + m.group(0) + "\n"
        "const out={};\n"
        # 단일: 상품상세 URL + Product ld+json + h1 1개 + 갤러리
        "location.href='https://www.temu.com/kr/x-g-601099.html'; location.pathname='/x-g-601099.html'; _cardN=4; _h1=1; _gallery=true; _lds=['{\"@type\":\"Product\"}'];\n"
        "out.single = kgpDetectPageType();\n"
        # 목록: 검색 URL + 카드 8개 + ItemList
        "location.href='https://www.temu.com/kr/search_result.html?search_key=desk'; location.pathname='/search_result.html'; _cardN=8; _h1=0; _gallery=false; _lds=['{\"@type\":\"ItemList\"}'];\n"
        "out.list = kgpDetectPageType();\n"
        # 오버라이드: 강제 목록
        "sessionStorage.setItem('kgp_pt_ov:/search_result.html','single'); out.override = kgpDetectPageType();\n"
        "console.log(JSON.stringify(out));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        d = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(f.name)
    assert d["single"] == "single", d      # 상품상세 → 단일(우측 FAB)
    assert d["list"] == "list", d          # 검색+카드8 → 목록(중앙 벌크)
    assert d["override"] == "single", d    # 수동 오버라이드 우선


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.60"
