"""tests/test_collect_consistency_p0.py — 수집 데이터 정직성 (v3 P0-2 + v4 P0, Phase 244).

- 대시보드 '오늘 수집' 카운트가 수집 이력 리스트와 동일 seller_id로 격리되어 일치.
- 확장 수집은 실제 저장(자기검증)됐을 때만 ok=true(가짜 성공 금지).
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
def _clear_store():
    from src.seller_console import collect_history_store as chs
    chs._in_memory.clear()
    yield
    chs._in_memory.clear()


# ── v3 P0-2: 대시보드 카운트 == 이력(셀러 격리) ──────────────────────────────

def test_today_kpi_is_seller_scoped():
    from src.seller_console import collect_history_store as chs
    from src.seller_console.data_aggregator import get_today_kpi
    chs.append(source="extension", url="https://x/1", title="a", seller_id="s1")
    chs.append(source="extension", url="https://x/2", title="b", seller_id="s1")
    chs.append(source="extension", url="https://x/3", title="c", seller_id="s2")

    assert get_today_kpi(seller_id="s1")["new_products_collected"] == 2
    assert get_today_kpi(seller_id="s2")["new_products_collected"] == 1
    # 다른(빈) 셀러는 0 — 가짜 카운트 금지
    assert get_today_kpi(seller_id="nobody")["new_products_collected"] == 0


def test_dashboard_count_matches_history_list_for_seller():
    """같은 seller_id에서 KPI 카운트와 이력 summary가 일치."""
    from src.seller_console import collect_history_store as chs
    from src.seller_console.data_aggregator import get_today_kpi
    for i in range(3):
        chs.append(source="extension", url=f"https://x/{i}", title=f"t{i}", seller_id="s1")
    kpi = get_today_kpi(seller_id="s1")["new_products_collected"]
    listed = chs.summary(seller_id="s1")["today"]
    assert kpi == listed == 3


# ── v4 P0: 확장 수집 정직성(저장 실패 시 ok=false) ───────────────────────────

def _auth(**over):
    base = {"user_id": "u1", "scopes": ["collect.write"]}
    base.update(over)
    return base


def test_extension_collect_honest_failure_when_not_saved(client):
    """append가 실패하면 가짜 성공 대신 502 ok=false."""
    def _boom(**kwargs):
        raise RuntimeError("store down")
    with patch("src.api.extension_api._require_token", return_value=_auth()), \
         patch("src.api.extension_api._upsert_catalog", return_value="cat1"), \
         patch("src.api.extension_api._notify_telegram"), \
         patch("src.seller_console.collect_history_store.append", _boom):
        resp = client.post("/api/v1/collect/extension",
                           data=json.dumps({"url": "https://shop/x", "title": "t", "translate": False}),
                           content_type="application/json",
                           headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 502
    assert resp.get_json()["ok"] is False


def test_extension_collect_honest_failure_when_verify_missing(client):
    """append는 id를 주지만 재조회(get)에서 안 보이면 저장 실패로 본다."""
    with patch("src.api.extension_api._require_token", return_value=_auth()), \
         patch("src.api.extension_api._upsert_catalog", return_value="cat1"), \
         patch("src.api.extension_api._notify_telegram"), \
         patch("src.seller_console.collect_history_store.append", return_value="hid"), \
         patch("src.seller_console.collect_history_store.get", return_value=None):
        resp = client.post("/api/v1/collect/extension",
                           data=json.dumps({"url": "https://shop/x", "title": "t", "translate": False}),
                           content_type="application/json",
                           headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 502
    assert resp.get_json()["ok"] is False


def test_extension_collect_success_when_really_saved(client):
    """실제 저장(자기검증 통과)되면 ok=true + item_id."""
    with patch("src.api.extension_api._require_token", return_value=_auth()), \
         patch("src.api.extension_api._upsert_catalog", return_value="cat1"), \
         patch("src.api.extension_api._notify_telegram"):
        resp = client.post("/api/v1/collect/extension",
                           data=json.dumps({"url": "https://shop/x", "title": "가방", "translate": False}),
                           content_type="application/json",
                           headers={"Authorization": "Bearer tok"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data.get("item_id")
