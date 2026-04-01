"""업로더 기본 클래스 — 모든 쇼핑몰 업로더의 ABC."""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseUploader(ABC):
    """해외직구 상품 업로더 기본 클래스."""

    uploader_name: str   # 'coupang', 'naver_smartstore' 등
    marketplace: str     # 'coupang', 'naver' 등

    UPLOAD_FIELDS = [
        'sku',
        'title',
        'description_html',
        'price',
        'original_price',
        'images',
        'category_id',
        'brand',
        'weight_kg',
        'stock',
        'options',
        'tags',
        'shipping_fee',
        'delivery_days',
        'return_info',
    ]

    @abstractmethod
    def upload_product(self, product: dict) -> dict:
        """단일 상품을 업로드한다.

        Returns:
            성공: {'success': True, 'product_id': '...', 'url': '...'}
            실패: {'success': False, 'error': '...'}
        """

    @abstractmethod
    def update_product(self, product_id: str, updates: dict) -> dict:
        """이미 업로드된 상품 정보를 업데이트한다.

        Returns:
            성공: {'success': True}
            실패: {'success': False, 'error': '...'}
        """

    @abstractmethod
    def delete_product(self, product_id: str) -> bool:
        """업로드된 상품을 삭제한다. 성공 시 True 반환."""

    @abstractmethod
    def get_categories(self) -> list:
        """마켓플레이스의 카테고리 목록을 반환한다."""

    def upload_batch(self, products: list) -> dict:
        """여러 상품을 일괄 업로드한다.

        Args:
            products: prepare_product() 출력 딕셔너리 목록

        Returns:
            {'total': N, 'success': M, 'failed': K, 'results': [...]}
        """
        total = len(products)
        success = 0
        failed = 0
        results = []
        for product in products:
            try:
                result = self.upload_product(product)
                if result.get('success'):
                    success += 1
                else:
                    failed += 1
                results.append(result)
            except Exception as exc:
                logger.error('upload_batch: failed for product %s: %s', product.get('sku', ''), exc)
                failed += 1
                results.append({'success': False, 'error': str(exc), 'sku': product.get('sku', '')})
        return {'total': total, 'success': success, 'failed': failed, 'results': results}

    def prepare_product(self, collected: dict) -> dict:
        """수집된 상품 딕셔너리를 업로드 형식으로 변환한다.

        하위 클래스에서 override하여 마켓플레이스 전용 변환을 구현한다.
        기본 구현은 UPLOAD_FIELDS에 맞는 기본 매핑을 수행한다.
        """
        if not collected:
            return {}
        return {
            'sku': collected.get('sku', ''),
            'title': collected.get('title_ko') or collected.get('title_original', ''),
            'description_html': collected.get('description_html', ''),
            'price': collected.get('sell_price_krw', 0),
            'original_price': collected.get('price_krw', 0),
            'images': collected.get('images', []),
            'category_id': '',
            'brand': collected.get('brand', ''),
            'weight_kg': collected.get('weight_kg'),
            'stock': 999,
            'options': collected.get('options', {}),
            'tags': collected.get('tags', []),
            'shipping_fee': 0,
            'delivery_days': '7-14',
            'return_info': '해외직구 상품으로 반품/교환이 불가합니다',
        }
