"""tests/test_i18n_screens_v16.py — v16 후속: i18n 화면 확장(주문·마켓 EN/KO)."""
from __future__ import annotations
import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_orders_ko_default(client):
    h = client.get("/seller/orders").get_data(as_text=True)
    assert "마켓" in h and "검색" in h and "CSV 내보내기" in h


def test_orders_english(client):
    client.set_cookie("kgp_lang", "en")
    h = client.get("/seller/orders").get_data(as_text=True)
    assert "Market" in h and "Search" in h and "Export CSV" in h


def test_markets_english(client):
    client.set_cookie("kgp_lang", "en")
    h = client.get("/seller/markets").get_data(as_text=True)
    assert "Market product status" in h and "Refresh" in h


def test_i18n_keys_have_both_langs():
    from src.seller_console.i18n import STRINGS
    for key, entry in STRINGS.items():
        assert entry.get("ko") and entry.get("en"), f"{key} ko/en 누락"
