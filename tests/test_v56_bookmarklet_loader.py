"""tests/test_v56_bookmarklet_loader.py — v56 STEP1: 북마클릿 로더 구조(침묵 사망 원천 제거).

인라인 코어(토스트 K 최우선·즉시 '수집 중…'·og+기본이미지+outerHTML) + run.js 로더(토큰 미노출) +
전구간 try/catch 최후 alert + 앵커 빈텍스트/ICON유지 + 설치 테스트 페이지.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")


def _bm():
    from src.seller_console.views import _bookmarklet_js
    return _bookmarklet_js("https://x.com", "TOK", True)


def _run():
    from src.seller_console.views import _bookmarklet_run_js
    return _bookmarklet_run_js()


def test_core_toast_first_and_immediate():
    js = _bm()
    # K() 정의가 fetch/로더보다 앞 + 즉시 '수집 중… (bm-vN)' 표시(침묵 금지 · v58 버전 스탬프).
    _toast = "K('수집 중… ('+BMV+')',true)"
    assert js.index("function K(") < js.index(_toast)
    assert js.index(_toast) < js.index("__kgpRun")   # 로더보다 먼저 토스트
    assert "function core()" in js and "outerHTML" in js and "og:image" in js   # 검증된 구버전 코어


def test_loader_and_fallback():
    js = _bm()
    assert "/seller/bookmarklet/run.js?v=" in js               # run.js 주입 시도
    # v81 STEP1: 타임아웃 2.5s→6s + 간이(코어) 폴백은 isCore 인자로 침묵 금지.
    assert "sc.onerror" in js and "setTimeout(function(){go(core(),true);},6000)" in js
    assert "window.__kgpRun" in js                             # run.js 함수 호출


def test_token_not_in_run_js():
    # 토큰은 코어 closure에만 — run.js URL/본문에 노출 0.
    assert "TOK" not in _run() and "Bearer" not in _run()
    assert "window.__kgpRun" in _run() and "cb(" in _run()


def test_last_resort_alert_and_trycatch():
    js = _bm()
    assert js.strip().startswith("javascript:(function(){try{")
    assert "alert('[고가수집기] 수집기 실행 오류" in js          # 최후 보루(토스트조차 실패 시)
    assert "try{alert('[고가수집기] '+m)" in js                # 토스트 생성 실패 시 alert 폴백


def test_run_js_endpoint():
    from src.order_webhook import app
    with app.test_client() as c:
        r = c.get("/seller/bookmarklet/run.js")
        assert r.status_code == 200 and "javascript" in r.mimetype
        assert r.headers.get("Access-Control-Allow-Origin") == "*"   # 임의 사이트 script 로드
        assert "window.__kgpRun" in r.get_data(as_text=True)


def test_testpage_and_verdict():
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
        r = c.get("/seller/bookmarklet/testpage")
        assert r.status_code == 200
        b = r.get_data(as_text=True)
        assert "application/ld+json" in b and '"@type":"Product"' in b   # 데모 상품(ld+json)
        assert "kgpbm" in b and "verdict" in b                # 토스트 감시 → 초록 판정
        assert "MutationObserver" in b


def test_install_test_button_and_icon_note():
    tpl = Path("src/seller_console/templates/bookmarklet.html").read_text(encoding="utf-8")
    assert "/seller/bookmarklet/testpage" in tpl and "설치 테스트" in tpl
    assert "아이콘만" in tpl                                    # '아이콘만 보이는 게 정상' 안내
