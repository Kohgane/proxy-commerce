"""tests/test_v32_part2_buttons.py — v32 PART2: 출시 필수 일괄 버튼 실동작 가드(가짜 성공 0).

상품명 정제(금지어/치환)·마진/가격·카테고리 자동분류가 실제로 커밋되는지(별칭 스코프 포함),
규칙 없으면 정직하게 막는지 검증. PART1 스코프 수정과 짝.
"""
from __future__ import annotations

import json
import os

import pytest


@pytest.fixture
def client():
    os.environ["SELLER_CONSOLE_AUTH"] = "0"
    from src.order_webhook import app
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _clean():
    from src.seller_console import collect_history_store as store
    store._in_memory[:] = []
    yield
    store._in_memory[:] = []


def _collect(seller_id="u1@example.com", *, title="진짜 가짜 백팩", price="100"):
    from src.seller_console import collect_history_store as store
    return store.append(source="extension", url="https://taobao.com/i", title=title,
                        price=price, currency="CNY", seller_id=seller_id)


def _login(client):
    with client.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "u1@example.com"


def test_bulk_clean_actually_removes_banned_word(client):
    from src.seller_console import word_rules, collect_history_store as store
    word_rules.save_rules("u1", banned=["가짜"], subs=[])
    iid = _collect(title="진짜 가짜 백팩")
    _login(client)
    r = client.post("/seller/collect/bulk-clean",
                    data=json.dumps({"item_ids": [iid]}), content_type="application/json")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True and body["updated"] == 1, "정제가 실제로 커밋되지 않음(가짜 성공)"
    item = store.get(iid, seller_ids={"u1", "u1@example.com"})
    assert "가짜" not in (item.get("title") or ""), "금지어가 제거되지 않음"


def test_bulk_clean_honest_when_no_rules(client):
    from src.seller_console import word_rules
    word_rules.save_rules("u1", banned=[], subs=[])     # 규칙 없음
    iid = _collect()
    _login(client)
    r = client.post("/seller/collect/bulk-clean",
                    data=json.dumps({"item_ids": [iid]}), content_type="application/json")
    assert r.status_code == 400
    assert r.get_json().get("no_rules") is True          # 정직 안내(가짜 성공 아님)


def test_bulk_price_margin_and_multiplier_commit(client):
    from src.seller_console import collect_history_store as store
    iid = _collect(price="100")
    _login(client)
    r = client.post("/seller/collect/bulk-price",
                    data=json.dumps({"item_ids": [iid], "target_margin_pct": 30, "price_multiplier": 1.1}),
                    content_type="application/json")
    assert r.status_code == 200 and r.get_json()["ok"] is True
    item = store.get(iid, seller_ids={"u1", "u1@example.com"})
    extra = json.loads(item.get("extra_json") or "{}")
    assert str(extra.get("target_margin_pct")) in ("30", "30.0"), "마진율이 저장되지 않음"
    # 배수 적용(100 → 110)
    assert abs(float(item.get("price")) - 110) < 0.5, "가격 배수가 실제로 반영되지 않음"


def test_classify_returns_real_code(client):
    _login(client)
    r = client.post("/seller/collect/classify",
                    data=json.dumps({"title": "백팩 가방 데일리"}), content_type="application/json")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body.get("code"), "분류 코드가 비어 있음"
