"""tests/test_v64_sticky_bar.py — v64 STEP4: 벌크바 스크롤 추적 sticky.

바는 position:fixed(뷰포트 상단 고정)+z-index 최상위라 스크롤을 따라온다. 일부 사이트는
조상 transform으로 fixed 기준을 바꿔 바가 콘텐츠와 함께 스크롤됨(고전 버그) → 스크롤 시 실제
top이 밀렸으면 translateY로 보정해 항상 상단 고정. 드래그 위치는 존중.
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
    assert MANIFEST["version"] == "1.5.116"


def test_bar_fixed_top_max_zindex():
    # 바 스타일: position:fixed + top:12px + z-index 최상위(사이트 헤더 위).
    # v72 STEP4: 격리 위해 position/transform/z-index에 !important. v73 STEP1: top/left도 !important
    #   (all:initial의 auto가 비-!important top/left를 덮어써 바가 화면 밖으로 떨어지던 회귀 수리).
    bar = re.search(r'"position:fixed !important", "top:12px !important", "left:50% !important", "transform:translateX\(-50%\) !important",\s*"z-index:2147483647 !important"', CS)
    assert bar, "벌크바가 fixed top + 최상위 z-index여야 함"


def test_sticky_hardening_wired():
    assert "_kgpKeepBarPinned" in CS and "_kgpBarScroll" in CS
    assert "__kgpBarScrollBound" in CS                      # 스크롤 리스너 1회 바인딩
    assert 'kgpLSget("kgp_bar_pos", "")' in CS              # 드래그 위치 존중(자동 재핀 안 함)
    assert "translateY(" in CS                              # 변형 조상 드리프트 보정
    # 마운트 즉시 재핀 호출.
    assert "_kgpKeepBarPinned();" in CS


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_keep_pinned_corrects_drift_node():
    """조상 transform으로 바 top이 밀린 경우 translateY 보정을 적용, 드래그 위치는 존중."""
    fn = re.search(r"function _kgpKeepBarPinned\(\) \{.*?\n\}", CS, re.S).group(0)
    harness = (
        "var _store={}; var _dragged='';\n"
        "function kgpLSget(k,d){ if(k==='kgp_bar_pos') return _dragged; return (k in _store)?_store[k]:d; }\n"
        "const KGP_TOOLBAR_ID='kgp-listing-toolbar';\n"
        "const _KGP_BAR_TOP=12;\n"
        # mock bar: getBoundingClientRect().top이 밀려 있음(예: 스크롤 200 → top=212 대신 여기선 60 드리프트 재현).
        "var _applied='';\n"
        "var bar={isConnected:true, style:{}, getBoundingClientRect:function(){return {top:72};}};\n"
        "global.document={getElementById:function(id){return id===KGP_TOOLBAR_ID?bar:null;}};\n"
        + fn + "\n"
        "_dragged=''; _kgpKeepBarPinned();\n"
        "var t1=bar.style.transform;\n"
        # 드래그된 경우: 재핀 안 함(base로 안 건드림).
        "_dragged='120,80'; bar.style.transform='DRAGGED'; _kgpKeepBarPinned();\n"
        "var t2=bar.style.transform;\n"
        "console.log(JSON.stringify({t1:t1, t2:t2}));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    # drift 60 → translateY(-60px) 보정 적용.
    assert "translateY(-60px)" in out["t1"], out
    assert "translateX(-50%)" in out["t1"], out
    # 드래그된 바는 건드리지 않음(존중).
    assert out["t2"] == "DRAGGED", out
