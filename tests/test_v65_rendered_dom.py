"""tests/test_v65_rendered_dom.py — v65 STEP1: 렌더드-DOM 단일 경로 추출기.

전략 전환: Tier1 인터셉트 의존 폐지. 정본 경로 = 렌더된 DOM 추출. 렌더 완료 대기(가격+메인이미지,
최대 8초, 미달=부분) + 제목이 순수 사이트명('Temu')으로 저장되는 것 차단. 보강 큐는 extractMetaWait 사용.
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
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.138"


def test_render_wait_source_contract():
    assert "function kgpWaitRendered" in EX and "function _renderReady" in EX
    assert "global.kgpWaitRendered = kgpWaitRendered" in EX
    assert "function _isBareSiteName" in EX
    # content_script: 렌더 대기 후 추출 메시지 + 접힘 펼침.
    assert 'msg.action === "extractMetaWait"' in CS
    assert "kgpWaitRendered" in CS and "kgpRevealDetailFolds" in CS
    # 보강 큐가 정본 경로(extractMetaWait) 사용 — 고정 sleep 제거.
    assert 'action: "extractMetaWait"' in BG


def _extract(fn):
    m = re.search(r"function " + fn + r"\([^)]*\) \{.*?\n  \}", EX, re.S)
    if not m:
        m = re.search(r"function " + fn + r"\([^)]*\) \{.*?\n\}", EX, re.S)
    assert m, fn + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_bare_site_name_guard_node():
    fn = _extract("_isBareSiteName")
    harness = (
        fn + "\n"
        "var out={};\n"
        "out.temu=_isBareSiteName('Temu');\n"
        "out.temu_lower=_isBareSiteName('temu');\n"
        "out.amazon=_isBareSiteName('Amazon.co.jp');\n"
        "out.yahoo=_isBareSiteName('Yahoo!ショッピング');\n"
        "out.empty=_isBareSiteName('');\n"
        "out.product=_isBareSiteName('무선 블루투스 이어폰 | Temu');\n"
        "out.real=_isBareSiteName('접이식 차량용 테이블');\n"
        "console.log(JSON.stringify(out));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["temu"] is True and out["temu_lower"] is True   # 순수 사이트명 배제
    assert out["amazon"] is True                                # 'Amazon.co.jp'도 배제
    assert out["yahoo"] is True                                 # 'Yahoo!ショッピング'도 배제
    assert out["empty"] is True
    assert out["product"] is False                              # 상품명 붙으면 유효
    assert out["real"] is False                                 # 진짜 상품명은 유효


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_render_ready_and_wait_node():
    ready = _extract("_renderReady")
    wait = _extract("kgpWaitRendered")
    harness = (
        # mock: 가격 노드 + 큰 이미지 present → ready.
        "function _domPrice(){ return { price:'12000', currency:'KRW' }; }\n"
        "global.document={querySelectorAll:function(sel){"
        "  if(sel==='img') return [{naturalWidth:400,naturalHeight:400}];"
        "  return [];"
        "}};\n"
        + ready + "\n" + wait + "\n"
        "var rr=_renderReady();\n"
        "var got=null;\n"
        "kgpWaitRendered(function(res){ got=res; }, 8000);\n"
        "setTimeout(function(){ console.log(JSON.stringify({ready:rr.ready, partial:got&&got.partial})); }, 50);\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["ready"] is True                 # 가격+이미지 → 준비 완료
    assert out["partial"] is False              # ready면 즉시 완료(부분 아님)
