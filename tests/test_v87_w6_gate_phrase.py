"""tests/test_v87_w6_gate_phrase.py — v87-W6 item 3(확장): 미실행/비상품/상품 문구 3분.

## 오너 실기기 결함(재조사 금지·실증)
콘텐츠 스크립트 **미실행** 상태에서 팝업이 "상품 페이지가 아니에요"(판정 결과)를 표시 → 미실행과 비상품을
오도(SUPERONE 건 오판). 미실행은 "새로고침 필요"만, 판정 결과 문구는 판정이 실제로 돈 경우에만.

## 근원 (1줄)
`kgpGetPageType`가 `chrome.runtime.lastError`(콘텐츠 스크립트 부재)를 `unknown`으로 뭉개고,
`kgpSingleGateMessage("unknown")`이 "상품 페이지가 아니에요"(비상품 판정)를 반환 → 미실행=비상품 오도.

## 수리
- `kgpGetPageType`: lastError→`not-injected`, 탭없음→`no-tab`, 실행+미결→`unknown`, 실행+판정→`single|list`.
- `kgpSingleGateMessage`: not-injected/no-tab → **'새로고침 필요'만**, unknown/기타 → 비상품 판정 문구.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import os
from pathlib import Path

import pytest

PJ = Path("extensions/chrome-collector/popup.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.148"


def test_getpagetype_distinguishes_not_injected():
    # 미실행(lastError)과 판정불가(unknown)를 구분해 반환해야 한다.
    assert 'resolve("not-injected")' in PJ and "chrome.runtime.lastError" in PJ
    assert 'resolve("no-tab")' in PJ
    # lastError 분기가 !r||!r.ok 분기보다 먼저(미실행을 unknown으로 뭉개지 않음).
    i_lasterr = PJ.find('if (chrome.runtime.lastError) { resolve("not-injected")')
    i_unknown = PJ.find('if (!r || !r.ok) { resolve("unknown")')
    assert i_lasterr != -1 and i_unknown != -1 and i_lasterr < i_unknown


def _eval_gate(pt):
    """실 kgpSingleGateMessage를 node로 실행해 문구를 얻는다(문구 3분 실증)."""
    fn_src = PJ[PJ.index("function kgpSingleGateMessage"):]
    fn_src = fn_src[:fn_src.index("\n}") + 2]
    js = fn_src + f"\nconsole.log(JSON.stringify(kgpSingleGateMessage({json.dumps(pt)})));\n"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js); path = f.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True, timeout=10)
    finally:
        os.unlink(path)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_three_state_phrases_are_distinct():
    single = _eval_gate("single")
    not_injected = _eval_gate("not-injected")
    no_tab = _eval_gate("no-tab")
    nonproduct = _eval_gate("unknown")
    lst = _eval_gate("list")

    assert single is None                                   # 상품 → 통과(문구 없음)
    # 미실행 = '새로고침 필요'만(판정 결과 문구 아님).
    assert not_injected and "새로고침" in not_injected and "상품 페이지가 아니" not in not_injected
    assert no_tab == not_injected                           # 탭없음도 미실행류
    # 비상품(판정 돎) = 판정 결과 문구.
    assert nonproduct and "상품 페이지가 아니" in nonproduct
    assert not_injected != nonproduct                       # 미실행 ≠ 비상품(오도 제거)
    assert "목록" in lst                                     # 목록은 별도 문구
