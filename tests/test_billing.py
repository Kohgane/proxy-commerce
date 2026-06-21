"""tests/test_billing.py — 요금제·충전(쉽고 간편 결제) (Phase 258, v6)."""
from __future__ import annotations

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
    from src.seller_console import billing_store as bs
    bs._in_memory.clear()
    yield
    bs._in_memory.clear()


def test_billing_page_shows_plans(client):
    html = client.get("/seller/billing").get_data(as_text=True)
    assert "요금제" in html
    for label in ("Free", "Plus", "Pro"):
        assert label in html
    assert "무료 번역" in html


def test_select_free_activates(client):
    from src.seller_console import billing_store as bs
    r = client.post("/seller/billing/select", json={"plan": "free"})
    assert r.get_json()["ok"] is True
    assert bs.get_account("default")["plan"] == "free"


def test_select_paid_without_payment_is_honest(client, monkeypatch):
    """결제 미설정 시 유료 활성 금지 — 정직 안내(가짜 활성 없음)."""
    from src.seller_console import billing_store as bs
    monkeypatch.delenv("TOSS_CLIENT_KEY", raising=False)
    monkeypatch.delenv("TOSS_SECRET_KEY", raising=False)
    r = client.post("/seller/billing/select", json={"plan": "plus"})
    data = r.get_json()
    assert data.get("pay_unconfigured") is True
    assert bs.get_account("default")["plan"] == "free"  # 활성 안 됨


def test_paid_plan_unlocks_unlimited_translation():
    """활성 유료 플랜이면 번역 무제한(billing_store.is_unlimited)."""
    from src.seller_console import billing_store as bs
    bs.set_plan("s1", "plus")
    assert bs.is_unlimited("s1") is True
    assert bs.is_unlimited("nobody") is False


def test_select_rejects_unknown_plan(client):
    assert client.post("/seller/billing/select", json={"plan": "ultra"}).status_code == 400


def test_billing_in_nav(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "/seller/billing" in html
