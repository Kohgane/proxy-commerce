"""tests/test_v49_status_fail.py — v49 STEP5: 수집 상태 3단계(성공/부분/실패—원인) 잔존분.

v47 STEP2의 성공/부분에 더해 '실패—원인'(핵심 3 전부 미확보=추출 실패) 추가. 목록 배지·드로어
수집 로그·토스트 모두 3단계 반영. 무음 실패·가짜 성공 금지.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ROWS = Path("src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
PREVIEW = Path("src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _mem():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    for k in ("DATABASE_URL", "DATABASE_URL_DIRECT"):
        os.environ.pop(k, None)
    yield


def test_all_core_missing_is_failure_with_cause():
    from src.collectors.collect_status import compute_collect_status, status_summary
    st = compute_collect_status({"title": "", "price": "", "price_status": "needs_check", "images": []})
    assert st["status"] == "실패"
    assert st["cause"] and "추출 실패" in st["cause"]
    assert "수집 실패" in status_summary(st)


def test_some_core_present_is_partial_not_failure():
    from src.collectors.collect_status import compute_collect_status
    # v54: core={가격,갤러리}. 가격 present + 갤러리 누락 → 핵심 하나만 → 부분(둘 다 누락은 실패).
    st = compute_collect_status({"title_ko": "상품", "price": "100", "price_status": "", "images": []})
    assert st["status"] == "부분"


def test_all_present_is_success():
    from src.collectors.collect_status import compute_collect_status
    st = compute_collect_status({"title_ko": "A", "price": "100", "price_status": "", "images": ["a"],
                                 "options": [{"a": 1}], "description": "x" * 40, "detail_images": ["d"],
                                 "reviews": [{"t": 1}]})
    assert st["status"] == "성공" and st["filled"] == 5   # v54: 5필드(제목 카운트 제외)


def test_failure_rendered_in_list_and_drawer_and_toast():
    # 목록 배지·드로어 로그·토스트에 실패 3단계 반영
    assert 'cs.status == "실패"' in ROWS and "실패 · 추출 실패" in ROWS
    assert 'collect_status.status == "실패"' in PREVIEW and "수집 실패" in PREVIEW
    assert 'fs.status === "실패"' in CS and "수집 실패" in CS


def test_list_failure_badge_renders():
    import json
    from src.order_webhook import app
    from src.seller_console import collect_history_store as ch
    try: ch._in_memory.clear()
    except Exception: pass
    ch.append(source="extension", url="https://x/g-1", title="", price="", currency="", status="ok",
              seller_id="u1", extra={"title": "", "price": "", "price_status": "needs_check", "images": []})
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"; s["email"] = "u1"; s["authenticated"] = True
        b = c.get("/seller/collect/history").get_data(as_text=True)
        assert "실패 · 추출 실패" in b     # 옛 레코드도 렌더 시 재판정 → 실패 배지
