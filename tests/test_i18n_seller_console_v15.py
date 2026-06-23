"""tests/test_i18n_seller_console_v15.py — v15 셀러 콘솔 i18n(한국어 기본 + 영어 1급) 가드."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_i18n_helper_ko_en_and_fallback():
    from src.seller_console.i18n import t, normalize_lang
    assert t("nav.home", "ko") == "홈(대시보드)"
    assert t("nav.home", "en") == "Home (Dashboard)"
    assert t("nav.collect", "en") == "Collect products"
    # 미지원 언어 → 기본(ko)
    assert normalize_lang("fr") == "ko"
    assert t("nav.home", "fr") == "홈(대시보드)"
    # 누락 키 → 키 자체 반환(누락이 보이게 — 정직)
    assert t("does.not.exist", "en") == "does.not.exist"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_default_korean_render(client):
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert 'lang="ko"' in html
    assert "홈(대시보드)" in html
    assert "i18n/set?lang=en" in html          # 언어 토글 노출


def test_english_render_via_cookie(client):
    client.set_cookie("kgp_lang", "en")
    html = client.get("/seller/dashboard").get_data(as_text=True)
    assert 'lang="en"' in html
    assert "Home (Dashboard)" in html          # 영어 1급 — 핵심 내비 영어로
    assert "Collect products" in html
    assert "New here?" in html                 # For Beginners 버튼도 영어
