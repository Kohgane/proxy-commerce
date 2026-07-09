"""tests/test_v47_collect_status.py — v47 STEP2: 수집 상태 가시화(성공/부분 + 필드 로그).

서버가 필드별 present를 단일 판정 → 목록 상태 컬럼·드로어 수집 로그·토스트가 같은 판정.
가짜 성공·무음 실패 금지: 핵심(제목·가격·이미지) 누락이면 '부분', 가격 needs_check도 present 아님.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

API = Path("src/api/extension_api.py").read_text(encoding="utf-8")
EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
ROWS = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _mem():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    yield


# ── 순수 판정 로직 ────────────────────────────────────────────
def test_all_fields_present_is_success():
    from src.collectors.collect_status import compute_collect_status
    full = {"title_ko": "상품", "price": "20605", "price_status": "", "images": ["a"],
            "options": [{"name": "옵션", "values": ["빨", "파"]}], "description": "x" * 40,
            "detail_images": ["d"], "reviews": [{"text": "good"}]}
    st = compute_collect_status(full)
    assert st["status"] == "성공" and st["filled"] == st["total"] == 7
    assert st["missing"] == []


def test_core_missing_is_partial_and_listed():
    from src.collectors.collect_status import compute_collect_status, status_summary
    part = {"title": "t", "price": "", "price_status": "needs_check", "images": []}
    st = compute_collect_status(part, sources={"title": "dom"})
    assert st["status"] == "부분"
    assert "가격" in st["core_missing"] and "이미지" in st["core_missing"]
    # 간결 요약은 핵심 누락 우선(노이즈 억제)
    assert st["missing_short"] == st["core_missing"]
    assert "부분 수집" in status_summary(st) and "가격" in status_summary(st)
    # 필드별 소스 표기(있으면 소스, 없으면 없음 — 가짜 소스 금지)
    src = {f["key"]: f["source"] for f in st["fields"]}
    assert src["title"] == "DOM" and src["price"] == "없음"


def test_needs_check_price_not_counted_present():
    from src.collectors.collect_status import compute_collect_status
    # 가격 값은 있지만 needs_check(임의 확정 금지) → present 아님
    st = compute_collect_status({"title": "t", "price": "9", "price_status": "needs_check", "images": ["a"]})
    src = {f["key"]: f["ok"] for f in st["fields"]}
    assert src["price"] is False and src["images"] is True


# ── 서버 응답 field_status ────────────────────────────────────
def test_server_returns_field_status():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    try: ch._in_memory.clear()
    except Exception: pass
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="c1"), \
         patch("src.api.extension_api._notify_telegram"):
        with app.test_client() as c:
            r = c.post("/api/v1/collect/extension",
                       data=json.dumps({"url": "https://x.com/g-1", "title": "t",
                                        "price": "20605", "currency": "KRW", "images": ["https://x/i.jpg"],
                                        "field_sources": {"price": "json", "images": "dom"}}),
                       content_type="application/json", headers={"Authorization": "Bearer t"})
            d = r.get_json()
            assert d["ok"] is True
            fs = d.get("field_status")
            assert fs and fs["status"] == "부분"       # 옵션·상세·리뷰 없음 → 부분(필드 상태)
            assert "가격" not in fs["missing"] and "이미지" not in fs["missing"]  # 핵심은 있음
            # partial(coarse, 북마클릿 하위호환)은 핵심 둘 다 있으면 False
            assert d["partial"] is False


# ── 소스 계약(UI가 상태를 실제로 표기) ────────────────────────
def test_source_contract():
    assert '"field_status": _field_status' in API           # 서버 응답 필드
    assert "compute_collect_status" in API                    # 서버 단일 판정
    assert "field_sources" in EX                              # 추출기 필드별 소스
    assert "field_status" in CS and "부분 수집" in CS         # 토스트 정직 표기
    assert "collect_status" in ROWS and "부분 ·" in ROWS      # 목록 상태 컬럼
    assert "수집 로그" in PREVIEW and "collect_status.fields" in PREVIEW  # 드로어 수집 로그
