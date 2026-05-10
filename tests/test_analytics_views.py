from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_seller_analytics_view_renders(monkeypatch):
    from src.order_webhook import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = "seller-1"
            sess["user_role"] = "seller"
        resp = client.get("/seller/analytics")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "BI" in html
    assert "베스트셀러" in html
