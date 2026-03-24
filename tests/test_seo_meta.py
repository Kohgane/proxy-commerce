"""tests/test_seo_meta.py — MetaGenerator 테스트."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.seo.meta_generator import MetaGenerator

SAMPLE_PRODUCT = {
    "sku": "TEST-001",
    "title_ko": "고급 무선 이어폰",
    "title_en": "Premium Wireless Earphones",
    "category": "전자제품",
    "price_krw": 99000,
    "brand": "TechBrand",
    "image_url": "https://example.com/image.jpg",
    "features": ["노이즈 캔슬링", "30시간 배터리", "방수"],
}


@pytest.fixture
def generator():
    return MetaGenerator()


class TestMetaTitle:
    def test_meta_title_length(self, generator):
        """meta_title은 60자 이하여야 한다."""
        result = generator.generate_meta(SAMPLE_PRODUCT, language='ko')
        assert len(result["meta_title"]) <= 60

    def test_meta_title_contains_brand(self, generator):
        """meta_title에 브랜드명이 포함되어야 한다."""
        result = generator.generate_meta(SAMPLE_PRODUCT, language='ko')
        assert "TechBrand" in result["meta_title"]


class TestMetaDescription:
    def test_meta_description_length(self, generator):
        """meta_description은 160자 이하여야 한다."""
        result = generator.generate_meta(SAMPLE_PRODUCT, language='ko')
        assert len(result["meta_description"]) <= 160

    def test_meta_description_not_empty(self, generator):
        """meta_description은 비어 있지 않아야 한다."""
        result = generator.generate_meta(SAMPLE_PRODUCT, language='ko')
        assert result["meta_description"]


class TestOgTags:
    def test_og_tags_present(self, generator):
        """og_tags에 필수 키가 있어야 한다."""
        result = generator.generate_meta(SAMPLE_PRODUCT, language='ko')
        og = result["og_tags"]
        assert "og:title" in og
        assert "og:description" in og
        assert "og:type" in og

    def test_og_type_is_product(self, generator):
        """og:type은 'product'여야 한다."""
        result = generator.generate_meta(SAMPLE_PRODUCT, language='ko')
        assert result["og_tags"]["og:type"] == "product"


class TestMultilingual:
    def test_multilingual_ko(self, generator):
        """한국어 CTA가 포함되어야 한다."""
        result = generator.generate_meta(SAMPLE_PRODUCT, language='ko')
        assert "지금 구매하기" in result["meta_description"]

    def test_multilingual_en(self, generator):
        """영어 CTA가 포함되어야 한다."""
        result = generator.generate_meta(SAMPLE_PRODUCT, language='en')
        assert "Buy Now" in result["meta_description"]

    def test_multilingual_ja(self, generator):
        """일본어 CTA가 포함되어야 한다."""
        result = generator.generate_meta(SAMPLE_PRODUCT, language='ja')
        assert "今すぐ購入" in result["meta_description"]


class TestBulkGenerate:
    def test_bulk_generate_returns_correct_length(self, generator):
        """bulk_generate는 입력 목록과 동일한 길이를 반환해야 한다."""
        products = [SAMPLE_PRODUCT, SAMPLE_PRODUCT, SAMPLE_PRODUCT]
        results = generator.bulk_generate(products, language='ko')
        assert len(results) == 3

    def test_bulk_generate_empty_list(self, generator):
        """빈 목록 입력 시 빈 리스트를 반환해야 한다."""
        results = generator.bulk_generate([], language='ko')
        assert results == []
