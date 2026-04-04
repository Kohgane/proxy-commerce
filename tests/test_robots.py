"""tests/test_robots.py — Phase 91: RobotsGenerator 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from src.seo.robots_generator import RobotsGenerator


@pytest.fixture
def gen():
    return RobotsGenerator(base_url="https://example.com")


class TestRobotsGenerator:
    def test_returns_string(self, gen):
        result = gen.generate()
        assert isinstance(result, str)

    def test_user_agent_all(self, gen):
        result = gen.generate()
        assert "User-agent: *" in result

    def test_disallow_admin(self, gen):
        result = gen.generate()
        assert "Disallow: /admin/" in result

    def test_disallow_api(self, gen):
        result = gen.generate()
        assert "Disallow: /api/" in result

    def test_allow_products(self, gen):
        result = gen.generate()
        assert "Allow: /products/" in result

    def test_allow_categories(self, gen):
        result = gen.generate()
        assert "Allow: /categories/" in result

    def test_sitemap_included(self, gen):
        result = gen.generate()
        assert "Sitemap:" in result
        assert "sitemap.xml" in result

    def test_custom_sitemap_url(self, gen):
        result = gen.generate(sitemap_url="https://example.com/sitemap-custom.xml")
        assert "https://example.com/sitemap-custom.xml" in result

    def test_extra_disallows(self, gen):
        result = gen.generate(extra_disallows=["/private/", "/internal/"])
        assert "Disallow: /private/" in result
        assert "Disallow: /internal/" in result

    def test_extra_allows(self, gen):
        result = gen.generate(extra_allows=["/shop/"])
        assert "Allow: /shop/" in result

    def test_base_url_in_sitemap(self):
        gen2 = RobotsGenerator(base_url="https://myshop.kr")
        result = gen2.generate()
        assert "https://myshop.kr/sitemap.xml" in result
