"""tests/test_billing.py — 요금제·충전(쉽고 간편 결제) (Phase 258, v6)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class _FakeBillingWS:
    header = ["seller_id", "plan", "token_balance"]

    def __init__(self):
        self.rows = []

    def row_values(self, index):
        if index == 1 and self.rows:
            return list(self.header)
        return []

    def insert_row(self, row, index=1):
        if row and row[0] == "seller_id":
            return
        self.rows.insert(max(index - 2, 0), list(row))

    def get_all_records(self):
        return [dict(zip(self.header, row)) for row in self.rows]

    def get_all_values(self):
        return [list(self.header)] + [list(row) for row in self.rows]

    def update_cell(self, row_idx, col, val):
        self.rows[row_idx - 2][col - 1] = val

    def append_row(self, row):
        self.rows.append(list(row))


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


@pytest.fixture
def billing_sheet(monkeypatch):
    from src.seller_console import billing_store as bs
    ws = _FakeBillingWS()
    monkeypatch.setattr(bs, "_SHEET_ID", "sheet-test", raising=False)
    monkeypatch.setattr(bs, "_get_worksheet", lambda: ws)
    return bs, ws


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
    assert "준비 중" in (data.get("error") or "")
    assert bs.get_account("default")["plan"] == "free"  # 활성 안 됨


def test_select_paid_with_payment_returns_checkout_payload(client, monkeypatch):
    monkeypatch.setenv("TOSS_CLIENT_KEY", "test_ck")
    monkeypatch.setenv("TOSS_SECRET_KEY", "test_sk")
    r = client.post("/seller/billing/select", json={"plan": "plus"})
    data = r.get_json()
    assert data["ok"] is True
    assert data["checkout"] is True
    payload = data.get("checkout_payload") or {}
    assert payload.get("order_id", "").startswith("BILL-")
    assert payload.get("amount") == 19000
    assert payload.get("order_name")
    assert payload.get("success_url", "").endswith("/seller/billing/success")
    assert payload.get("fail_url", "").endswith("/seller/billing/fail")


def test_billing_success_confirms_and_activates_plan(client, monkeypatch):
    from src.seller_console import billing_store as bs
    monkeypatch.setenv("TOSS_CLIENT_KEY", "test_ck")
    monkeypatch.setenv("TOSS_SECRET_KEY", "test_sk")
    created = client.post("/seller/billing/select", json={"plan": "pro"}).get_json()["checkout_payload"]
    with patch("src.payments.toss.confirm_payment") as mocked_confirm:
        mocked_confirm.return_value = {"ok": True, "status": "DONE"}
        resp = client.get(
            f"/seller/billing/success?paymentKey=pk_test&orderId={created['order_id']}&amount={created['amount']}"
        )
    assert resp.status_code == 302
    assert bs.get_account("default")["plan"] == "pro"


def test_billing_success_does_not_activate_on_failed_confirm(client, monkeypatch):
    from src.seller_console import billing_store as bs
    monkeypatch.setenv("TOSS_CLIENT_KEY", "test_ck")
    monkeypatch.setenv("TOSS_SECRET_KEY", "test_sk")
    created = client.post("/seller/billing/select", json={"plan": "plus"}).get_json()["checkout_payload"]
    with patch("src.payments.toss.confirm_payment") as mocked_confirm:
        mocked_confirm.return_value = {"ok": False, "status": "FAILED"}
        resp = client.get(
            f"/seller/billing/success?paymentKey=pk_test&orderId={created['order_id']}&amount={created['amount']}"
        )
    assert resp.status_code == 302
    assert bs.get_account("default")["plan"] == "free"


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


def test_set_plan_verifies_sheet_commit(billing_sheet):
    bs, ws = billing_sheet
    acc = bs.set_plan("seller-1", "plus")
    assert acc["plan"] == "plus"
    assert acc["durable"] is True
    assert ws.rows == [["seller-1", "plus", "0"]]


def test_add_tokens_verifies_sheet_commit(billing_sheet):
    bs, ws = billing_sheet
    bs.set_plan("seller-1", "free")
    acc = bs.add_tokens("seller-1", 7)
    assert acc["token_balance"] == 7
    assert acc["durable"] is True
    assert ws.rows == [["seller-1", "free", "7"]]


def test_set_plan_honest_failure_when_sheet_write_breaks(billing_sheet, monkeypatch):
    bs, ws = billing_sheet

    def _boom(row):
        raise RuntimeError("append failed")

    monkeypatch.setattr(ws, "append_row", _boom)
    with pytest.raises(bs.BillingCommitError):
        bs.set_plan("seller-1", "pro")


def test_add_tokens_honest_failure_when_recheck_does_not_persist(billing_sheet, monkeypatch):
    bs, ws = billing_sheet
    bs.set_plan("seller-1", "free")

    def _no_persist(row_idx, col, val):
        return None

    monkeypatch.setattr(ws, "update_cell", _no_persist)
    with pytest.raises(bs.BillingCommitError):
        bs.add_tokens("seller-1", 3)
