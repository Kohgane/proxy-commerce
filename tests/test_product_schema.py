"""tests/test_product_schema.py — Unified Product schema tests.

schemas/product.py 의 Product 모델, validators, fixtures 를 검증한다.
이슈 #85: 수집기/퍼블리셔용 단일 Product 스키마 정의.
"""
from __future__ import annotations

import sys
import os

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from schemas.product import (  # noqa: E402
    Product,
    ProductOption,
    StockStatus,
    SUPPORTED_CURRENCIES,
)


# ──────────────────────────────────────────────────────────
# Fixtures — 10개 샘플 상품
# ──────────────────────────────────────────────────────────

FIXTURE_PRODUCTS = [
    {
        "source": "musinsa",
        "source_product_id": "MSS-001",
        "source_url": "https://www.musinsa.com/products/MSS-001",
        "brand": "포터",
        "title": "포터 탱커 토트백",
        "description": "일본 브랜드 포터의 대표 탱커 시리즈 토트백",
        "currency": "KRW",
        "cost_price": 120000.0,
        "sell_price": 150000.0,
        "images": ["https://img.musinsa.com/MSS-001-main.jpg"],
        "options": [{"name": "색상", "values": ["블랙", "카키"]}],
        "stock_status": "in_stock",
    },
    {
        "source": "rakuten",
        "source_product_id": "RAK-0042",
        "source_url": "https://item.rakuten.co.jp/shop/RAK-0042",
        "brand": "MEMO",
        "title": "MEMO Paris Perfume 50ml",
        "description": "파리 메종 퍼퓨머리의 시그니처 향수",
        "currency": "JPY",
        "cost_price": 18000.0,
        "sell_price": 22000.0,
        "images": [
            "https://img.rakuten.co.jp/RAK-0042-front.jpg",
            "https://img.rakuten.co.jp/RAK-0042-side.jpg",
        ],
        "stock_status": "in_stock",
    },
    {
        "source": "amazon_us",
        "source_product_id": "B08XYZ1234",
        "source_url": "https://www.amazon.com/dp/B08XYZ1234",
        "brand": "Apple",
        "title": "Apple AirPods Pro (2nd Gen)",
        "description": "Active Noise Cancellation, Adaptive Transparency",
        "currency": "USD",
        "cost_price": 199.0,
        "sell_price": 249.0,
        "images": ["https://m.media-amazon.com/images/airpods-pro.jpg"],
        "options": [{"name": "Storage", "values": ["Standard"]}],
        "stock_status": "in_stock",
    },
    {
        "source": "taobao",
        "source_product_id": "TB-9988",
        "source_url": "https://item.taobao.com/item.htm?id=9988",
        "brand": None,
        "title": "남성 캐주얼 린넨 셔츠",
        "description": "통기성 좋은 린넨 소재 여름 셔츠",
        "currency": "CNY",
        "cost_price": 89.0,
        "sell_price": 120.0,
        "images": ["https://img.alicdn.com/TB-9988.jpg"],
        "options": [
            {"name": "사이즈", "values": ["S", "M", "L", "XL"]},
            {"name": "색상", "values": ["화이트", "네이비"]},
        ],
        "stock_status": "in_stock",
    },
    {
        "source": "hktv",
        "source_product_id": "HKT-5001",
        "source_url": "https://www.hktvmall.com/HKT-5001",
        "brand": "SK-II",
        "title": "SK-II Facial Treatment Essence 230ml",
        "description": "피테라 성분 페이셜 에센스",
        "currency": "HKD",
        "cost_price": 650.0,
        "sell_price": 780.0,
        "images": ["https://cdn.hktvmall.com/SKII-essence.jpg"],
        "stock_status": "low_stock",
    },
    {
        "source": "musinsa",
        "source_product_id": "MSS-OUT-002",
        "source_url": "https://www.musinsa.com/products/MSS-OUT-002",
        "brand": "아크네",
        "title": "아크네 스튜디오 울 스카프",
        "description": "아이코닉 페이스 패치 울 스카프 (한정판)",
        "currency": "KRW",
        "cost_price": 280000.0,
        "sell_price": 350000.0,
        "images": ["https://img.musinsa.com/MSS-OUT-002.jpg"],
        "stock_status": "out_of_stock",
    },
    {
        "source": "yahoo_japan",
        "source_product_id": "YJ-77712",
        "source_url": "https://shopping.yahoo.co.jp/products/YJ-77712",
        "brand": "Supreme",
        "title": "Supreme Box Logo Hoodie",
        "description": "Supreme FW23 박스 로고 후드티",
        "currency": "JPY",
        "cost_price": 35000.0,
        "sell_price": 80000.0,
        "images": ["https://img.yahoo.co.jp/supreme-hoodie.jpg"],
        "options": [{"name": "Size", "values": ["S", "M", "L"]}],
        "stock_status": "unknown",
    },
    {
        "source": "amazon_sg",
        "source_product_id": "SG-B09ABC",
        "source_url": "https://www.amazon.sg/dp/B09ABC",
        "brand": "Dyson",
        "title": "Dyson V15 Detect Vacuum",
        "description": "레이저 먼지 감지 무선 청소기",
        "currency": "SGD",
        "cost_price": 699.0,
        "sell_price": 899.0,
        "images": ["https://images-na.ssl-images-amazon.com/dyson-v15.jpg"],
        "stock_status": "in_stock",
    },
    {
        "source": "farfetch",
        "source_product_id": "FF-GUCCI-2024",
        "source_url": "https://www.farfetch.com/shopping/FF-GUCCI-2024",
        "brand": "Gucci",
        "title": "Gucci GG Canvas Tote Bag",
        "description": "구찌 GG 캔버스 토트백 (베이지/에보니)",
        "currency": "EUR",
        "cost_price": 850.0,
        "sell_price": 1100.0,
        "images": [
            "https://cdn-images.farfetch.com/gucci-tote-front.jpg",
            "https://cdn-images.farfetch.com/gucci-tote-back.jpg",
        ],
        "options": [{"name": "Size", "values": ["Small", "Medium"]}],
        "stock_status": "low_stock",
    },
    {
        "source": "selfridges",
        "source_product_id": "SELF-NB-990",
        "source_url": "https://www.selfridges.com/SELF-NB-990",
        "brand": "New Balance",
        "title": "New Balance 990v6 Made in USA",
        "description": "미국 생산 990v6 클래식 러닝화",
        "currency": "GBP",
        "cost_price": 160.0,
        "sell_price": 200.0,
        "images": ["https://assets.selfridges.com/nb-990v6.jpg"],
        "options": [
            {"name": "Size (UK)", "values": ["7", "8", "9", "10", "11"]},
            {"name": "Width", "values": ["D", "2E"]},
        ],
        "stock_status": "in_stock",
    },
]


