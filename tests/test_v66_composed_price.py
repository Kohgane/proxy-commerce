"""tests/test_v66_composed_price.py — v66 STEP2: 테무 가격 합성 텍스트 추출.

가격 추출을 노드 단위 → 컨테이너 합성 텍스트로: textContent 공백·개행 제거 후 통화 패턴 매칭
(span 분절 ₩|1|,|899 조립). aria-label·content 속성도 후보. 통화 미감지 시 추정 금지(빈 통화).
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


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.76"


def test_source_contract():
    assert "function _composedPrice(el)" in EX
    assert 'el.getAttribute("aria-label")' in EX          # aria-label 후보 포함
    assert '(el.textContent || "").replace(/\\s+/g, "")' in EX   # 공백·개행 제거(span 조립)
    assert "var p = _composedPrice(el); if (!p) continue;" in EX  # _domPrice가 사용
    # 취소선 제외는 컨테이너 단위 유지.
    assert "function _priceOriginal(el)" in EX


def _extract(fn):
    m = re.search(r"function " + fn + r"\([^)]*\) \{.*?\n  \}", EX, re.S)
    assert m, fn + " 추출 실패"
    return m.group(0)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_composed_price_span_split_node():
    # parsePriceStr + _composedPrice 추출. span 분절/aria-label/통화 미상 케이스.
    pps = re.search(r"function parsePriceStr\(raw\) \{.*?\n  \}", EX, re.S).group(0)
    # PRICE_RE·_sym·CODE 상수도 필요.
    price_re = re.search(r"var PRICE_RE = (/.*/i);", EX).group(1)
    sym = re.search(r"function _sym\(s\) \{.*?\n  \}", EX, re.S).group(0)
    code = re.search(r"var CODE = \{.*?\};", EX, re.S).group(0)
    comp = _extract("_composedPrice")
    harness = (
        code + "\n" + "var PRICE_RE = " + price_re + ";\n" + sym + "\n" + pps + "\n" + comp + "\n"
        "function el(o){o.getAttribute=o.getAttribute||function(k){return o['_'+k]||null;};return o;}\n"
        # 케이스1: span 분절(공백/개행 포함) → 조립되어 매칭.
        "var c1=el({textContent:'₩ 1 , 899', _content:null});\n"
        # 케이스2: aria-label만(textContent 빈약).
        "var c2=el({textContent:'가격', 'aria-label':'₩61,144'});\n"
        "c2.getAttribute=function(k){return k==='aria-label'?'₩61,144':null;};\n"
        # 케이스3: 통화 기호 전무 → 가격으로 안 잡음(랜덤 숫자 오인 금지 = 추정 금지).
        "var c3=el({textContent:'12345', getAttribute:function(){return null;}});\n"
        "var out={c1:_composedPrice(c1), c2:_composedPrice(c2), c3:_composedPrice(c3)};\n"
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
    assert out["c1"] and out["c1"]["price"] == "1899" and out["c1"]["currency"] == "KRW", out  # span 분절 조립
    assert out["c2"] and out["c2"]["price"] == "61144" and out["c2"]["currency"] == "KRW", out  # aria-label
    assert out["c3"] is None, out      # 통화 기호 없으면 미추출(랜덤 숫자 오인·추정 금지)
