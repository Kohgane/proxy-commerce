"""
src/channels/ 단위 테스트

PercentyExporter, ShopifyGlobalChannel, WooDomesticChannel,
채널 레지스트리 및 CLI dry-run 동작을 검증한다.
"""

import csv
import os
import sys
import tempfile

import pytest

# 패키지 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.channels import get_channel, CHANNEL_REGISTRY  # noqa: E402
from src.channels.percenty import (  # noqa: E402
    PercentyExporter,
    COUPANG_CATEGORIES,
    NAVER_CATEGORIES,
    MARKET_PRICE_POLICY,
)
from src.channels.shopify_global import ShopifyGlobalChannel  # noqa: E402
from src.channels.woo_domestic import WooDomesticChannel  # noqa: E402


# ──────────────────────────────────────────────────────────
# 공통 픽스처
# ──────────────────────────────────────────────────────────

PORTER_CATALOG = {
    'sku': 'PTR-TNK-100000',
    'title_ko': '탱커 2WAY 브리프케이스',
    'title_en': 'Tanker 2WAY Briefcase',
    'title_ja': 'タンカー 2WAYブリーフケース',
    'title_fr': '',
    'src_url': 'https://www.yoshidakaban.com/product/100000.html',
    'buy_currency': 'JPY',
    'buy_price': 30800.0,
    'source_country': 'JP',
    'images': 'https://example.com/img1.jpg,https://example.com/img2.jpg',
    'stock': 5,
    'tags': 'porter,tanker,bag',
    'vendor': 'PORTER',
    'status': 'active',
    'category': 'bag',
    'brand': 'PORTER',
    'forwarder': 'zenmarket',
    'customs_category': 'bag',
}

MEMO_CATALOG = {
    'sku': 'MMP-EDP-AFRICA',
    'title_ko': '아프리카 레더 오드퍼퓸',
    'title_en': 'African Leather Eau de Parfum',
    'title_ja': '',
    'title_fr': 'African Leather Eau de Parfum',
    'src_url': 'https://www.memoparis.com/products/african-leather',
    'buy_currency': 'EUR',
    'buy_price': 250.0,
    'source_country': 'FR',
    'images': 'https://example.com/memo1.jpg',
    'stock': 3,
    'tags': '75ml,perfume,memo_paris',
    'vendor': 'MEMO_PARIS',
    'status': 'active',
    'category': 'perfume',
    'brand': 'MEMO_PARIS',
    'forwarder': '',
    'customs_category': 'perfume',
    'fragrance_type': 'Eau de Parfum',
}

SELL_PRICE_KRW = 450000.0
SELL_PRICE_USD = 250.0


# ──────────────────────────────────────────────────────────
# PercentyExporter: prepare_product 테스트
# ──────────────────────────────────────────────────────────

class TestPercentyPrepareProduct:
    def setup_method(self):
        self.exporter = PercentyExporter()

    def test_porter_required_fields_present(self):
        result = self.exporter.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)
        for field in ['상품명', '판매가', '카테고리', '대표이미지URL', '바코드/SKU', '원산지', '브랜드']:
            assert field in result, f"필드 누락: {field}"

    def test_porter_sell_price(self):
        result = self.exporter.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)
        assert result['판매가'] == int(SELL_PRICE_KRW)

    def test_porter_origin_japan(self):
        result = self.exporter.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)
        assert result['원산지'] == '일본'

    def test_porter_delivery_method(self):
        result = self.exporter.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)
        assert result['배송방법'] == '해외배송'

    def test_porter_images_split(self):
        result = self.exporter.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)
        assert result['대표이미지URL'] == 'https://example.com/img1.jpg'
        assert 'https://example.com/img2.jpg' in result['추가이미지URL']

    def test_porter_sku_mapped(self):
        result = self.exporter.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)
        assert result['바코드/SKU'] == 'PTR-TNK-100000'

    def test_memo_prepare_product(self):
        result = self.exporter.prepare_product(MEMO_CATALOG, SELL_PRICE_KRW)
        assert result['원산지'] == '프랑스'
        assert result['상품명'] == MEMO_CATALOG['title_ko']
        assert result['판매가'] == int(SELL_PRICE_KRW)