@pytest.fixture
def valid_product_data():
    """가장 기본적인 유효한 상품 데이터."""
    return {
        "source": "musinsa",
        "source_product_id": "MSS-001",
        "source_url": "https://www.musinsa.com/products/MSS-001",
        "title": "포터 탱커 토트백",
        "currency": "KRW",
        "cost_price": 120000.0,
        "images": ["https://img.musinsa.com/MSS-001-main.jpg"],
    }


# ──────────────────────────────────────────────────────────
# 필드 존재 & 타입 테스트
# ──────────────────────────────────────────────────────────

class TestProductFields:
    def test_required_fields_present(self, valid_product_data):
        """필수 필드가 모두 있으면 생성에 성공한다."""
        p = Product(**valid_product_data)
        assert p.source == "musinsa"
        assert p.source_product_id == "MSS-001"
        assert p.source_url == "https://www.musinsa.com/products/MSS-001"
        assert p.title == "포터 탱커 토트백"
        assert p.currency == "KRW"
        assert p.cost_price == 120000.0

    def test_optional_fields_default_none_or_empty(self, valid_product_data):
        """선택 필드가 제공되지 않으면 기본값을 가진다."""
        p = Product(**valid_product_data)
        assert p.brand is None
        assert p.description is None
        assert p.sell_price is None
        assert p.options == []
        assert p.stock_status == StockStatus.UNKNOWN

    def test_thumbnail_auto_set_from_images(self, valid_product_data):
        """thumbnail 미제공 시 첫 번째 이미지로 자동 설정."""
        p = Product(**valid_product_data)
        assert p.thumbnail == valid_product_data["images"][0]

    def test_thumbnail_not_overridden_when_provided(self, valid_product_data):
        """thumbnail 이 제공되면 덮어쓰지 않는다."""
        data = {**valid_product_data, "thumbnail": "https://example.com/thumb.jpg"}
        p = Product(**data)
        assert p.thumbnail == "https://example.com/thumb.jpg"

    def test_options_list_of_product_option(self, valid_product_data):
        """options 필드가 ProductOption 목록으로 파싱된다."""
        data = {
            **valid_product_data,
            "options": [{"name": "색상", "values": ["블랙", "화이트"]}],
        }
        p = Product(**data)
        assert len(p.options) == 1
        assert isinstance(p.options[0], ProductOption)
        assert p.options[0].name == "색상"
        assert "블랙" in p.options[0].values


