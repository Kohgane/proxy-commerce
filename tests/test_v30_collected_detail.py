"""tests/test_v30_collected_detail.py — v30 P0: 수집한 상품 클릭 시 404 회귀 가드.

원인: 목록은 관용 식별자(seller_ids=user_id+email)로 보여주는데 상세/저장은 exact
seller_id로 조회 → 별칭(user_id vs email) 불일치 시 목록엔 보이는데 클릭하면 404.
수정: _get_owned_item으로 상세·저장을 목록과 같은 스코프로 통일.
이 테스트를 CI 게이트(pytest)에 둬 재발(회귀) 차단.
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
def _clean_store():
    from src.seller_console import collect_history_store as store
    store._in_memory[:] = []
    yield
    store._in_memory[:] = []


def _collect(seller_id: str, *, source: str = "extension") -> str:
    from src.seller_console import collect_history_store as store
    return store.append(source=source, url="https://taobao.com/item/1",
                        title="테스트 상품", price="100", currency="CNY", seller_id=seller_id)


def test_detail_200_when_stored_under_email_alias(client):
    # 저장 seller_id = 이메일, 세션 user_id = 다른 별칭 → 목록과 같은 본인 → 상세 200(404 아님)
    item_id = _collect("u1@example.com")
    with client.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "u1@example.com"
    r = client.get(f"/seller/collect/preview/{item_id}")
    assert r.status_code == 200, "별칭 불일치로 본인 상품이 404 (v30 회귀)"


@pytest.mark.parametrize("source", ["extension", "bookmarklet", "manual", "bulk"])
def test_detail_200_for_every_collect_source(client, source):
    item_id = _collect("u1", source=source)
    with client.session_transaction() as s:
        s["user_id"] = "u1"
    r = client.get(f"/seller/collect/preview/{item_id}")
    assert r.status_code == 200, f"{source} 경로 수집 항목 클릭 404"


def test_other_sellers_item_not_leaked(client):
    # v39 F: 타 셀러 항목 접근 → 404 페이지 대신 '수집 실패' 빈 상태(200)지만 데이터 누출은 0.
    item_id = _collect("someone-else@example.com")
    with client.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "u1@example.com"
    r = client.get(f"/seller/collect/preview/{item_id}")
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "수집 실패" in body                       # 정직 빈 상태(404 페이지 아님)
    assert "수집 상품 편집" not in body              # 타인 항목 편집폼 미노출(누출 0)


def test_save_200_across_alias(client):
    item_id = _collect("u1@example.com")
    with client.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "u1@example.com"
    r = client.post(f"/seller/collect/preview/{item_id}/save",
                    data=json.dumps({"title": "수정됨", "price": "100", "currency": "CNY"}),
                    content_type="application/json")
    assert r.status_code == 200, "별칭 불일치로 저장 404/실패 (v30)"
    body = r.get_json()
    assert body.get("ok") is True
