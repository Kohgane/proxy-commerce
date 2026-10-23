"""Resume #935: an unconfirmed registration must never disappear or look successful."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.db import image_translate_queue_pg as state
from src.services import coupang_option_quota as quota
from src.services import oneshot_ops as ops


@pytest.fixture(autouse=True)
def memory_state(monkeypatch):
    monkeypatch.setattr(state, "_enabled", lambda: False)
    state.reset_for_tests()
    yield
    state.reset_for_tests()


def tomorrow():
    # 이틀 뒤 **KST 정오** — 「지금+이틀+1시간」은 UTC 14:00~14:09에 돌면 KST 00:00~00:09(이월 시각 00:10 전)가 돼 하루 10분 실패했다(순찰 57 실측)
    kst = timezone(timedelta(hours=9))
    return (datetime.now(kst) + timedelta(days=2)).replace(hour=12, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def test_exception_keeps_carry_for_review_without_resending():
    quota.carry_add("item1", "coupang:gogane", "u1")
    with patch.object(ops, "register", side_effect=TimeoutError("response lost")) as send:
        ops.carry_drain(now=tomorrow())
        rows = quota.carry_rows()
        assert len(rows) == 1
        assert rows[0]["state"] == "needs_review"
        assert rows[0]["last"]["error_code"] == "carry_unconfirmed"
        assert "TimeoutError" in rows[0]["last"]["message"]
        assert ops.carry_drain(now=tomorrow())["picked"] == 0
        assert send.call_count == 1


def test_explicit_failure_stays_visible_until_new_registration_request():
    quota.carry_add("item1", "coupang:gogane", "u1")
    quota.carry_done("item1", "coupang:gogane", {
        "success": False, "error_code": "token_missing", "message": "연결을 확인해 주세요"})
    assert len(quota.carry_rows()) == 1
    assert quota.carry_due(tomorrow()) == []
    quota.carry_add("item1", "coupang:gogane", "u1")
    assert len(quota.carry_due(tomorrow())) == 1
    quota.carry_done("item1", "coupang:gogane", {"success": True})
    assert quota.carry_rows() == []


@pytest.mark.parametrize("results", [[], [{"market": "smartstore:chezgoga", "success": True}]])
def test_register_requires_a_result_for_every_requested_market(monkeypatch, results):
    from flask import jsonify
    from src.services import ocr_compare_diag as diag
    from src.seller_console import views, product_builder
    monkeypatch.setattr(diag, "_item", lambda iid: ({"id": iid}, "u1"))
    monkeypatch.setattr(product_builder, "build_product", lambda *a, **k: {"title": "상품"})
    monkeypatch.setattr(views, "collect_upload", lambda: jsonify({"ok": True, "result": {"results": results}}))
    result = ops.register("item1", ["coupang:gogane"])
    assert result["ok"] is False
    assert result["why"]


def test_carry_storage_failure_does_not_promise_automatic_retry(monkeypatch):
    from src.seller_console import views
    result = {"results": [{"market": "coupang:gogane", "success": False,
                           "error_code": quota.CODE, "message": "쿠팡 일일 옵션 한도"}]}
    monkeypatch.setattr(views, "_seller_id", lambda: "u1")
    monkeypatch.setattr(quota, "carry_add", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("storage down")))
    views._carry_option_quota("item1", result)
    row = result["results"][0]
    assert "자동 재시도" not in row["message"]
    assert "저장하지 못" in row["hint"]
    assert not row.get("carry")
