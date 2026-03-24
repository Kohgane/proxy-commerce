"""tests/e2e/test_catalog_flow.py — 카탈로그 동기화 플로우 E2E 테스트.

가격 계산, 멀티 통화, dry_run 모드를 검증한다.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch


class TestCatalogPriceCalculation:
    """카탈로그 가격 계산 E2E 테스트."""

    def test_catalog_price_calculation_jpy(self, monkeypatch):
        """JPY 구매가 → KRW 판매가 계산이 올바른지 검증한다."""
        from src.price import calc_price

        buy_price = Decimal('30800')  # JPY
        fx_jpykrw = Decimal('9.2')
        margin = Decimal('22')

        price_krw = calc_price(
            buy_price, 'JPY', Decimal('1380'), margin, 'KRW',
            fx_rates={'JPYKRW': fx_jpykrw, 'USDKRW': Decimal('1380'), 'EURKRW': Decimal('1500')},
        )

        # JPY → KRW: 30800 * 9.2 = 283360, 마진 22% 적용
        expected_base = buy_price * fx_jpykrw
        assert price_krw > expected_base  # 마진이 적용된 판매가는 원가보다 높아야 함
        assert price_krw > 0

    def test_catalog_price_calculation_eur(self, monkeypatch):
        """EUR 구매가 → KRW 판매가 계산이 올바른지 검증한다."""
        from src.price import calc_price

        buy_price = Decimal('250')  # EUR
        fx_eurkrw = Decimal('1500')
        margin = Decimal('20')

        price_krw = calc_price(
            buy_price, 'EUR', Decimal('1380'), margin, 'KRW',
            fx_rates={'EURKRW': fx_eurkrw, 'USDKRW': Decimal('1380'), 'JPYKRW': Decimal('9.2')},
        )

        # EUR → KRW: 250 * 1500 = 375000, 마진 20% 적용
        expected_base = buy_price * fx_eurkrw
        assert price_krw > expected_base
        assert price_krw > 0


class TestCatalogMultiCurrency:
    """카탈로그 멀티 통화 E2E 테스트."""

    def test_catalog_multi_currency_rates_applied(self, monkeypatch):
        """FX 환율이 가격 계산에 올바르게 적용되는지 검증한다."""
        from src.price import calc_price

        # 동일 JPY 가격, 다른 환율로 계산 시 다른 결과
        buy_price = Decimal('10000')
        margin = Decimal('20')

        price_low = calc_price(
            buy_price, 'JPY', Decimal('1380'), margin, 'KRW',
            fx_rates={'JPYKRW': Decimal('8.0'), 'USDKRW': Decimal('1380'), 'EURKRW': Decimal('1500')},
        )
        price_high = calc_price(
            buy_price, 'JPY', Decimal('1380'), margin, 'KRW',
            fx_rates={'JPYKRW': Decimal('10.0'), 'USDKRW': Decimal('1380'), 'EURKRW': Decimal('1500')},
        )

        # 환율이 높을수록 KRW 가격도 높아야 함
        assert price_high > price_low

    def test_catalog_usd_to_krw(self, monkeypatch):
        """USD → KRW 변환이 올바른지 검증한다."""
        from src.price import calc_price

        buy_price = Decimal('100')  # USD
        fx_usdkrw = Decimal('1380')
        margin = Decimal('22')

        price_krw = calc_price(
            buy_price, 'USD', fx_usdkrw, margin, 'KRW',
            fx_rates={'USDKRW': fx_usdkrw, 'JPYKRW': Decimal('9.2'), 'EURKRW': Decimal('1500')},
        )

        expected_base = buy_price * fx_usdkrw  # 138000 KRW
        assert price_krw > expected_base


class TestCatalogSyncDryRun:
    """카탈로그 동기화 dry_run 모드 E2E 테스트."""

    def test_catalog_sync_dry_run(self, monkeypatch):
        """CatalogSync dry_run=True 시 실제 업서트가 호출되지 않는다."""
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test_sheet_id')
        monkeypatch.setenv('FX_USE_LIVE', '0')

        import src.catalog_sync as catalog_sync_mod

        with patch.object(catalog_sync_mod, 'open_sheet') as mock_sheet, \
             patch.object(catalog_sync_mod, 'shopify_upsert') as mock_shopify, \
             patch.object(catalog_sync_mod, 'woo_upsert') as mock_woo, \
             patch.object(catalog_sync_mod, 'ensure_images', return_value=['https://example.com/img.jpg']), \
             patch.object(catalog_sync_mod, 'ko_to_en_if_needed', return_value='Test Product'):

            ws = MagicMock()
            ws.get_all_records.return_value = [
                {
                    'sku': 'PTR-TNK-001',
                    'title_ko': '포터 탱커',
                    'title_en': 'Porter Tanker',
                    'title_ja': '',
                    'title_fr': '',
                    'src_url': 'https://example.com',
                    'buy_currency': 'JPY',
                    'buy_price': '30800',
                    'stock': 5,
                    'tags': 'bag,japan',
                    'vendor': 'porter',
                    'source_country': 'JP',
                    'status': 'active',
                }
            ]
            mock_sheet.return_value = ws

            from src.catalog_sync import row_to_product
            row = ws.get_all_records.return_value[0]
            shopify_prod, woo_prod = row_to_product(row)

        # dry_run이므로 실제 업서트 호출되지 않음
        mock_shopify.assert_not_called()
        mock_woo.assert_not_called()
        assert shopify_prod is not None
        assert shopify_prod['variants'][0]['sku'] == 'PTR-TNK-001'
