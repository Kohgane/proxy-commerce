"""tests/test_v64_ad_filter.py — v64 STEP2: 광고/실상품 분류 수리.

증상: 아마존 66중 48 제외 — 실상품 다수가 '광고 영역' 휴리스틱으로 오제외. 근본: _kgpInBadRegion이
sponsor/ad 클래스 영역을 통째로 제외 → 스폰서=실상품인데 카드째 사라짐. 수리: allowAds로 영역 제외
안 하고 명시 신호(_kgpAmazonSponsored)로 태깅만. 전체선택/전체수집은 광고 기본 제외 + '광고 포함' 토글.
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
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.142"


def test_source_contract():
    # bad-region이 광고/구조 분리(함수 내부 structRe/adRe) + allowAds 파라미터.
    assert "function _kgpInBadRegion(el, opts)" in CS
    assert "const structRe" in CS and "const adRe" in CS
    assert "opts.allowAds" in CS
    # 아마존 어댑터는 allowAds로 호출(스폰서 영역 제외 안 함). v67: structuralOnly로 추천도 버튼.
    assert "_kgpInBadRegion(el, { allowAds: true, structuralOnly: true })" in CS
    # AD 미니 배지 + 전체선택 광고 제외 헬퍼 + 광고 포함 토글.
    assert "kgp-card-ad" in CS and 'textContent = "AD"' in CS
    assert "_kgpSelectableUrls" in CS and "_kgpInclAds" in CS
    assert 'data-act="incl-ads"' in CS
    assert "kgpCollect(_kgpSelectableUrls())" in CS   # 전체수집 광고 제외


def _extract(fn):
    m = re.search(r"function " + fn + r"\([^)]*\) \{.*?\n\}", CS, re.S)
    assert m, fn + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_bad_region_allowads_node():
    """스폰서 클래스 조상을 가진 카드: allowAds=false면 제외, true(아마존)면 통과."""
    harness = (
        _extract("_kgpInBadRegion") + "\n"     # structRe/adRe는 함수 내부 지역 상수(자립)
        "function mk(cls,parent){return {className:cls,tagName:'DIV',id:'',parentElement:parent||null,"
        "getAttribute:function(){return null;}};}\n"
        # 스폰서 컨테이너 안의 상품 카드.
        "var sponsorWrap=mk('AdHolder s-result-item sponsored-view');\n"
        "var prodCard=mk('s-card-container', sponsorWrap);\n"
        # 추천 레일 안의 카드(구조적 비상품).
        "var recoWrap=mk('p13n-recommend related-products');\n"
        "var recoCard=mk('card', recoWrap);\n"
        "var out={};\n"
        "out.sponsor_default=_kgpInBadRegion(prodCard, {});\n"
        "out.sponsor_allowads=_kgpInBadRegion(prodCard, {allowAds:true});\n"
        "out.reco_allowads=_kgpInBadRegion(recoCard, {allowAds:true});\n"
        "console.log(JSON.stringify(out));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["sponsor_default"] is True       # 광고 영역 제외(비아마존 기본)
    assert out["sponsor_allowads"] is False      # 아마존: 스폰서=실상품 → 통과(오제외 박멸)
    assert out["reco_allowads"] is True          # 추천 레일은 여전히 제외(구조적 비상품)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_selectable_excludes_ads_node():
    """전체선택/전체수집 대상: 기본은 실상품만(광고 제외), 광고 포함 토글 시 전부."""
    harness = (
        "var _store={};\n"
        "function kgpLSget(k,d){return (k in _store)?_store[k]:d;}\n"
        "var _kgpCardByUrl={'u1':{sponsored:false},'u2':{sponsored:true},'u3':{sponsored:false}};\n"
        + _extract("_kgpInclAds") + "\n" + _extract("_kgpSelectableUrls") + "\n" + _extract("_kgpAdCount") + "\n"
        "var off=_kgpSelectableUrls().sort();\n"
        "_store['kgp_incl_ads']='1';\n"
        "var on=_kgpSelectableUrls().sort();\n"
        "console.log(JSON.stringify({off:off, on:on, ads:_kgpAdCount()}));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["off"] == ["u1", "u3"]              # 기본: 광고(u2) 제외
    assert out["on"] == ["u1", "u2", "u3"]          # 광고 포함 토글: 전부
    assert out["ads"] == 1
