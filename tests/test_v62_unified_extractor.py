"""tests/test_v62_unified_extractor.py — v62 STEP1: 추출기 단일 모듈화(경로별 품질 편차 제거).

run.js(북마클릿)와 확장 콘텐츠 스크립트가 **같은 kgp-extractor.js**를 공유(번들). 옛 이원화(run.js 자체
약한 추출 로직) 제거 → 북마클릿·확장 추출 결과 동일. 산출 스키마 통일(title/price/images/desc_text/…).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
MF = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def _run_js():
    from src.seller_console import views as v
    return v._bookmarklet_run_js()


def test_run_js_bundles_the_shared_extractor():
    run = _run_js()
    # run.js가 kgp-extractor.js 전체를 번들(핵심 심볼 다수 일치) + __kgpRun 래퍼.
    for sym in ("kgpExtractProduct", "parsePriceStr", "_domImages", "_adapterTitle", "_domDescription", "desc_text"):
        assert sym in run, f"run.js에 공유 추출기 심볼 없음: {sym}"
    assert "window.__kgpRun=function(cb)" in run
    # 옛 경로 전용 재구현 제거(중복 0).
    assert "function PP(t)" not in run and "function PR()" not in run


def test_extension_content_script_loads_same_extractor():
    # 확장 격리월드 항목이 kgp-extractor.js를 content_script.js보다 먼저 로드(동일 소스).
    iso = [c for c in MF["content_scripts"] if "content_script.js" in c.get("js", [])][0]
    assert iso["js"][0] == "kgp-extractor.js"
    # content_script는 window.kgpExtractProduct(공유)를 호출.
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    assert "window.kgpExtractProduct()" in cs


def test_unified_schema_fields_present():
    # 산출 스키마 통일: title/price/currency/images/desc_text/desc_images/options/rating/reviews + sources.
    out_seg = EX.split("var out = {")[1].split("return out;")[0]
    for f in ("title:", "price:", "currency:", "images:", "desc_text:", "desc_images:",
              "options:", "rating:", "reviews:", "field_sources:"):
        assert f in out_seg, f"통일 스키마 필드 누락: {f}"


def test_run_js_route_served():
    from src.order_webhook import app
    with app.test_client() as c:
        r = c.get("/seller/bookmarklet/run.js")
    assert r.status_code == 200
    assert "javascript" in r.headers.get("Content-Type", "")
    body = r.get_data(as_text=True)
    assert "kgpExtractProduct" in body and "window.__kgpRun" in body
