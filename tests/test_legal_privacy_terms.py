"""tests/test_legal_privacy_terms.py — /privacy, /terms 페이지 검증 (Phase 150)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    app.secret_key = "test-secret-legal-150"
    with app.test_client() as c:
        yield c


class TestPrivacyPage:
    def test_privacy_returns_200(self, client):
        resp = client.get("/privacy")
        assert resp.status_code == 200

    def test_privacy_contains_korean_title(self, client):
        html = client.get("/privacy").get_data(as_text=True)
        assert "개인정보처리방침" in html

    def test_privacy_contains_collection_info(self, client):
        html = client.get("/privacy").get_data(as_text=True)
        assert "수집 정보" in html

    def test_privacy_contains_contact(self, client):
        html = client.get("/privacy").get_data(as_text=True)
        # 연락처 정보가 있어야 함 (이메일 또는 문의 섹션)
        assert "문의" in html or "@" in html


class TestTermsPage:
    def test_terms_returns_200(self, client):
        resp = client.get("/terms")
        assert resp.status_code == 200

    def test_terms_contains_korean_title(self, client):
        html = client.get("/terms").get_data(as_text=True)
        assert "이용약관" in html

    def test_terms_contains_user_responsibility(self, client):
        html = client.get("/terms").get_data(as_text=True)
        assert "사용자 책임" in html


class TestPlainTextEndpoints:
    def test_privacy_txt_returns_200(self, client):
        resp = client.get("/privacy.txt")
        assert resp.status_code == 200

    def test_privacy_txt_content_type(self, client):
        resp = client.get("/privacy.txt")
        assert "text/plain" in resp.content_type

    def test_privacy_txt_contains_korean(self, client):
        text = client.get("/privacy.txt").get_data(as_text=True)
        assert "개인정보처리방침" in text

    def test_terms_txt_returns_200(self, client):
        resp = client.get("/terms.txt")
        assert resp.status_code == 200

    def test_terms_txt_content_type(self, client):
        resp = client.get("/terms.txt")
        assert "text/plain" in resp.content_type

    def test_terms_txt_contains_korean(self, client):
        text = client.get("/terms.txt").get_data(as_text=True)
        assert "이용약관" in text
