"""
Shopify 글로벌 채널 — 기존 vendors/shopify_client.py 래핑

BaseChannel 인터페이스를 구현하며 Shopify REST API를 직접 호출한다.
"""

import logging

from .base_channel import BaseChannel

logger = logging.getLogger(__name__)

# 카테고리 태그 매핑
_CATEGORY_TAGS = {
    'bag': 'bag,accessories',
    'wallet': 'wallet,accessories',
    'perfume': 'perfume,beauty,fragrance',
    'pouch': 'pouch,accessories',
}


class ShopifyGlobalChannel(BaseChannel):
    """Shopify 글로벌 판매 채널."""

    channel_name = 'shopify'
    target_currency = 'USD'

    def prepare_product(self, catalog_row: dict, sell_price: float) -> dict:
        """카탈로그 행 → Shopify product JSON 형식으로 변환.

        Args:
            catalog_row: CATALOG_FIELDS 형식의 카탈로그 행
            sell_price: USD 판매가

        Returns:
            Shopify REST API product dict
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
                    'value': catalog_row.get('buy_currency', ''),
                    'type': 'single_line_text_field',
                    'namespace': 'proxy_commerce',
                },
            ],
        }
        return product

    def export_batch(self, products: list, output_path: str) -> str:
        """Shopify API를 통해 상품 일괄 등록/갱신.

        Args:
            products: prepare_product()로 변환된 상품 dict 리스트
            output_path: 미사용 (API 방식이므로 파일 저장 불필요)

        Returns:
            빈 문자열 (API 호출 결과는 로그로 출력)
        """
        from src.vendors.shopify_client import upsert_product

        success = 0
        errors = []
        for prod in products:
            try:
                upsert_product(prod)
                success += 1
            except Exception as exc:
                sku = prod.get('variants', [{}])[0].get('sku', '?')
                logger.error('Shopify 업로드 실패 SKU=%s: %s', sku, exc)
                errors.append(str(exc))

        logger.info('Shopify 동기화 완료: 성공=%d, 실패=%d', success, len(errors))
        return ''

    def get_category_mapping(self, catalog_category: str) -> str:
        """카탈로그 카테고리 → Shopify product_type 매핑."""
        return catalog_category
