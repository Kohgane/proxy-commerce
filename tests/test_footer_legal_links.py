"""tests/test_footer_legal_links.py — 셀러 콘솔 푸터에 법적 링크 존재 확인 (Phase 150)."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    app.secret_key = "test-secret-footer"
    with app.test_client() as c:
        yield c


class TestFooterLegalLinks:
    def test_seller_base_template_has_privacy_link(self):
        """_base.html 템플릿 소스에 /privacy 링크 포함 확인."""
        base_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "src",
            "seller_console",
            "templates",
            "_base.html",
        )
        with open(base_path, encoding="utf-8") as f:
            content = f.read()
        assert "/privacy" in content, "푸터에 /privacy 링크가 없습니다"

    def test_seller_base_template_has_terms_link(self):
        """_base.html 템플릿 소스에 /terms 링크 포함 확인."""
        base_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "src",
            "seller_console",
            "templates",
            "_base.html",
        )
        with open(base_path, encoding="utf-8") as f:
            content = f.read()
        assert "/terms" in content, "푸터에 /terms 링크가 없습니다"

    def test_seller_base_template_privacy_label(self):
        """_base.html 템플릿에 '개인정보처리방침' 텍스트 포함 확인."""
        base_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "src",
            "seller_console",
            "templates",
            "_base.html",
        )
        with open(base_path, encoding="utf-8") as f:
            content = f.read()
        assert "개인정보처리방침" in content

    def test_seller_base_template_terms_label(self):
        """_base.html 템플릿에 '이용약관' 텍스트 포함 확인."""
        base_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "src",
            "seller_console",
            "templates",
            "_base.html",
        )
        with open(base_path, encoding="utf-8") as f:
            content = f.read()
        assert "이용약관" in content
