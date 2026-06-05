from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("SECRET_KEY", "test-secret")
    import src.order_webhook as wh

    wh.app.config["TESTING"] = True
    return wh.app


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


def test_shop_footer_links_are_real_routes(client):
    template = Path("src/shop/templates/shop/base.html").read_text(encoding="utf-8")
    assert 'href="/terms"' in template
    assert 'href="/privacy"' in template
    assert "href=\"#\"" not in template


def test_admin_sidebar_contains_core_pages(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "admin-user"
        sess["user_role"] = "admin"
    resp = client.get("/admin/products")
    html = resp.get_data(as_text=True)
    for path in (
        "/admin/",
        "/admin/products",
        "/admin/orders",
        "/admin/inventory",
        "/admin/diagnostics",
        "/admin/users",
        "/admin/env",
        "/admin/logs",
    ):
        assert path in html


def test_ai_listing_page_defines_retry_market_handler(client):
    resp = client.get("/seller/listing/ai-create")
    html = resp.get_data(as_text=True)
    assert "onclick='retryMarket(" in html
    assert "async function retryMarket(market)" in html
