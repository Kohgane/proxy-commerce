"""tests/test_v67_visible_enrich.py — v67 STEP2: 보강 렌더 보장 (테무 1/5 근원).

백그라운드 탭 스로틀 대응 — 보강 탭을 별도 소형 창(popup 480×640, 활성=렌더 보장)에서 순차 오픈.
렌더 대기 강화(자동 스크롤·인터스티셜 닫기·12초). 테무 성공 기준=가격+갤러리≥3, 미달/게이트면 정직 실패.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

BG = Path("extensions/chrome-collector/background.js").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
POPUP_JS = Path("extensions/chrome-collector/popup.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.134"


def test_window_mode_source_contract():
    # 소형 창(popup) 기반 보강 + 모드 설정.
    assert 'chrome.windows.create({ url: item.url, type: "popup", width: 480, height: 640' in BG
    assert 'enrichMode: localData.kgp_enrich_mode || "window"' in BG
    assert "chrome.windows.remove" in BG
    # 팝업 설정.
    assert 'id="enrichMode"' in Path("extensions/chrome-collector/popup.html").read_text(encoding="utf-8")
    assert "kgp_enrich_mode" in POPUP_JS


def test_render_wait_hardening_source_contract():
    # 자동 스크롤·인터스티셜·12초·조건 로그.
    assert "function _kgpAutoScroll(cb)" in CS
    assert "function _kgpDismissInterstitial()" in CS
    assert "}, 12000);" in CS                              # 12초 대기
    assert "document.hidden" in CS                         # hidden 가드 로그
    assert "priceOk=" in CS and "imgOk=" in CS             # 타임아웃 조건 로그
    # 렌더 미보장 상태로 '보강 완료' 금지(verdict 미달=throw).
    assert "if (!verdict.ok) throw new Error(verdict.reason)" in BG


def _extract_bg(fn):
    m = re.search(r"function " + fn + r"\([^)]*\) \{.*?\n\}", BG, re.S)
    assert m, fn + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_temu_enrich_verdict_node():
    fn = _extract_bg("_kgpEnrichVerdict")
    harness = (
        fn + "\n"
        "var temu='https://www.temu.com/g-1.html', amz='https://www.amazon.com/dp/B0';\n"
        "var out={};\n"
        "out.temu_ok=_kgpEnrichVerdict({url:temu},{price:'12000',images:['a','b','c']}).ok;\n"
        "out.temu_noprice=_kgpEnrichVerdict({url:temu},{price:'',images:['a','b','c']});\n"
        "out.temu_smallgal=_kgpEnrichVerdict({url:temu},{price:'12000',images:['a']});\n"
        "out.temu_interstitial=_kgpEnrichVerdict({url:temu},{price:'12000',images:['a','b','c'],interstitial:true});\n"
        "out.amz_lenient=_kgpEnrichVerdict({url:amz},{price:'',images:['a']}).ok;\n"
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
    assert out["temu_ok"] is True                                  # 가격+갤러리3 → 성공
    assert out["temu_noprice"]["ok"] is False and "가격" in out["temu_noprice"]["reason"]
    assert out["temu_smallgal"]["ok"] is False and "갤러리" in out["temu_smallgal"]["reason"]
    assert out["temu_interstitial"]["ok"] is False and "게이트" in out["temu_interstitial"]["reason"]
    assert out["amz_lenient"] is True                              # 비테무는 엄격 게이트 없음
