"""Shopify Markets 다통화 채널.

Phase 6-1의 src/shipping/ 엔진을 활용해 국가별 세금 포함가를 자동 계산하고,
Shopify Markets API 호환 형식으로 상품 데이터를 준비한다.
"""
import json
import logging
import os
from decimal import Decimal

from .base_channel import BaseChannel
from ..shipping import TaxCalculator, ShippingEstimator, get_country
from ..fx.multi_currency import MultiCurrencyConverter

logger = logging.getLogger(__name__)

# 카테고리 태그 매핑 (shopify_global.py와 동일)
_CATEGORY_TAGS = {
    'bag': 'bag,accessories',
    'wallet': 'wallet,accessories',
    'perfume': 'perfume,beauty,fragrance',
    'pouch': 'pouch,accessories',
}

# Tier 1 기본 대상 국가
_DEFAULT_COUNTRIES = ['US', 'GB']


class ShopifyMarketsChannel(BaseChannel):
    """Shopify Markets 다통화 판매 채널."""

    channel_name = 'shopify_markets'

    def __init__(self, target_countries: list = None, fx_rates: dict = None):
        """
        Args:
            target_countries: 대상 국가 ISO 코드 리스트. None이면 Tier 1 국가만.
            fx_rates: 환율 딕셔너리. None이면 기본값(DEFAULT_MULTI_FX_RATES) 사용.
        """
        self.tax_calc = TaxCalculator()
        self.shipping_est = ShippingEstimator()
        self.fx_converter = MultiCurrencyConverter(fx_rates)
        self.target_countries = target_countries or list(_DEFAULT_COUNTRIES)

    # ── BaseChannel 추상 메서드 구현 ─────────────────────────────────────────

    def prepare_product(self, catalog_row: dict, sell_price: float) -> dict:
        """카탈로그 행 → Shopify Markets 다통화 product dict.

        기존 shopify_global.py의 prepare_product()를 확장해서:
        1. 기본 USD 가격 설정
        2. 각 대상 국가별 현지통화 가격 계산 (세금 포함/미포함)
        3. country_prices 필드에 국가별 가격 메타데이터 추가

        Args:
            catalog_row: CATALOG_FIELDS 형식의 카탈로그 행
            sell_price: 기본 USD 판매가 (float)

        Returns:
            Shopify Markets 호환 product dict
        """
        title = (
            catalog_row.get('title_en')
            or catalog_row.get('title_ko')
            or catalog_row.get('title_ja')
            or ''
        )
        sku = catalog_row.get('sku', '')
        category = catalog_row.get('category', '')
        brand = catalog_row.get('brand', '')
        source_country = catalog_row.get('source_country', '')

        tags_list = [brand, category] + _CATEGORY_TAGS.get(category, '').split(',')
        tags = ','.join(t for t in tags_list if t)

        # 이미지 파싱
        images_raw = catalog_row.get('images', '') or ''
        if isinstance(images_raw, list):
            image_list = [u.strip() for u in images_raw if u.strip()]
        else:
            image_list = [u.strip() for u in images_raw.split(',') if u.strip()]
        images = [{'src': url} for url in image_list]

        # 국가별 다통화 가격 계산
        buy_price = catalog_row.get('buy_price', 0)
        buy_currency = catalog_row.get('buy_currency', 'USD')
        try:
            margin_pct = Decimal(str(os.getenv('TARGET_MARGIN_PCT', '22')))
        except Exception:
            margin_pct = Decimal('22')

        country_prices = self.calc_country_prices(
            buy_price=Decimal(str(buy_price)) if buy_price else Decimal('0'),
            buy_currency=str(buy_currency),
            margin_pct=margin_pct,
        )

        product = {
            'title': title,
            'body_html': f'<p>{title}</p>',
            'vendor': brand,
            'product_type': category,
            'tags': tags,
            'status': catalog_row.get('status', 'active'),
            'variants': [
                {
                    'sku': sku,
                    'price': str(round(float(sell_price), 2)),
                    'inventory_quantity': int(catalog_row.get('stock', 0)),
                    'fulfillment_service': 'manual',
                }
            ],
            'images': images,
            'country_prices': country_prices,
            'metafields': [
                {
                    'key': 'source_country',
                    'value': source_country,
                    'type': 'single_line_text_field',
                    'namespace': 'proxy_commerce',
                },
                {
                    'key': 'original_price',
                    'value': str(catalog_row.get('buy_price', '')),
                    'type': 'single_line_text_field',
                    'namespace': 'proxy_commerce',
                },
                {
                    'key': 'original_currency',
                    'value': str(buy_currency),
                    'type': 'single_line_text_field',
                    'namespace': 'proxy_commerce',
                },
                {
                    'key': 'country_prices_json',
                    'value': json.dumps(
                        {k: {**v, 'price': str(v['price'])} for k, v in country_prices.items()},
                        ensure_ascii=False,
                    ),
                    'type': 'multi_line_text_field',
                    'namespace': 'proxy_commerce',
                },
            ],
        }
        return product

    def export_batch(self, products: list, output_path: str) -> str:
        """Shopify Markets API 호출 또는 JSON 파일 생성.

        Args:
            products: prepare_product()로 변환된 상품 dict 리스트
            output_path: 출력 파일 경로. 빈 문자열이면 API 호출 시도.

        Returns:
            저장된 파일 경로 또는 빈 문자열 (API 모드)
        """
        if output_path:
            os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
            # Decimal 직렬화를 위해 price를 str로 변환
            serializable = []
            for prod in products:
                prod_copy = dict(prod)
                if 'country_prices' in prod_copy:
                    prod_copy['country_prices'] = {
                        k: {**v, 'price': str(v['price'])}
                        for k, v in prod_copy['country_prices'].items()
                    }
                serializable.append(prod_copy)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            logger.info('Shopify Markets JSON 저장: %s (%d개)', output_path, len(products))
            return output_path

        # API 모드: shopify_global.py와 동일한 방식
        from src.vendors.shopify_client import upsert_product

        success = 0
        errors = []
        for prod in products:
            try:
                upsert_product(prod)
                success += 1
            except Exception as exc:
                sku = prod.get('variants', [{}])[0].get('sku', '?')
                logger.error('Shopify Markets 업로드 실패 SKU=%s: %s', sku, exc)
                errors.append(str(exc))

        logger.info('Shopify Markets 동기화 완료: 성공=%d, 실패=%d', success, len(errors))
        return ''

    def get_category_mapping(self, catalog_category: str) -> str:
        """카탈로그 카테고리 → Shopify product_type 매핑."""
        return catalog_category

    # ── 다통화 가격 계산 ─────────────────────────────────────────────────────

    def calc_country_prices(
        self,
        buy_price: Decimal,
        buy_currency: str,
        margin_pct: Decimal,
        fx_rates: dict = None,
    ) -> dict:
        """모든 대상 국가에 대해 현지통화 판매가 일괄 계산.

        Args:
            buy_price: 구매가 (buy_currency 기준)
            buy_currency: 구매 통화 ISO 코드
            margin_pct: 마진율 (%, 예: 22 = 22%)
            fx_rates: 환율 딕셔너리. None이면 인스턴스 기본값 사용.

        Returns:
            {
                'US': {'price': Decimal('89.99'), 'currency': 'USD',
                       'tax_inclusive': False, 'incoterms': 'DAP'},
                'GB': {'price': Decimal('79.99'), 'currency': 'GBP',
                       'tax_inclusive': True, 'incoterms': 'DDP'},
                ...
            }
        """
        if fx_rates is None:
            fx_rates = self.fx_converter.fx_rates

        result = {}
        for code in self.target_countries:
            try:
                config = get_country(code)
                landed = self.tax_calc.calc_landed_price(
                    country_code=code,
                    buy_price=Decimal(str(buy_price)),
                    buy_currency=str(buy_currency),
                    margin_pct=Decimal(str(margin_pct)),
                    fx_rates=fx_rates,
                )
                # DDP 국가는 세금 포함가 사용, DAP는 세전 판매가 사용
                if config.incoterms == 'DDP':
                    price = landed['sell_price']
                    tax_inclusive = True
                else:
                    # DAP: 세전 가격 (세금은 수입 시 고객 부담)
                    price = landed['sell_price']
                    tax_inclusive = False

                result[code] = {
                    'price': price,
                    'currency': config.currency,
                    'tax_inclusive': tax_inclusive,
                    'incoterms': config.incoterms,
                }
            except Exception as exc:
                logger.warning('국가 %s 가격 계산 실패: %s', code, exc)

        return result

    def get_shipping_options(self, country_code: str, weight_kg: Decimal = Decimal('0.5')) -> list:
        """특정 국가의 배송 옵션 리스트 (cheapest/fastest 포함).

        Args:
            country_code: ISO alpha-2 국가 코드
            weight_kg: 상품 중량 (kg)

        Returns:
            배송 옵션 dict 리스트. 각 항목:
            {
                'method': str,
                'cost_krw': Decimal,
                'delivery_days_min': int,
                'delivery_days_max': int,
                'tracking': bool,
                'is_cheapest': bool,
                'is_fastest': bool,
            }
        """
        estimates = self.shipping_est.estimate(country_code, Decimal(str(weight_kg)))
        cheapest = self.shipping_est.cheapest(country_code, Decimal(str(weight_kg)))
        fastest = self.shipping_est.fastest(country_code, Decimal(str(weight_kg)))

        options = []
        for est in estimates:
            options.append({
                'method': est.method,
                'cost_krw': est.cost_krw,
                'delivery_days_min': est.delivery_days_min,
                'delivery_days_max': est.delivery_days_max,
                'tracking': est.tracking,
                'is_cheapest': est.method == cheapest.method,
                'is_fastest': est.method == fastest.method,
            })
        return options
