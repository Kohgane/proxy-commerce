from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_onboarding_page_available_and_has_steps():
    from src.order_webhook import app

    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/onboarding")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "처음 오셨나요?" in html
    assert "OAuth 로그인" in html
    assert "이메일 로그인" in html
    assert "비상 진입" in html

