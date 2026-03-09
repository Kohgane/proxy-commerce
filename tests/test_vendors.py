"""src/vendors/ 단위 테스트 — BaseVendor, PorterVendor, MemoPariVendor"""
import os
import sys
import pytest

# 패키지 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.vendors import get_vendor, VENDOR_REGISTRY, CATALOG_FIELDS
from src.vendors.base_vendor import BaseVendor
from src.vendors.porter import PorterVendor, PORTER_CATEGORIES, _clean_price as porter_clean_price
from src.vendors.memo_paris import MemoPariVendor, MEMO_COLLECTIONS, _clean_price as memo_clean_price


# ──────────────────────────────────────────────────────────
# 공통 픽스처
# ──────────────────────────────────────────────────────────

PORTER_RAW = {
    'title_ja': 'タンカー 2WAYブリーフケース',
    'title_en': '',
    'title_ko': '',
    'src_url': 'https://www.yoshidakaban.com/product/100000.html',
    'price': '¥30,800',
    'category_ja': 'タンカー',
    'images': 'https://www.yoshidakaban.com/img/100000_1.jpg,https://www.yoshidakaban.com/img/100000_2.jpg',
    'stock': 0,
    'status': 'active',
}

MEMO_RAW = {
    'title_en': 'African Leather Eau de Parfum',
    'title_fr': 'African Leather Eau de Parfum',
    'title_ko': '',
    'src_url': 'https://www.memoparis.com/products/african-leather',
    'price': '€250.00',
    'fragrance_type': 'Eau de Parfum',
    'images': 'https://www.memoparis.com/img/african_leather_1.jpg',
    'volume': '75ml',
    'stock': 0,
    'status': 'active',
}


# ──────────────────────────────────────────────────────────
# PorterVendor 테스트
# ──────────────────────────────────────────────────────────

class TestPorterNormalizeRow:
    def setup_method(self):
        self.vendor = PorterVendor()

    def test_required_fields_present(self):
        result = self.vendor.normalize_row(PORTER_RAW)
        for field in CATALOG_FIELDS:
            assert field in result, f"필드 누락: {field}"

    def test_title_ja_mapped(self):
        result = self.vendor.normalize_row(PORTER_RAW)
        assert result['title_ja'] == 'タンカー 2WAYブリーフケース'

    def test_title_ko_en_empty(self):
        result = self.vendor.normalize_row(PORTER_RAW)
        assert result['title_ko'] == ''
        assert result['title_en'] == ''

    def test_vendor_fields(self):
        result = self.vendor.normalize_row(PORTER_RAW)
        assert result['vendor'] == 'PORTER'
        assert result['buy_currency'] == 'JPY'
        assert result['source_country'] == 'JP'
        assert result['forwarder'] == 'zenmarket'

    def test_src_url(self):
        result = self.vendor.normalize_row(PORTER_RAW)
        assert result['src_url'] == PORTER_RAW['src_url']

    def test_images_as_comma_string(self):
        result = self.vendor.normalize_row(PORTER_RAW)
        assert isinstance(result['images'], str)
        assert ',' in result['images']

    def test_stock_default_zero(self):
        row = {**PORTER_RAW}
        row.pop('stock', None)
        result = self.vendor.normalize_row(row)
        assert result['stock'] == 0

    def test_category_and_brand(self):
        result = self.vendor.normalize_row(PORTER_RAW)
        assert result['category'] == 'bag'
        assert result['brand'] == 'PORTER'
        assert result['customs_category'] == 'bag'


