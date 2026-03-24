"""tests/test_structured_data.py — StructuredDataGenerator 테스트."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.seo.structured_data import StructuredDataGenerator

SAMPLE_PRODUCT = {
    "sku": "SKU-001",
    "title_ko": "테스트 제품",
    "title_en": "Test Product",
    "description": "테스트 제품 설명",
    "category": "카테고리",
    "price_krw": 50000,
    "brand": "TestBrand",
    "image_url": "https://example.com/img.jpg",
    "in_stock": True,
}


@pytest.fixture
def generator():
    return StructuredDataGenerator()


class TestProductJsonLd:
    def test_product_jsonld_schema(self, generator):
        """Product JSON-LD에 @context, @type, name, sku가 있어야 한다."""
        result = generator.generate_product_jsonld(SAMPLE_PRODUCT)
        assert result["@context"] == "https://schema.org"
        assert result["@type"] == "Product"
        assert result["name"] == "테스트 제품"
        assert result["sku"] == "SKU-001"

    def test_product_jsonld_offers(self, generator):
        """offers에 price와 priceCurrency가 있어야 한다."""
        result = generator.generate_product_jsonld(SAMPLE_PRODUCT)
        offers = result["offers"]
        assert offers["@type"] == "Offer"
        assert "price" in offers
        assert offers["priceCurrency"] == "KRW"

    def test_product_jsonld_availability_in_stock(self, generator):
        """재고 있음 시 InStock URL이 설정되어야 한다."""
        result = generator.generate_product_jsonld(SAMPLE_PRODUCT)
        assert "InStock" in result["offers"]["availability"]

    def test_product_jsonld_availability_out_of_stock(self, generator):
        """재고 없음 시 OutOfStock URL이 설정되어야 한다."""
        product = {**SAMPLE_PRODUCT, "in_stock": False}
        result = generator.generate_product_jsonld(product)
        assert "OutOfStock" in result["offers"]["availability"]

    def test_product_jsonld_brand(self, generator):
        """brand 정보가 포함되어야 한다."""
        result = generator.generate_product_jsonld(SAMPLE_PRODUCT)
        assert result["brand"]["name"] == "TestBrand"


class TestBreadcrumbJsonLd:
    def test_breadcrumb_jsonld(self, generator):
        """BreadcrumbList JSON-LD 구조가 올바르게 생성되어야 한다."""
        path = ["홈", "전자제품", "이어폰"]
        result = generator.generate_breadcrumb_jsonld(path)
        assert result["@context"] == "https://schema.org"
        assert result["@type"] == "BreadcrumbList"
        assert len(result["itemListElement"]) == 3

    def test_breadcrumb_positions(self, generator):
        """BreadcrumbList의 position은 1부터 시작해야 한다."""
        path = ["홈", "카테고리"]
        result = generator.generate_breadcrumb_jsonld(path)
        positions = [item["position"] for item in result["itemListElement"]]
        assert positions == [1, 2]

    def test_breadcrumb_empty_path(self, generator):
        """빈 경로는 빈 itemListElement를 반환해야 한다."""
        result = generator.generate_breadcrumb_jsonld([])
        assert result["itemListElement"] == []


class TestOrganizationJsonLd:
    def test_organization_jsonld(self, generator):
        """Organization JSON-LD에 @type=Organization이 있어야 한다."""
        result = generator.generate_organization_jsonld()
        assert result["@context"] == "https://schema.org"
        assert result["@type"] == "Organization"
        assert "name" in result
        assert "url" in result
