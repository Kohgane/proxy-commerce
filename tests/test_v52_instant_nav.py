"""tests/test_v52_instant_nav.py — v52 STEP1: 인스턴트 내비 엔진(body-swap) + 전송 최적화.

동일 오리진 <a> 클릭 → <main> 스왑 + pushState + 스크롤. prefetch 메모리 캐시(TTL30s·동시2). 스왑 오류 시
일반 내비 폴백(내비 죽지 않음). 폴링 등 teardown 훅. 폰트 미사용 굵기 제거(전송만). 목록 lazy 이미지.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = (ROOT / "src/seller_console/templates/_base.html").read_text(encoding="utf-8")
HIST = (ROOT / "src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
APPCSS = (ROOT / "src/static/app.css").read_text(encoding="utf-8")
LANDING = (ROOT / "src/templates/landing.html").read_text(encoding="utf-8")
ROWS = (ROOT / "src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")


def test_engine_source_contract():
    # 스왑 루트·프리패치 캐시·pushState·스크롤·폴백·teardown·X-KGP-Nav·popstate.
    assert "main.console-content" in BASE and "kgp-page-js" in BASE     # 스왑 루트 + 페이지 스크립트 래퍼
    assert "history.pushState" in BASE and "popstate" in BASE
    assert "location.assign(url)" in BASE                                # 오류 시 일반 내비 폴백
    assert "TTL = 30000" in BASE and "MAXFLIGHT = 2" in BASE             # 캐시 TTL·동시 제한
    assert "'X-KGP-Nav'" in BASE                                         # 서버가 내비 요청 구분 가능
    assert "__kgpTeardown" in BASE                                       # 재실행 정리 훅
    assert "runScripts" in BASE                                          # 스왑 후 페이지 스크립트 재실행


def test_polling_teardown_registered():
    # 수집이력 폴링이 teardown에 등록(스왑 이탈 시 인터벌 정리 → 누수/중복 방지).
    assert "__kgpTeardown" in HIST and "clearInterval(_pollTimer)" in HIST


def test_eligible_link_filtering():
    # eligible(a): 내부 링크만 스왑, _blank·download·logout·외부·javascript·data-no-swap 제외.
    m = re.search(r"function eligible\(a\)\s*\{.*?\n  \}", BASE, re.S)
    assert m, "eligible 함수를 찾지 못함"
    fn = m.group(0)
    harness = (
        "var location={origin:'https://x.com'};\n"
        + fn + "\n"
        "function A(o){o.getAttribute=function(k){return k==='href'?o._href:null};"
        "o.hasAttribute=function(k){return !!o[k+'_attr']};return o;}\n"
        "var out={};\n"
        "out.internal = eligible(A({_href:'/seller/dashboard', href:'https://x.com/seller/dashboard', origin:'https://x.com', pathname:'/seller/dashboard', target:''}));\n"
        "out.blank = eligible(A({_href:'/x', href:'https://x.com/x', origin:'https://x.com', pathname:'/x', target:'_blank'}));\n"
        "out.logout = eligible(A({_href:'/auth/logout', href:'https://x.com/auth/logout', origin:'https://x.com', pathname:'/auth/logout', target:''}));\n"
        "out.external = eligible(A({_href:'https://other.com/y', href:'https://other.com/y', origin:'https://other.com', pathname:'/y', target:''}));\n"
        "out.js = eligible(A({_href:'javascript:void(0)', href:'javascript:void(0)', origin:'https://x.com', pathname:'', target:''}));\n"
        "out.download = eligible(A({_href:'/f.zip', href:'https://x.com/f.zip', origin:'https://x.com', pathname:'/f.zip', target:'', download_attr:1}));\n"
        "out.noswap = eligible(A({_href:'/z', href:'https://x.com/z', origin:'https://x.com', pathname:'/z', target:'', 'data-no-swap_attr':1}));\n"
        "console.log(JSON.stringify(out));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        import json
        d = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(f.name)
    assert d["internal"] == "https://x.com/seller/dashboard"   # 내부 링크만 스왑
    for k in ("blank", "logout", "external", "js", "download", "noswap"):
        assert d[k] is None, f"{k}는 스왑 제외여야"


def test_font_weight_reduced_transfer_only():
    # 콘솔 세리프 600만, 랜딩 500;900 — 미사용 굵기 제거(패밀리·display=swap 불변).
    assert "Noto+Serif+KR:wght@600&display=swap" in APPCSS
    assert "wght@500;600;700" not in APPCSS                     # 옛 3굵기 제거
    assert "Noto+Serif+KR:wght@500;900&display=swap" in LANDING
    assert "wght@500;700;900" not in LANDING
    assert "display=swap" in APPCSS and "display=swap" in LANDING


def test_list_images_lazy():
    assert 'loading="lazy" decoding="async"' in ROWS           # 목록 썸네일 지연 로드
