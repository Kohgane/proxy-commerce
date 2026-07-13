"""tests/test_v62_amazon_twister.py — v62 STEP3: 아마존 트위스터 옵션 축 이름 정확 매핑.

v58 스와치 경로가 값은 이미 잡지만 이름이 '옵션'으로 뭉개짐 → inline-twister-row id / .a-form-label로
색상/사이즈 축명 복원. 값은 그대로(회귀 0), 이름만 정확화. 트위스터 행은 제네릭 경로에서 중복 배제.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_source_contract():
    assert "inline-twister-row-" in EX          # 아마존 트위스터 행 셀렉터
    assert "_TW_ID" in EX and "a-form-label" in EX
    # 트위스터 행은 제네릭 스와치 경로에서 중복 배제(closest 가드).
    assert 'grp.closest(\'[id^="inline-twister-row-"]\')' in EX


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.70"


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_twister_axis_naming_node():
    # _domOptions를 mock document로 실증: 트위스터 색상/사이즈 행 → 축명 정확·값 유지, 중복 0.
    m = re.search(r"function _domOptions\(\) \{.*?\n  \}", EX, re.S)
    assert m, "_domOptions 추출 실패"
    opt_label = re.search(r"var OPT_LABEL = (/.*/i);", EX).group(1)
    harness = (
        "var OPT_LABEL=" + opt_label + ";\n"
        "function _nonProdRegion(){return false;}\n"
        "function _galleryExcluded(){return false;}\n"
        # mock DOM: 트위스터 색상행(3값) + 사이즈행(2값) + select 없음.
        "function mkEl(o){o.querySelector=o.querySelector||function(){return null;};"
        "o.querySelectorAll=o.querySelectorAll||function(){return [];};"
        "o.getAttribute=o.getAttribute||function(){return null;};o.closest=function(){return null;};return o;}\n"
        "function txt(s){return mkEl({innerText:s,textContent:s});}\n"
        "function swatch(v){return mkEl({getAttribute:function(k){return k==='title'?v:null;},innerText:v,textContent:v,"
        "querySelector:function(){return null;}});}\n"
        "var colorRow=mkEl({id:'inline-twister-row-color_name',"
        "  querySelector:function(sel){return /form-label|label/.test(sel)?txt('Color:'):null;},"
        "  querySelectorAll:function(sel){return /swatch|li|radio|asin|button/.test(sel)?[swatch('Black'),swatch('White'),swatch('Blue')]:[];}});\n"
        "var sizeRow=mkEl({id:'inline-twister-row-size_name',"
        "  querySelector:function(sel){return /form-label|label/.test(sel)?txt('Size:'):null;},"
        "  querySelectorAll:function(sel){return /swatch|li|radio|asin|button/.test(sel)?[swatch('S'),swatch('M')]:[];}});\n"
        "global.document={querySelectorAll:function(sel){"
        "  if(sel==='select')return [];"
        "  if(sel.indexOf('inline-twister-row-')>=0)return [colorRow,sizeRow];"
        "  return [];   /* 제네릭 그룹 셀렉터: 트위스터 값은 위에서 잡힘 */"
        "},querySelector:function(){return null;}};\n"
        + m.group(0) + "\n"
        "var out=_domOptions();\n"
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
    by = {o["name"]: o["values"] for o in out}
    assert "색상" in by, out                          # 축명 정확(옵션 아님)
    assert by["색상"] == ["Black", "White", "Blue"]   # 값 유지
    assert "사이즈" in by and by["사이즈"] == ["S", "M"]
    # 중복 0(같은 값이 '옵션'으로 다시 안 들어감).
    assert len(out) == 2, out