class TestPorterGenerateSku:
    def setup_method(self):
        self.vendor = PorterVendor()

    def test_tanker_sku(self):
        sku = self.vendor.generate_sku(PORTER_RAW)
        assert sku.startswith('PTR-TNK-')

    def test_sku_format(self):
        sku = self.vendor.generate_sku(PORTER_RAW)
        parts = sku.split('-')
        assert len(parts) == 3
        assert parts[0] == 'PTR'

    def test_heat_sku(self):
        row = {**PORTER_RAW, 'category_ja': 'ヒート'}
        sku = self.vendor.generate_sku(row)
        assert sku.startswith('PTR-HET-')

    def test_luggage_label_sku(self):
        row = {**PORTER_RAW, 'category_ja': 'ラゲッジレーベル'}
        sku = self.vendor.generate_sku(row)
        assert sku.startswith('PTR-LGL-')

    def test_unknown_category_uses_etc(self):
        row = {**PORTER_RAW, 'category_ja': '未知のシリーズ'}
        sku = self.vendor.generate_sku(row)
        assert sku.startswith('PTR-ETC-')

    def test_product_number_from_url(self):
        # PORTER_RAW의 URL에서 '100000'이 추출되어 SKU에 포함되어야 함
        sku = self.vendor.generate_sku(PORTER_RAW)
        assert '100000' in sku


class TestPorterExtractImages:
    def setup_method(self):
        self.vendor = PorterVendor()

    def test_extracts_images_from_comma_string(self):
        images = self.vendor.extract_images(PORTER_RAW)
        assert isinstance(images, list)
        assert len(images) == 2

    def test_max_5_images(self):
        row = {**PORTER_RAW, 'images': ','.join([f'https://example.com/img{i}.jpg' for i in range(10)])}
        images = self.vendor.extract_images(row)
        assert len(images) <= 5

    def test_single_image_field(self):
        row = {'image_url': 'https://www.yoshidakaban.com/img/100000_main.jpg'}
        images = self.vendor.extract_images(row)
        assert len(images) == 1
        assert images[0].startswith('https://www.yoshidakaban.com/')

    def test_empty_images(self):
        row = {}
        images = self.vendor.extract_images(row)
        assert images == []

    def test_thumbnail_url_upgraded(self):
        row = {'image_url': 'https://www.yoshidakaban.com/img/100000_thumb.jpg'}
        images = self.vendor.extract_images(row)
        assert '_main.jpg' in images[0]


class TestPorterPriceCleaning:
    def test_yen_with_comma(self):
        assert porter_clean_price('¥30,800') == 30800.0

    def test_yen_no_comma(self):
        assert porter_clean_price('¥5000') == 5000.0

    def test_plain_number(self):
        assert porter_clean_price('12000') == 12000.0

    def test_none_returns_zero(self):
        assert porter_clean_price(None) == 0.0

    def test_empty_string_returns_zero(self):
        assert porter_clean_price('') == 0.0

    def test_price_in_normalize_row(self):
        vendor = PorterVendor()
        result = vendor.normalize_row(PORTER_RAW)
        assert result['buy_price'] == 30800.0


# ──────────────────────────────────────────────────────────
# MemoPariVendor 테스트
# ──────────────────────────────────────────────────────────

class TestMemoNormalizeRow:
    def setup_method(self):
        self.vendor = MemoPariVendor()

    def test_required_fields_present(self):
        result = self.vendor.normalize_row(MEMO_RAW)
        for field in CATALOG_FIELDS:
            assert field in result, f"필드 누락: {field}"

    def test_title_en_fr_mapped(self):
        result = self.vendor.normalize_row(MEMO_RAW)
        assert 'African Leather' in result['title_en']
        assert 'African Leather' in result['title_fr']

    def test_title_ko_empty(self):
        result = self.vendor.normalize_row(MEMO_RAW)
        assert result['title_ko'] == ''

    def test_vendor_fields(self):
        result = self.vendor.normalize_row(MEMO_RAW)
        assert result['vendor'] == 'MEMO_PARIS'
        assert result['buy_currency'] == 'EUR'
        assert result['source_country'] == 'FR'
        assert result['forwarder'] == ''

    def test_volume_in_tags(self):
        result = self.vendor.normalize_row(MEMO_RAW)
        assert '75ml' in result['tags']

    def test_category_and_brand(self):
        result = self.vendor.normalize_row(MEMO_RAW)
        assert result['category'] == 'perfume'
        assert result['brand'] == 'MEMO_PARIS'
        assert result['customs_category'] == 'perfume'


