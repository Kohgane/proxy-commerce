"""tests/test_region_banner_i18n.py — 외국인 지역/언어 배너 (Phase 268, v9 P1)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ROOT_REDIRECT", "landing")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_banner_shown_for_foreign_visitor(client):
    html = client.get("/", headers={"Accept-Language": "en-US,en;q=0.9"}).get_data(as_text=True)
    assert "Choose your language" in html
    assert "/i18n/set?lang=en" in html


def test_banner_hidden_for_korean(client):
    html = client.get("/", headers={"Accept-Language": "ko-KR,ko;q=0.9"}).get_data(as_text=True)
    assert "Choose your language" not in html


def test_set_lang_en_sets_cookie_and_redirects(client):
    resp = client.get("/i18n/set?lang=en&next=/")
    assert resp.status_code == 302
    cookies = resp.headers.getlist("Set-Cookie")
    assert any("kgp_lang=en" in c for c in cookies)
    assert any("kgp_region_dismissed=1" in c for c in cookies)


def test_landing_renders_english_when_lang_cookie_en(client):
    client.set_cookie("kgp_lang", "en")
    html = client.get("/").get_data(as_text=True)
    assert "Cross over." in html             # 실제 EN 카피로 전환(가짜 아님, v40)
    assert "Start free" in html
    # 이미 선택 → 배너 안 뜸
    assert "Choose your language" not in html


def test_dismiss_hides_banner_for_foreign(client):
    client.set_cookie("kgp_region_dismissed", "1")
    html = client.get("/", headers={"Accept-Language": "en-US"}).get_data(as_text=True)
    assert "Choose your language" not in html
