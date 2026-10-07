from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_seller_analytics_view_renders(monkeypatch):
    from src.order_webhook import app

    app.config["TESTING"] = True
    # Z7: BI는 오너 풀(공유 마켓) 데이터 — 관리자·가족만 본다. 일반 가입자는 빈 상태(test_z7_orders_scope).
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = "seller-1"
            sess["user_role"] = "admin"
        resp = client.get("/seller/analytics")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "BI" in html
    assert "베스트셀러" in html

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = "seller-1"
            sess["user_role"] = "seller"
        html = client.get("/seller/analytics").get_data(as_text=True)
    assert "BI" in html and "베스트셀러" not in html
    assert "아직 이 계정의 판매 데이터가 없습니다" in html
