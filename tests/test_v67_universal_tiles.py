"""tests/test_v67_universal_tiles.py — v67 STEP1: 전 타일 버튼 (퍼센티 패리티).

수집 버튼을 상품 타일 전부에(메인 그리드+추천 캐러셀+frequently viewed). v66 메인 한정은 카운트에만.
region 태그(main/reco)로 전체선택 기본은 메인, '추천 포함'·'광고 포함' 토글.
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
    assert MANIFEST["version"] == "1.5.95"


def test_source_contract():
    assert "function _kgpIsRecoRegion(el)" in CS
    assert "opts.structuralOnly" in CS
    # 전체선택/전체수집 기본 메인, 추천 포함 토글.
    assert "function _kgpInclReco()" in CS
    assert 'data-act="incl-reco"' in CS
    assert 'act === "incl-reco"' in CS
    # region 기반 selectable(추천 기본 제외).
    assert 'c.region === "reco" && !inclReco' in CS
    # region count helpers.
    assert "function _kgpRecoCount()" in CS and "function _kgpMainCount()" in CS


def _extract(fn):
    m = re.search(r"function " + fn + r"\([^)]*\) \{.*?\n\}", CS, re.S)
    assert m, fn + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_selectable_region_defaults_node():
    """전체선택 대상: 기본 메인만(추천·광고 제외). 추천 포함·광고 포함 토글로 확장."""
    harness = (
        "var _store={};\n"
        "function kgpLSget(k,d){return (k in _store)?_store[k]:d;}\n"
        "var _kgpCardByUrl={"
        "  'm1':{region:'main',sponsored:false},"
        "  'm2':{region:'main',sponsored:false},"
        "  'r1':{region:'reco',sponsored:false},"
        "  'a1':{region:'main',sponsored:true}"
        "};\n"
        + _extract("_kgpInclAds") + "\n" + _extract("_kgpInclReco") + "\n"
        + _extract("_kgpSelectableUrls") + "\n" + _extract("_kgpRecoCount") + "\n" + _extract("_kgpMainCount") + "\n"
        "var base=_kgpSelectableUrls().sort();\n"
        "_store['kgp_incl_reco']='1';\n"
        "var withReco=_kgpSelectableUrls().sort();\n"
        "_store['kgp_incl_ads']='1';\n"
        "var withAll=_kgpSelectableUrls().sort();\n"
        "console.log(JSON.stringify({base:base, withReco:withReco, withAll:withAll,"
        " main:_kgpMainCount(), reco:_kgpRecoCount()}));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["base"] == ["m1", "m2"]                     # 기본: 메인 비스폰서만
    assert out["withReco"] == ["m1", "m2", "r1"]           # 추천 포함
    assert out["withAll"] == ["a1", "m1", "m2", "r1"]      # 광고까지 포함
    assert out["main"] == 2 and out["reco"] == 1           # region 카운트
