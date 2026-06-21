"""tests/test_collect_trace_v9.py — '수집 성공인데 이력에 없음' 재현/회귀 가드 (Phase 266, v9 P0).

브리프 요구: 확장 수집 1건 → 같은 seller_id로 이력 조회 시 +1(즉시 노출) 보장.
+ user_id/email 별칭으로 저장돼도 본인 이력에 보이는 관용 매칭.
"""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

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
    chs._in_memory.clear()
    yield
    chs._in_memory.clear()


def test_extension_collect_appears_in_history_same_seller(client):
    """확장 수집(토큰 user_id=u1) → 세션 user_id=u1로 이력 조회 시 그 상품이 보인다."""
    with patch("src.api.extension_api._require_token", return_value={"user_id": "u1", "scopes": ["collect.write"]}), \
         patch("src.api.extension_api._upsert_catalog", return_value="cat1"), \
         patch("src.api.extension_api._notify_telegram"):
        r = client.post("/api/v1/collect/extension",
                        data=json.dumps({"url": "https://shop/x", "title": "추적가방", "translate": False}),
                        content_type="application/json",
                        headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    # 같은 사용자로 이력 페이지 → 그 상품이 보여야 한다(저장 seller_id == 조회 seller_id)
    with client.session_transaction() as sess:
        sess["user_id"] = "u1"
    html = client.get("/seller/collect/history").get_data(as_text=True)
    assert "추적가방" in html


def test_history_tolerant_identity_email_vs_userid(client):
    """저장은 email seller_id, 조회는 user_id 세션이어도 본인 이력에 보인다(별칭 관용)."""
    from src.seller_console import collect_history_store as chs
    chs.append(source="extension", url="https://shop/y", title="별칭상품", seller_id="me@x.com")
    with client.session_transaction() as sess:
        sess["user_id"] = "uA"
        sess["user_email"] = "me@x.com"
    html = client.get("/seller/collect/history").get_data(as_text=True)
    assert "별칭상품" in html


def test_other_seller_item_not_visible(client):
    """타 셀러 항목은 여전히 안 보인다(관용 매칭이 누출되지 않음)."""
    from src.seller_console import collect_history_store as chs
    chs.append(source="extension", url="https://shop/z", title="남의상품", seller_id="someone-else")
    with client.session_transaction() as sess:
        sess["user_id"] = "uA"
        sess["user_email"] = "me@x.com"
    html = client.get("/seller/collect/history").get_data(as_text=True)
    assert "남의상품" not in html
