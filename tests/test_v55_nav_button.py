"""tests/test_v55_nav_button.py — v55 STEP4(내비 안정화) + STEP5(버튼 감지 안정화).

STEP4: document 위임(스왑 생존) + 멱등 init 가드 + 인터셉트 범위 축소 + 2초 타임아웃/워치독 폴백.
STEP5: 재판정 URL변경 한정(history훅+popstate), DOM변이 재판정 제거(점멸), 테무 -g-{숫자} 하드매치,
URL별 판정 캐시(세션 내 불변=히스테리시스).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")

ROOT = Path(__file__).resolve().parent.parent
BASE = (ROOT / "src/seller_console/templates/_base.html").read_text(encoding="utf-8")
CS = (ROOT / "extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
HIST = (ROOT / "src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")


# ── STEP4: 내비 안정화 ────────────────────────────────────────
def test_nav_engine_stability_contract():
    assert "window.kgpInitOnce" in BASE                       # 멱등 init 가드
    assert "AbortController" in BASE and "2000" in BASE       # 2초 fetch 타임아웃
    assert "2500" in BASE                                     # 스톨 워치독
    assert "button, input, select, textarea" in BASE         # 링크 내부 컨트롤 제외
    assert "e.button !== 0" in BASE                           # 좌클릭만
    assert "document.addEventListener('click'" in BASE        # document 위임(스왑 생존)


def test_collect_history_idempotent_listeners():
    assert "kgpInitOnce" in HIST and "_chOnce" in HIST        # document/window 리스너 1회 바인딩
    assert "removeEventListener('visibilitychange'" in HIST   # 상태의존 리스너는 teardown 제거
    assert "_chInitCheckboxes" in HIST and "readyState" in HIST  # 스왑-인 시 체크박스 재초기화


# ── STEP5: 버튼 감지 안정화 ───────────────────────────────────
def test_button_no_dom_mutation_rejudge():
    assert "function kgpPageType" in CS and "KGP_PT_CACHE" in CS   # URL별 판정 캐시(히스테리시스)
    assert "주기적 always-refresh(4초) 제거" in CS               # 4초 재판정 제거
    assert "재주입 전용 옵저버" in CS                            # 옵저버=재마운트만(재판정 아님)
    assert "isDetail && !isList" in CS                          # URL 하드매치 결정적


def test_pagetype_url_decisive_and_cached_node():
    # 테무 -g-{숫자} → single(즉시), /search → list. 같은 URL은 캐시로 불변(DOM이 바뀌어도 번복 0).
    m = re.search(r"function kgpDetectPageType\(\) \{.*?\n\}", CS, re.S)
    cache = re.search(r"const KGP_PT_CACHE = \{\};\nfunction kgpPageType\(\) \{.*?\n\}", CS, re.S)
    assert m and cache
    dre = re.search(r"const KGP_DETAIL_URL_RE = (/.*/i);", CS).group(1)
    lre = re.search(r"const KGP_LIST_URL_RE = (/.*/i);", CS).group(1)
    harness = (
        "const KGP_DETAIL_URL_RE=" + dre + ";const KGP_LIST_URL_RE=" + lre + ";\n"
        "let _cards=0; function kgpFindCards(){return new Array(_cards);}\n"
        "function kgpIsDefaultSourcing(){return false;}\n"   # v60 STEP5: 점수제/캐시 경로 검증 → 디폴트소싱 우회

        "global.location={href:'',pathname:'/',search:''};\n"
        "global.sessionStorage={_d:{},getItem(k){return this._d[k]||null;},setItem(k,v){this._d[k]=v;}};\n"
        "global.document={querySelectorAll(){return [];},querySelector(){return null;}};\n"
        + m.group(0) + "\n" + cache.group(0) + "\n"
        "const out={};\n"
        # 테무 상품상세: -g-숫자 → single 즉시(DOM 무관)
        "location.href='https://www.temu.com/kr/x-g-601099.html'; location.pathname='/x-g-601099.html'; _cards=9;\n"
        "out.temu_detail = kgpPageType();\n"
        # DOM이 바뀌어도(카드 늘어도) 같은 URL은 캐시로 불변
        "_cards=50; out.temu_detail_again = kgpPageType();\n"
        # 검색 목록
        "location.href='https://www.temu.com/kr/search_result.html?q=desk'; location.pathname='/search_result.html'; location.search='?q=desk';\n"
        "out.temu_search = kgpPageType();\n"
        "console.log('@@'+JSON.stringify(out));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        d = json.loads([l[2:] for l in r.stdout.splitlines() if l.startswith("@@")][-1])
    finally:
        os.unlink(f.name)
    assert d["temu_detail"] == "single"          # -g-숫자 → 단일(우측 버튼)
    assert d["temu_detail_again"] == "single"    # 카드 50개로 늘어도 캐시로 불변(점멸 0)
    assert d["temu_search"] == "list"            # 검색 → 목록(중앙)
