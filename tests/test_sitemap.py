"""tests/test_sitemap.py — Phase 91: SitemapGenerator 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest

from src.seo.sitemap_generator import SitemapGenerator, MAX_URLS_PER_SITEMAP


SAMPLE_PRODUCTS = [
    {"sku": f"SKU-{i:03}", "slug": f"product-{i}", "updated_at": "2026-04-01T00:00:00"}
    for i in range(5)
]

SAMPLE_CATEGORIES = [
    {"id": f"cat-{i}", "slug": f"category-{i}"}
    for i in range(3)
]


@pytest.fixture
def gen():
    return SitemapGenerator(base_url="https://example.com")


class TestSitemapGeneratorBasic:
    def test_returns_xml_string(self, gen):
        result = gen.generate()
        assert isinstance(result, str)
        assert result.startswith("<?xml")

    def test_contains_urlset(self, gen):
        result = gen.generate()
        assert "<urlset" in result
        assert "</urlset>" in result

    def test_contains_static_pages(self, gen):
        result = gen.generate()
        assert "<loc>https://example.com/</loc>" in result

    def test_contains_product_urls(self, gen):
        result = gen.generate(products=SAMPLE_PRODUCTS)
        assert "product-0" in result
        assert "product-4" in result

    def test_contains_category_urls(self, gen):
        result = gen.generate(categories=SAMPLE_CATEGORIES)
        assert "category-0" in result

    def test_lastmod_present(self, gen):
        result = gen.generate()
        assert "<lastmod>" in result

    def test_changefreq_present(self, gen):
        result = gen.generate()
        assert "<changefreq>" in result

    def test_priority_present(self, gen):
        result = gen.generate()
        assert "<priority>" in result

    def test_base_url_respected(self):
        gen2 = SitemapGenerator(base_url="https://myshop.kr")
        result = gen2.generate()
        assert "<loc>https://myshop.kr/</loc>" in result

    def test_no_products_or_categories(self, gen):
        result = gen.generate(products=None, categories=None)
        assert "<url>" in result

    def test_product_without_slug_uses_sku(self, gen):
        products = [{"sku": "MY-SKU-001"}]
        result = gen.generate(products=products)
        assert "my-sku-001" in result


class TestSitemapIndex:
    def test_single_sitemap_for_small_count(self, gen):
        result = gen.generate_index(products=SAMPLE_PRODUCTS)
        assert result["index"] is None
        assert len(result["sitemaps"]) == 1

    def test_index_generated_for_large_count(self):
        gen = SitemapGenerator(base_url="https://example.com")
        large_products = [{"sku": f"SKU-{i}", "slug": f"product-{i}"} for i in range(MAX_URLS_PER_SITEMAP + 10)]
        result = gen.generate_index(products=large_products)
        assert result["index"] is not None
        assert "<sitemapindex" in result["index"]
        assert len(result["sitemaps"]) >= 2

    def test_index_contains_sitemap_locs(self):
        gen = SitemapGenerator(base_url="https://example.com")
        large_products = [{"sku": f"SKU-{i}", "slug": f"product-{i}"} for i in range(MAX_URLS_PER_SITEMAP + 10)]
        result = gen.generate_index(products=large_products)
        assert "sitemap-1.xml" in result["index"]

    def test_each_chunk_is_valid_xml(self):
        gen = SitemapGenerator(base_url="https://example.com")
        large_products = [{"sku": f"SKU-{i}", "slug": f"product-{i}"} for i in range(MAX_URLS_PER_SITEMAP + 10)]
        result = gen.generate_index(products=large_products)
        for sitemap_xml in result["sitemaps"]:
            assert "<?xml" in sitemap_xml
            assert "<urlset" in sitemap_xml