class TestMemoGenerateSku:
    def setup_method(self):
        self.vendor = MemoPariVendor()

    def test_edp_sku(self):
        sku = self.vendor.generate_sku(MEMO_RAW)
        assert sku.startswith('MMP-EDP-')

    def test_edt_sku(self):
        row = {**MEMO_RAW, 'fragrance_type': 'Eau de Toilette'}
        sku = self.vendor.generate_sku(row)
        assert sku.startswith('MMP-EDT-')

    def test_unknown_type_uses_etc(self):
        row = {**MEMO_RAW, 'fragrance_type': ''}
        row.pop('title_en', None)
        row.pop('title_fr', None)
        sku = self.vendor.generate_sku(row)
        assert sku.startswith('MMP-ETC-')

    def test_sku_format(self):
        sku = self.vendor.generate_sku(MEMO_RAW)
        parts = sku.split('-')
        assert len(parts) == 3
        assert parts[0] == 'MMP'


class TestMemoPriceCleaning:
    def test_euro_with_decimal(self):
        assert memo_clean_price('€250.00') == 250.0

    def test_euro_no_decimal(self):
        assert memo_clean_price('€180') == 180.0

    def test_plain_number(self):
        assert memo_clean_price('320') == 320.0

    def test_none_returns_zero(self):
        assert memo_clean_price(None) == 0.0

    def test_empty_string_returns_zero(self):
        assert memo_clean_price('') == 0.0

    def test_price_in_normalize_row(self):
        vendor = MemoPariVendor()
        result = vendor.normalize_row(MEMO_RAW)
        assert result['buy_price'] == 250.0


# ──────────────────────────────────────────────────────────
# 벤더 레지스트리 테스트
# ──────────────────────────────────────────────────────────

class TestVendorRegistry:
    def test_get_vendor_porter(self):
        vendor = get_vendor('porter')
        assert isinstance(vendor, PorterVendor)

    def test_get_vendor_memo_paris(self):
        vendor = get_vendor('memo_paris')
        assert isinstance(vendor, MemoPariVendor)

    def test_get_vendor_case_insensitive(self):
        vendor = get_vendor('PORTER')
        assert isinstance(vendor, PorterVendor)

    def test_vendor_registry_keys(self):
        assert 'porter' in VENDOR_REGISTRY
        assert 'memo_paris' in VENDOR_REGISTRY

    def test_unknown_vendor_raises(self):
        with pytest.raises(ValueError, match="Unknown vendor"):
            get_vendor('nonexistent_vendor')


# ──────────────────────────────────────────────────────────
# normalize_batch 테스트
# ──────────────────────────────────────────────────────────

class TestNormalizeBatch:
    def setup_method(self):
        self.porter = PorterVendor()
        self.memo = MemoPariVendor()

    def test_porter_batch(self):
        rows = [PORTER_RAW, {**PORTER_RAW, 'title_ja': '別の商品'}]
        results = self.porter.normalize_batch(rows)
        assert len(results) == 2
        for r in results:
            assert r['vendor'] == 'PORTER'

    def test_memo_batch(self):
        rows = [MEMO_RAW, {**MEMO_RAW, 'title_en': 'Another Perfume'}]
        results = self.memo.normalize_batch(rows)
        assert len(results) == 2
        for r in results:
            assert r['vendor'] == 'MEMO_PARIS'

    def test_empty_batch(self):
        assert self.porter.normalize_batch([]) == []

    def test_to_catalog_row_has_all_fields(self):
        result = self.porter.to_catalog_row(PORTER_RAW)
        assert list(result.keys()) == CATALOG_FIELDS

    def test_to_catalog_row_missing_fields_default_empty(self):
        # 최소 필드만 있는 행에서 누락된 CATALOG_FIELDS는 '' 이어야 함
        result = self.memo.to_catalog_row({'title_en': 'Test'})
        assert result['title_ko'] == ''
        assert result['title_ja'] == ''


# ──────────────────────────────────────────────────────────
# 알 수 없는 벤더 에러 처리 테스트
# ──────────────────────────────────────────────────────────

class TestUnknownVendor:
    def test_raises_value_error(self):
        with pytest.raises(ValueError):
            get_vendor('unknown_brand')

    def test_error_message_includes_name(self):
        try:
            get_vendor('mystery_shop')
        except ValueError as e:
            assert 'mystery_shop' in str(e)
