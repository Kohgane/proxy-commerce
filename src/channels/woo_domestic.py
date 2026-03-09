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
    'accessory': '액세서리',
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
        from src.vendors.woocommerce_client import prepare_product_data
        return prepare_product_data(catalog_row, sell_price)

    def export_batch(self, products: list, output_path: str) -> str:
        """WooCommerce API를 통해 상품 일괄 등록/갱신.

        Args:
            products: prepare_product()로 변환된 상품 dict 리스트
            output_path: 미사용 (API 방식)

        Returns:
            빈 문자열
        """
        from src.vendors.woocommerce_client import upsert_batch

        results = upsert_batch(products)
        logger.info(
            'WooCommerce 동기화 완료: 생성=%d, 갱신=%d, 실패=%d',
            results['created'],
            results['updated'],
            len(results['errors']),
        )
        return ''

    def get_category_mapping(self, catalog_category: str) -> str:
        """카탈로그 카테고리 → WooCommerce 카테고리명 매핑."""
        return _CATEGORY_SLUGS.get(catalog_category, catalog_category)
