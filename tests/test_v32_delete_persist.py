"""tests/test_v32_delete_persist.py — v32 P0: 일괄 삭제 영속성(재진입 시 부활) 회귀 가드.

원인(v30과 동형): 삭제가 exact seller_id로만 매칭 → 별칭(user_id↔email) 불일치 시 삭제 0건
→ 낙관적 UI로 지워진 듯 보이나 재진입하면 그대로. 수정: 관용 식별자(seller_ids)로 삭제.
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


def _collect(seller_id):
    from src.seller_console import collect_history_store as store
    return store.append(source="extension", url="https://taobao.com/i", title="t", seller_id=seller_id)


def test_bulk_delete_persists_across_alias(client):
    from src.seller_console import collect_history_store as store
    a = _collect("u1@example.com")     # 이메일 별칭으로 저장
    b = _collect("u1@example.com")
    with client.session_transaction() as s:
        s["user_id"] = "u1"            # 세션은 user_id 별칭
        s["user_email"] = "u1@example.com"
    r = client.post("/seller/collect/bulk-delete",
                    data=json.dumps({"item_ids": [a, b]}), content_type="application/json")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["deleted"] == 2, "별칭 불일치로 삭제 0건(재진입 부활 버그)"
    # 영속: 같은 본인 스코프로 재조회해도 사라진 상태 유지
    ids = {"u1", "u1@example.com"}
    assert store.list_items(days=30, seller_ids=ids) == []


def test_bulk_delete_does_not_touch_other_seller(client):
    from src.seller_console import collect_history_store as store
    mine = _collect("u1")
    theirs = _collect("someone@else.com")
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    r = client.post("/seller/collect/bulk-delete",
                    data=json.dumps({"item_ids": [mine, theirs]}), content_type="application/json")
    assert r.get_json()["deleted"] == 1     # 본인 것만 삭제(타 셀러 보존)
    # 타 셀러 항목은 그대로
    remaining = [i["id"] for i in store.list_items(days=30, seller_ids={"someone@else.com"})]
    assert theirs in remaining


def test_bulk_update_works_across_alias_not_silent_noop(client):
    # 일괄 버튼(예: 상태 변경)도 별칭 불일치로 가짜 성공(무변경)되지 않아야 함
    from src.seller_console import collect_history_store as store
    iid = _collect("u1@example.com")
    with client.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "u1@example.com"
    r = client.post("/seller/collect/bulk-status",
                    data=json.dumps({"item_ids": [iid], "status": "archived"}),
                    content_type="application/json")
    assert r.status_code == 200 and r.get_json().get("ok") is True
    # 실제로 반영됐는지(재조회) — 무변경이면 가짜 성공
    item = store.get(iid, seller_ids={"u1", "u1@example.com"})
    assert item is not None and item.get("status") == "archived"


def test_store_delete_removes_inmemory_fallback_rows():
    # 시트 쓰기 실패 폴백 행도 삭제돼야(시트 분기 early-return 버그 수정)
    from src.seller_console import collect_history_store as store
    store._in_memory[:] = []
    iid = store.append(source="extension", url="https://x.com/p", title="t", seller_id="u1")
    n = store.delete([iid], seller_ids={"u1"})
    assert n == 1
    assert store.list_items(days=30, seller_ids={"u1"}) == []