# ──────────────────────────────────────────────────────────
# 필수 필드 누락 검증
# ──────────────────────────────────────────────────────────

class TestRequiredFieldValidation:
    @pytest.mark.parametrize("field", [
        name
        for name, info in Product.model_fields.items()
        if info.is_required()
    ])
    def test_missing_required_field_raises_validation_error(self, valid_product_data, field):
        """필수 필드 누락 시 ValidationError 가 발생한다."""
        data = {k: v for k, v in valid_product_data.items() if k != field}
        with pytest.raises(ValidationError) as exc_info:
            Product(**data)
        errors = exc_info.value.errors()
        fields_in_errors = {e["loc"][0] for e in errors}
        assert field in fields_in_errors


# ──────────────────────────────────────────────────────────
# title validator 테스트
# ──────────────────────────────────────────────────────────

class TestTitleValidator:
    def test_empty_title_raises_error(self, valid_product_data):
        """빈 title 은 ValidationError."""
        with pytest.raises(ValidationError):
            Product(**{**valid_product_data, "title": ""})

    def test_whitespace_only_title_raises_error(self, valid_product_data):
        """공백만 있는 title 은 ValidationError."""
        with pytest.raises(ValidationError):
            Product(**{**valid_product_data, "title": "   "})

    def test_title_is_stripped(self, valid_product_data):
        """title 앞뒤 공백이 제거된다."""
        p = Product(**{**valid_product_data, "title": "  포터 토트백  "})
        assert p.title == "포터 토트백"


# ──────────────────────────────────────────────────────────
# currency validator 테스트
# ──────────────────────────────────────────────────────────

class TestCurrencyValidator:
    @pytest.mark.parametrize("currency", list(SUPPORTED_CURRENCIES))
    def test_supported_currencies_accepted(self, valid_product_data, currency):
        """지원 통화는 모두 허용된다."""
        p = Product(**{**valid_product_data, "currency": currency})
        assert p.currency == currency

    @pytest.mark.parametrize("alias, expected", [
        ("US", "USD"),
        ("KR", "KRW"),
        ("JP", "JPY"),
        ("CN", "CNY"),
    ])
    def test_currency_aliases_normalized(self, valid_product_data, alias, expected):
        """통화 별칭이 표준 코드로 정규화된다."""
        p = Product(**{**valid_product_data, "currency": alias})
        assert p.currency == expected

    def test_lowercase_currency_accepted(self, valid_product_data):
        """소문자 통화 코드도 허용한다."""
        p = Product(**{**valid_product_data, "currency": "usd"})
        assert p.currency == "USD"

    def test_unsupported_currency_raises_error(self, valid_product_data):
        """지원하지 않는 통화는 ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Product(**{**valid_product_data, "currency": "XYZ"})
        assert any(
            "unsupported currency" in str(e["msg"]).lower()
            for e in exc_info.value.errors()
        )


# ──────────────────────────────────────────────────────────
# cost_price validator 테스트
# ──────────────────────────────────────────────────────────

class TestCostPriceValidator:
    def test_zero_cost_price_accepted(self, valid_product_data):
        """cost_price 가 0 이면 허용된다."""
        p = Product(**{**valid_product_data, "cost_price": 0.0})
        assert p.cost_price == 0.0

    def test_positive_cost_price_accepted(self, valid_product_data):
        """양수 cost_price 는 허용된다."""
        p = Product(**{**valid_product_data, "cost_price": 9999.99})
        assert p.cost_price == 9999.99

    def test_negative_cost_price_raises_error(self, valid_product_data):
        """음수 cost_price 는 ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Product(**{**valid_product_data, "cost_price": -1.0})
        assert any(
            "non-negative" in str(e["msg"])
            for e in exc_info.value.errors()
        )


# ──────────────────────────────────────────────────────────
# images validator 테스트
# ──────────────────────────────────────────────────────────

