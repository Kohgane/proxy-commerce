"""tests/test_v66_bookmarklet_fields.py — v66 STEP5: 북마클릿 옵션·상세 (run.js 보강).

run.js 확장판에 옵션·상세 추출이 STEP2·3과 동일 코어(kgp-extractor.js)로 포함되는지 감사
(v62 단일 모듈 원칙). run.js = 공유 추출기 전체 + __kgpRun 래퍼 → 확장·북마클릿 품질 편차 0.
"""
from __future__ import annotations

from pathlib import Path

import src.seller_console.views as views

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")


def test_run_js_bundles_shared_extractor():
    run = views._bookmarklet_run_js()
    # run.js = 공유 추출기 전체(kgpExtractProduct) + 래퍼.
    assert "window.kgpExtractProduct" in run
    assert "window.__kgpRun=function(cb)" in run
    # 공유 추출기 전체를 그대로 포함(코어 == 파일).
    core = views._shared_extractor_js()
    assert core and core in run
    assert core == EX     # 확장 콘텐츠 스크립트와 바이트 동일(단일 소스)


def test_run_js_includes_options_and_detail():
    run = views._bookmarklet_run_js()
    # 옵션 추출(_domOptions, 스와치·select) + 상세(_domDescription, feature-bullets·productDescription).
    assert "_domOptions" in run
    assert "_domDescription" in run
    assert "#feature-bullets" in run and "#productDescription" in run
    # v66 STEP2 합성 가격도 동일 코어로 포함.
    assert "_composedPrice" in run
    # v66 STEP3 아마존 hi-res 상세 이미지.
    assert "data-old-hires" in run and "#aplus img" in run


def test_run_js_wrapper_carries_html_and_version():
    run = views._bookmarklet_run_js()
    # 래퍼가 html·버전만 얹고 추출은 코어가(전송·토큰 노출 0).
    assert "r.html=" in run
    assert "r.ext_version=" in run
    # run.js 자체엔 토큰·서버 URL 없음(코어가 담당).
    assert "Bearer" not in run
