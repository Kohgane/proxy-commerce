"""tests/test_v65_button_anchor.py — v65 STEP3: 수집 버튼 이미지 앵커.

현재 카드 우측 허공 부유 → 상품 이미지 요소 기준 absolute 오버레이(이미지 중앙, position 옵션 유지).
이미지를 카드에서 못 찾으면 카드 좌상단 폴백(허공 금지).
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
    assert MANIFEST["version"] == "1.5.125"


def test_source_contract():
    assert "function _kgpCardImage(card)" in CS          # 카드 대표 이미지 탐색
    # v80 STEP2: 버튼을 이미지 요소의 부모에 앵커(카드 아님) — 단, 캐러셀 안이면 최외곽 캐러셀 컨테이너(안정).
    assert "host = carousel || imgEl.parentElement;" in CS
    assert 'const mode = imgEl ? "" : "corner";' in CS    # 이미지 없으면 corner 폴백
    assert "host.appendChild(q)" in CS
    # corner 앵커 = 좌상단(허공 금지).
    assert 'if (mode === "corner") return ["top:6px !important", "left:6px !important"];' in CS
    # 앵커 모드 보존(재스타일 시).
    assert "q.dataset.anchorMode = mode" in CS
    assert 'kgpQuickBtnStyle(true, btn.dataset.anchorMode' in CS


def _extract(fn):
    m = re.search(r"function " + fn + r"\([^)]*\) \{.*?\n\}", CS, re.S)
    assert m, fn + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_card_image_picks_largest_node():
    fn = _extract("_kgpCardImage")
    harness = (
        fn + "\n"
        # 카드에 아이콘(작음) + 상품 이미지(큼) → 큰 것 채택. 이미지 없는 카드 → null.
        "function img(w,h){return {naturalWidth:w,naturalHeight:h,width:w,height:h,clientWidth:w,clientHeight:h};}\n"
        "var big=img(400,400), small=img(20,20);\n"
        "var card={querySelectorAll:function(sel){return sel==='img'?[small,big]:[];}};\n"
        "var empty={querySelectorAll:function(){return [];}};\n"
        "var picked=_kgpCardImage(card);\n"
        "console.log(JSON.stringify({isBig: picked===big, emptyNull: _kgpCardImage(empty)===null}));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["isBig"] is True          # 가장 큰 이미지 채택(아이콘 제외)
    assert out["emptyNull"] is True      # 이미지 없으면 null(→ corner 폴백)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_anchor_css_corner_node():
    fn = _extract("_kgpAnchorCss")
    harness = (
        "var KGP_TOUCH=false; function kgpHoverAnchor(){return 'center';}\n"
        + fn + "\n"
        "console.log(JSON.stringify({corner:_kgpAnchorCss('corner').join('|'), center:_kgpAnchorCss('').join('|')}));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["corner"] == "top:6px !important|left:6px !important"   # 폴백 좌상단(v73: !important)
    assert "translate(-50%,-50%)" in out["center"]               # 이미지 중앙(기본)