class TestImagesValidator:
    def test_empty_images_list_raises_error(self, valid_product_data):
        """이미지 목록이 비어 있으면 ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Product(**{**valid_product_data, "images": []})
        assert any(
            "image" in str(e["msg"]).lower()
            for e in exc_info.value.errors()
        )

    def test_multiple_images_accepted(self, valid_product_data):
        """여러 이미지 URL 이 허용된다."""
        images = [
            "https://example.com/img1.jpg",
            "https://example.com/img2.jpg",
        ]
        p = Product(**{**valid_product_data, "images": images})
        assert len(p.images) == 2


# ──────────────────────────────────────────────────────────
# stock_status 테스트
# ──────────────────────────────────────────────────────────

class TestStockStatus:
    @pytest.mark.parametrize("status", [
        "in_stock", "out_of_stock", "low_stock", "unknown",
    ])
    def test_valid_stock_statuses_accepted(self, valid_product_data, status):
        """유효한 stock_status 값은 모두 허용된다."""
        p = Product(**{**valid_product_data, "stock_status": status})
        assert p.stock_status == StockStatus(status)

    def test_invalid_stock_status_raises_error(self, valid_product_data):
        """유효하지 않은 stock_status 는 ValidationError."""
        with pytest.raises(ValidationError):
            Product(**{**valid_product_data, "stock_status": "discontinued"})

    def test_default_stock_status_is_unknown(self, valid_product_data):
        """stock_status 미제공 시 기본값은 UNKNOWN."""
        p = Product(**valid_product_data)
        assert p.stock_status == StockStatus.UNKNOWN


# ──────────────────────────────────────────────────────────
# ProductOption 테스트
# ──────────────────────────────────────────────────────────

class TestProductOption:
    def test_valid_option(self):
        """유효한 옵션 생성."""
        opt = ProductOption(name="색상", values=["블랙", "화이트"])
        assert opt.name == "색상"
        assert len(opt.values) == 2

    def test_option_missing_name_raises_error(self):
        """name 누락 시 ValidationError."""
        with pytest.raises(ValidationError):
            ProductOption(values=["블랙"])

    def test_option_missing_values_raises_error(self):
        """values 누락 시 ValidationError."""
        with pytest.raises(ValidationError):
            ProductOption(name="색상")


# ──────────────────────────────────────────────────────────
# 10개 샘플 fixture 통과 테스트
# ──────────────────────────────────────────────────────────

class TestFixtureProducts:
    @pytest.mark.parametrize("data", FIXTURE_PRODUCTS)
    def test_all_fixtures_pass_validation(self, data):
        """10개 샘플 fixture 가 모두 유효성 검사를 통과한다."""
        p = Product(**data)
        assert p.source
        assert p.source_product_id
        assert p.title
        assert p.cost_price >= 0
        assert len(p.images) >= 1
        assert p.thumbnail is not None

    def test_fixture_count(self):
        """정확히 10개의 fixture 가 존재한다."""
        assert len(FIXTURE_PRODUCTS) == 10

    def test_fixtures_cover_all_supported_currencies(self):
        """fixture 가 모든 지원 통화 중 다양한 통화를 포함한다."""
        currencies_used = {Product(**d).currency for d in FIXTURE_PRODUCTS}
        # 적어도 5개 이상의 서로 다른 통화를 커버해야 함
        assert len(currencies_used) >= 5

    def test_fixtures_cover_all_stock_statuses(self):
        """fixture 가 모든 stock_status 값을 커버한다."""
        statuses = {Product(**d).stock_status for d in FIXTURE_PRODUCTS}
        assert StockStatus.IN_STOCK in statuses
        assert StockStatus.OUT_OF_STOCK in statuses
        assert StockStatus.LOW_STOCK in statuses
        assert StockStatus.UNKNOWN in statuses


# ──────────────────────────────────────────────────────────
# 직렬화 테스트
# ──────────────────────────────────────────────────────────

class TestProductSerialization:
    def test_model_dump_contains_all_fields(self, valid_product_data):
        """model_dump() 가 스키마의 모든 필드를 포함한다."""
        p = Product(**valid_product_data)
        d = p.model_dump()
        expected_keys = set(Product.model_fields.keys())
        assert expected_keys == set(d.keys())

    def test_model_dump_json_roundtrip(self, valid_product_data):
        """JSON 직렬화 → 역직렬화 라운드트립이 동일한 모델을 반환한다."""
        p = Product(**valid_product_data)
        json_str = p.model_dump_json()
        p2 = Product.model_validate_json(json_str)
        assert p == p2

    def test_validation_error_contains_field_info(self, valid_product_data):
        """ValidationError 에 오류 필드 정보가 포함된다."""
        data = {**valid_product_data, "cost_price": -500.0, "title": ""}
        with pytest.raises(ValidationError) as exc_info:
            Product(**data)
        errors = exc_info.value.errors()
        error_fields = {e["loc"][0] for e in errors}
        assert "cost_price" in error_fields or "title" in error_fields
