"""tests/test_onboarding_wizard.py — For Beginners 키노트 온보딩 (Phase 253, v5)."""
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


def test_wizard_page_renders_steps(client):
    html = client.get("/seller/start").get_data(as_text=True)
    assert "코고가네" in html
    # 좌측 스텝퍼 + 단계 키워드(실제 동작으로 이어지는 단계들)
    for kw in ("구글로 시작", "마켓 연동", "확장", "첫 상품", "사업자"):
        assert kw in html
    # 실제 동작 경로가 박혀 있다(가이드만 아님)
    assert "/auth/google/start" in html
    assert "/seller/markets/connect" in html
    assert "/seller/manual-collect" in html


def test_wizard_accessible_without_login(client):
    """미로그인도 진입 가능(구글 로그인 단계가 첫 관문)."""
    resp = client.get("/seller/start")
    assert resp.status_code == 200
    assert "LOGGED_IN = false" in resp.get_data(as_text=True)


def test_dashboard_has_for_beginners_button(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert "For Beginners" in html
    assert "/seller/start" in html


def test_landing_has_for_beginners_button(client, monkeypatch):
    monkeypatch.setenv("ROOT_REDIRECT", "landing")
    from src.order_webhook import app
    with app.test_client() as c:
        html = c.get("/").get_data(as_text=True)
    assert "For Beginners" in html
    assert "/seller/start" in html
