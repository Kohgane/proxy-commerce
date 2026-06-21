"""tests/test_word_rules.py — 금지어/치환 규칙 (Phase 248, v3 P1-5)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _clear():
    from src.seller_console import collect_history_store as chs
    from src.seller_console import word_rules as wr
    chs._in_memory.clear()
    wr._in_memory.clear()
    yield
    chs._in_memory.clear()
    wr._in_memory.clear()


def test_apply_rules_substitute_and_remove():
    from src.seller_console import word_rules as wr
    rules = {"banned": ["정품", "최저가"], "subs": [{"from": "나이키", "to": "NIKE"}]}
    res = wr.apply_rules("정품 나이키 운동화 최저가", "s1", rules=rules)
    assert "정품" not in res["text"]
    assert "최저가" not in res["text"]
    assert "NIKE" in res["text"]
    assert res["changed"] is True
    assert "정품" in res["removed"]


def test_save_and_get_rules_route(client):
    r = client.post("/seller/listing/word-rules/save",
                    json={"banned": "정품\n특가, 최저가", "subs": [{"from": "A", "to": "B"}]})
    assert r.status_code == 200
    rules = r.get_json()["rules"]
    assert "정품" in rules["banned"] and "특가" in rules["banned"] and "최저가" in rules["banned"]
    assert rules["subs"] == [{"from": "A", "to": "B"}]


def test_bulk_clean_applies_to_titles(client):
    from src.seller_console import collect_history_store as chs
    from src.seller_console import word_rules as wr
    wr.save_rules("default", ["정품"], [{"from": "신발", "to": "운동화"}])
    a = chs.append(source="manual", url="https://x/1", title="정품 신발 멋짐", seller_id="default")
    r = client.post("/seller/collect/bulk-clean", json={"item_ids": [a]})
    data = r.get_json()
    assert data["ok"] is True and data["updated"] == 1
    new_title = chs._in_memory[0]["title"]
    assert "정품" not in new_title
    assert "운동화" in new_title


def test_bulk_clean_no_rules_returns_hint(client):
    from src.seller_console import collect_history_store as chs
    a = chs.append(source="manual", url="https://x/1", title="t", seller_id="default")
    r = client.post("/seller/collect/bulk-clean", json={"item_ids": [a]})
    assert r.status_code == 400
    assert r.get_json().get("no_rules") is True


def test_word_rules_page_and_nav(client):
    html = client.get("/seller/listing/word-rules").get_data(as_text=True)
    assert "금지어" in html and "치환" in html
    nav = client.get("/seller/dashboard").get_data(as_text=True)
    assert "/seller/listing/word-rules" in nav


def test_history_has_clean_button(client):
    html = client.get("/seller/collect/history").get_data(as_text=True)
    assert "bulkCleanBtn" in html and "runBulkClean" in html