# ──────────────────────────────────────────────────────────
# PercentyExporter: export_batch CSV 생성 테스트
# ──────────────────────────────────────────────────────────

class TestPercentyExportBatch:
    def setup_method(self):
        self.exporter = PercentyExporter()

    def test_csv_file_created(self):
        products = [self.exporter.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, 'test.csv')
            result_path = self.exporter.export_batch(products, out_path)
            assert os.path.exists(result_path)

    def test_csv_utf8_bom(self):
        """CSV 파일이 UTF-8 with BOM으로 저장되어야 한다."""
        products = [self.exporter.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, 'test.csv')
            self.exporter.export_batch(products, out_path)
            with open(out_path, 'rb') as f:
                bom = f.read(3)
            # UTF-8 BOM: EF BB BF
            assert bom == b'\xef\xbb\xbf', 'UTF-8 BOM이 없음'

    def test_csv_header_row(self):
        products = [self.exporter.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, 'test.csv')
            self.exporter.export_batch(products, out_path)
            with open(out_path, encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                assert '상품명' in reader.fieldnames
                assert '판매가' in reader.fieldnames

    def test_csv_data_row(self):
        products = [self.exporter.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, 'test.csv')
            self.exporter.export_batch(products, out_path)
            with open(out_path, encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            assert len(rows) == 1
            assert rows[0]['바코드/SKU'] == 'PTR-TNK-100000'

    def test_returns_absolute_path(self):
        products = [self.exporter.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, 'test.csv')
            result = self.exporter.export_batch(products, out_path)
            assert os.path.isabs(result)


# ──────────────────────────────────────────────────────────
# PercentyExporter: export_for_market 테스트
# ──────────────────────────────────────────────────────────

class TestPercentyExportForMarket:
    def setup_method(self):
        self.exporter = PercentyExporter()
        self.products = [
            self.exporter.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW),
            self.exporter.prepare_product(MEMO_CATALOG, SELL_PRICE_KRW),
        ]

    def test_coupang_csv_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'coupang.csv')
            path = self.exporter.export_for_market(self.products, 'coupang', out)
            assert os.path.exists(path)

    def test_coupang_price_adjusted(self):
        """쿠팡 마진 조정이 적용된 가격이어야 한다 (환경변수 없으면 -2%)."""
        os.environ.pop('COUPANG_MARGIN_ADJUST', None)
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'coupang.csv')
            self.exporter.export_for_market(self.products, 'coupang', out)
            with open(out, encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            original_price = int(SELL_PRICE_KRW)
            adjusted = int(rows[0]['판매가'])
            # -2% 조정 → 원래 가격보다 낮아야 함
            assert adjusted < original_price

    def test_smartstore_csv_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'smartstore.csv')
            path = self.exporter.export_for_market(self.products, 'smartstore', out)
            assert os.path.exists(path)

    def test_smartstore_category_code(self):
        """스마트스토어는 NAVER_CATEGORIES 숫자 코드를 사용해야 한다."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out = os.path.join(tmpdir, 'smartstore.csv')
            self.exporter.export_for_market(self.products, 'smartstore', out)
            with open(out, encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            # 가방 상품의 카테고리는 NAVER_CATEGORIES['bag'] 이어야 함
            assert rows[0]['카테고리'] == NAVER_CATEGORIES['bag']


# ──────────────────────────────────────────────────────────
# PercentyExporter: 카테고리 매핑 테스트
# ──────────────────────────────────────────────────────────

class TestPercentyCategoryMapping:
    def setup_method(self):
        self.exporter = PercentyExporter()

    def test_bag_category(self):
        result = self.exporter.get_category_mapping('bag')
        assert result == COUPANG_CATEGORIES['bag']

    def test_perfume_category(self):
        result = self.exporter.get_category_mapping('perfume')
        assert result == COUPANG_CATEGORIES['perfume']

    def test_wallet_category(self):
        result = self.exporter.get_category_mapping('wallet')
        assert result == COUPANG_CATEGORIES['wallet']

    def test_unknown_category_passthrough(self):
        result = self.exporter.get_category_mapping('unknown_cat')
        assert result == 'unknown_cat'


# ──────────────────────────────────────────────────────────
# PercentyExporter: 가격 정책 테스트
# ──────────────────────────────────────────────────────────

class TestPercentyPricePolicy:
    def test_coupang_policy_exists(self):
        assert 'coupang' in MARKET_PRICE_POLICY
        assert MARKET_PRICE_POLICY['coupang']['margin_adjust'] == -2.0
        assert MARKET_PRICE_POLICY['coupang']['commission_rate'] == 10.8

    def test_smartstore_policy_exists(self):
        assert 'smartstore' in MARKET_PRICE_POLICY
        assert MARKET_PRICE_POLICY['smartstore']['margin_adjust'] == 0.0
        assert MARKET_PRICE_POLICY['smartstore']['commission_rate'] == 5.0

    def test_11st_policy_exists(self):
        assert '11st' in MARKET_PRICE_POLICY
        assert MARKET_PRICE_POLICY['11st']['commission_rate'] == 12.0


# ──────────────────────────────────────────────────────────
# PercentyExporter: HTML 상세설명 테스트
# ──────────────────────────────────────────────────────────

class TestPercentyDescriptionHtml:
    def setup_method(self):
        self.exporter = PercentyExporter()

    def test_porter_html_contains_brand(self):
        html = self.exporter.generate_description_html(PORTER_CATALOG)
        assert 'PORTER' in html

    def test_porter_html_contains_title(self):
        html = self.exporter.generate_description_html(PORTER_CATALOG)
        assert PORTER_CATALOG['title_ko'] in html

    def test_porter_html_contains_shipping_info(self):
        html = self.exporter.generate_description_html(PORTER_CATALOG)
        assert '배송 안내' in html

    def test_memo_html_contains_volume(self):
        html = self.exporter.generate_description_html(MEMO_CATALOG)
        assert '75ml' in html

    def test_memo_html_contains_return_info(self):
        html = self.exporter.generate_description_html(MEMO_CATALOG)
        assert '반품' in html

    def test_memo_html_contains_fragrance_type(self):
        html = self.exporter.generate_description_html(MEMO_CATALOG)
        assert 'Eau de Parfum' in html


# ──────────────────────────────────────────────────────────
# ShopifyGlobalChannel: prepare_product 테스트
# ──────────────────────────────────────────────────────────

class TestShopifyPrepareProduct:
    def setup_method(self):
        self.channel = ShopifyGlobalChannel()

    def test_basic_fields(self):
        result = self.channel.prepare_product(PORTER_CATALOG, SELL_PRICE_USD)
        assert result['title'] == PORTER_CATALOG['title_en']
        assert result['vendor'] == PORTER_CATALOG['brand']

    def test_variant_price(self):
        result = self.channel.prepare_product(PORTER_CATALOG, SELL_PRICE_USD)
        assert result['variants'][0]['price'] == str(round(SELL_PRICE_USD, 2))

    def test_variant_sku(self):
        result = self.channel.prepare_product(PORTER_CATALOG, SELL_PRICE_USD)
        assert result['variants'][0]['sku'] == PORTER_CATALOG['sku']

    def test_metafields_source_country(self):
        result = self.channel.prepare_product(PORTER_CATALOG, SELL_PRICE_USD)
        meta_keys = {m['key']: m['value'] for m in result['metafields']}
        assert meta_keys['source_country'] == 'JP'

    def test_metafields_original_price(self):
        result = self.channel.prepare_product(PORTER_CATALOG, SELL_PRICE_USD)
        meta_keys = {m['key']: m['value'] for m in result['metafields']}
        assert meta_keys['original_price'] == str(PORTER_CATALOG['buy_price'])

    def test_images_mapped(self):
        result = self.channel.prepare_product(PORTER_CATALOG, SELL_PRICE_USD)
        assert len(result['images']) == 2
        assert result['images'][0]['src'] == 'https://example.com/img1.jpg'

    def test_channel_name(self):
        assert self.channel.channel_name == 'shopify'
        assert self.channel.target_currency == 'USD'


# ──────────────────────────────────────────────────────────
# WooDomesticChannel: prepare_product 테스트
# ──────────────────────────────────────────────────────────

class TestWooPrepareProduct:
    def setup_method(self):
        self.channel = WooDomesticChannel()

    def test_basic_fields(self):
        result = self.channel.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)
        assert result['name'] == PORTER_CATALOG['title_ko']
        assert result['sku'] == PORTER_CATALOG['sku']

    def test_regular_price_krw(self):
        result = self.channel.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)
        assert result['regular_price'] == str(int(SELL_PRICE_KRW))

    def test_categories_id_mapped(self):
        """카테고리가 API로 조회되면 ID로 매핑된다 (API 사용 가능 시)."""
        from unittest.mock import patch as mock_patch
        import src.vendors.woocommerce_client as woo_mod
        with mock_patch.object(woo_mod, 'get_or_create_category', return_value=7):
            with mock_patch.object(woo_mod, 'get_or_create_tag', return_value=1):
                result = self.channel.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)
        assert result['categories'] == [{'id': 7}]

    def test_meta_source_country(self):
        result = self.channel.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)
        meta = {m['key']: m['value'] for m in result['meta_data']}
        assert meta['source_country'] == 'JP'

    def test_meta_vendor(self):
        """meta_data에 vendor 키가 포함된다."""
        result = self.channel.prepare_product(PORTER_CATALOG, SELL_PRICE_KRW)
        meta = {m['key']: m['value'] for m in result['meta_data']}
        assert meta['vendor'] == 'PORTER'

    def test_channel_name(self):
        assert self.channel.channel_name == 'woocommerce'
        assert self.channel.target_currency == 'KRW'


# ──────────────────────────────────────────────────────────
# 채널 레지스트리 테스트
# ──────────────────────────────────────────────────────────

class TestChannelRegistry:
    def test_get_channel_percenty(self):
        channel = get_channel('percenty')
        assert isinstance(channel, PercentyExporter)

    def test_get_channel_shopify(self):
        channel = get_channel('shopify')
        assert isinstance(channel, ShopifyGlobalChannel)

    def test_get_channel_woocommerce(self):
        channel = get_channel('woocommerce')
        assert isinstance(channel, WooDomesticChannel)

    def test_get_channel_case_insensitive(self):
        channel = get_channel('PERCENTY')
        assert isinstance(channel, PercentyExporter)

    def test_registry_keys(self):
        assert 'percenty' in CHANNEL_REGISTRY
        assert 'shopify' in CHANNEL_REGISTRY
        assert 'woocommerce' in CHANNEL_REGISTRY


# ──────────────────────────────────────────────────────────
# 알 수 없는 채널 에러 처리 테스트
# ──────────────────────────────────────────────────────────

class TestUnknownChannel:
    def test_raises_value_error(self):
        with pytest.raises(ValueError, match='Unknown channel'):
            get_channel('nonexistent_channel')

    def test_error_message_includes_name(self):
        with pytest.raises(ValueError) as exc_info:
            get_channel('mystery_channel')
        assert 'mystery_channel' in str(exc_info.value)


# ──────────────────────────────────────────────────────────
# CLI dry-run 테스트
# ──────────────────────────────────────────────────────────

class TestCliDryRun:
    def test_dry_run_percenty_no_sheet_required(self, capsys):
        """--dry-run 모드에서 _run_percenty()를 직접 호출하면 출력에 DRY-RUN이 포함되어야 한다."""
        from unittest.mock import patch, MagicMock

        from src.channels import cli as channels_cli

        mock_catalog = [
            {**PORTER_CATALOG},
            {**MEMO_CATALOG},
        ]

        with patch.object(channels_cli, '_load_catalog', return_value=mock_catalog):
            with tempfile.TemporaryDirectory() as tmpdir:
                # dry_run=True 직접 호출
                args = MagicMock()
                args.output = tmpdir
                args.market = 'all'
                channels_cli._run_percenty(args, mock_catalog, dry_run=True)

        captured = capsys.readouterr()
        assert 'DRY-RUN' in captured.out
        assert '2' in captured.out  # 2개 상품

    def test_dry_run_exits_one_without_sheet_id(self):
        """main()은 --sheet-id 또는 GOOGLE_SHEET_ID 환경변수가 없으면 sys.exit(1)을 발생시켜야 한다."""
        from src.channels import cli as channels_cli

        with pytest.raises(SystemExit) as exc_info:
            os.environ.pop('GOOGLE_SHEET_ID', None)
            channels_cli.main(['--channel', 'percenty', '--dry-run'])
        assert exc_info.value.code == 1
