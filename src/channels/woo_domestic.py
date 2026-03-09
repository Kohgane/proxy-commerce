"""
WooCommerce 국내몰 채널 — 기존 vendors/woocommerce_client.py 래핑

BaseChannel 인터페이스를 구현하며 WooCommerce REST API를 직접 호출한다.
"""

import logging

from .base_channel import BaseChannel

logger = logging.getLogger(__name__)

# 카테고리 → WooCommerce slug 매핑
_CATEGORY_SLUGS = {
    'bag': '가방',
    'wallet': '지갑',
    'perfume': '향수',
    'pouch': '파우치',
}


class WooDomesticChannel(BaseChannel):
    """WooCommerce 국내 판매 채널."""

    channel_name = 'woocommerce'
    target_currency = 'KRW'

    def prepare_product(self, catalog_row: dict, sell_price: float) -> dict:
        """카탈로그 행 → WooCommerce product JSON 형식으로 변환.

        Args:
            catalog_row: CATALOG_FIELDS 형식의 카탈로그 행
            sell_price: KRW 판매가

        Returns:
            WooCommerce REST API product dict
        """
        title = (
            catalog_row.get('title_ko')
            or catalog_row.get('title_en')
            or ''
        )
        sku = catalog_row.get('sku', '')
        category = catalog_row.get('category', '')
        brand = catalog_row.get('brand', '')
        source_country = catalog_row.get('source_country', '')
        forwarder = catalog_row.get('forwarder', '')

        # 이미지 파싱
        images_raw = catalog_row.get('images', '') or ''
        if isinstance(images_raw, list):
            image_list = [u.strip() for u in images_raw if u.strip()]
        else:
            image_list = [u.strip() for u in images_raw.split(',') if u.strip()]
        images = [{'src': url} for url in image_list]

        categories = [{'name': brand}]
        category_slug = _CATEGORY_SLUGS.get(category)
        if category_slug:
            categories.append({'name': category_slug})

        product = {
            'name': title,
            'sku': sku,
            'regular_price': str(int(sell_price)),
            'status': catalog_row.get('status', 'publish'),
            'description': f'<p>{title}</p>',
            'categories': categories,
            'images': images,
            'stock_quantity': int(catalog_row.get('stock', 0)),
            'manage_stock': True,
            'meta_data': [
                {'key': 'source_country', 'value': source_country},
                {'key': 'forwarder', 'value': forwarder},
                {'key': 'customs_info', 'value': catalog_row.get('customs_category', '')},
                {'key': 'buy_price', 'value': str(catalog_row.get('buy_price', ''))},
                {'key': 'buy_currency', 'value': catalog_row.get('buy_currency', '')},
            ],
        }
        return product

    def export_batch(self, products: list, output_path: str) -> str:
        """WooCommerce API를 통해 상품 일괄 등록/갱신.

        Args:
            products: prepare_product()로 변환된 상품 dict 리스트
            output_path: 미사용 (API 방식)

        Returns:
            빈 문자열
        """
        from src.vendors.woocommerce_client import upsert_product

        success = 0
        errors = []
        for prod in products:
            try:
                upsert_product(prod)
                success += 1
            except Exception as exc:
                sku = prod.get('sku', '?')
                logger.error('WooCommerce 업로드 실패 SKU=%s: %s', sku, exc)
                errors.append(str(exc))

        logger.info('WooCommerce 동기화 완료: 성공=%d, 실패=%d', success, len(errors))
        return ''

    def get_category_mapping(self, catalog_category: str) -> str:
        """카탈로그 카테고리 → WooCommerce 카테고리명 매핑."""
        return _CATEGORY_SLUGS.get(catalog_category, catalog_category)
