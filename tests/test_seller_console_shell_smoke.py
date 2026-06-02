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


def test_seller_console_shell_smoke(client):
    routes = [
        "/seller/",
        "/seller/collect",
        "/seller/pricing",
        "/seller/markets",
        "/seller/catalog",
    ]

    for route in routes:
        resp = client.get(route)
        assert resp.status_code == 200, route
        html = resp.get_data(as_text=True)
        assert 'data-testid="seller-console-shell"' in html
        assert 'data-testid="seller-sidebar"' in html
