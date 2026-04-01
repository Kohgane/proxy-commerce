"""src/editor/editor.py — 상품 상세페이지 편집 통합 인터페이스."""

import logging
from .template_engine import TemplateEngine
from .image_processor import ImageProcessor
from .market_sanitizer import MarketSanitizer

logger = logging.getLogger(__name__)

_PREVIEW_WRAPPER = '''\
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>미리보기 — {title}</title>
<style>
  body {{ font-family: sans-serif; margin: 0; padding: 0; }}
</style>
</head>
<body>
{body}
</body>
</html>'''


class ProductEditor:
    """상품 상세페이지 편집 통합 인터페이스."""

    def __init__(self, cloud_name: str = ''):
        self._engine = TemplateEngine()
        self._processor = ImageProcessor(cloud_name=cloud_name)
        self._sanitizer = MarketSanitizer()

    def load_product(self, sku: str) -> dict:
        """SKU로 상품 로드 (Google Sheets 카탈로그에서).

        실제 환경에서는 gspread로 카탈로그 시트를 조회한다.
        테스트 환경에서는 빈 딕셔너리 구조를 반환한다.

        Args:
            sku: 상품 SKU (예: PTR-TNK-001)

        Returns:
            상품 데이터 딕셔너리
        """
        try:
            from src.catalog_sync import CatalogSync
            sync = CatalogSync()
            product = sync.get_product_by_sku(sku)
            if product:
                return product
        except Exception as exc:
            logger.warning('카탈로그 로드 실패 (sku=%s): %s', sku, exc)

        # 기본 구조 반환
        return {
            'sku': sku,
            'title_ko': '',
            'title_en': '',
            'description': '',
            'images': [],
            'specs': {},
            'shipping_info': '',
            'origin_country': '',
        }

    def edit_fields(self, product: dict, updates: dict) -> dict:
        """상품 필드 편집.

        Args:
            product: 기존 상품 데이터
            updates: 업데이트할 필드 딕셔너리

        Returns:
            업데이트된 상품 딕셔너리 (원본은 변경하지 않음)
        """
        result = dict(product)
        result.update(updates)
        return result

    def generate_detail_page(self, product: dict, template: str = 'default') -> str:
        """상세페이지 HTML 생성.

        Args:
            product: 상품 데이터 딕셔너리
            template: 템플릿명 (default/luxury/cosmetic/electronics)

        Returns:
            렌더링된 HTML 문자열
        """
        return self._engine.render(product, template_name=template)

    def preview(self, html: str) -> str:
        """미리보기용 standalone HTML 파일 생성.

        Args:
            html: 본문 HTML

        Returns:
            완전한 standalone HTML 문자열
        """
        title = '상품 상세페이지 미리보기'
        return _PREVIEW_WRAPPER.format(title=title, body=html)

    def export_for_market(self, product: dict, market: str) -> dict:
        """마켓별 규격 변환 (HTML sanitize + 이미지 최적화).

        Args:
            product: 상품 데이터 딕셔너리
            market: 마켓명 ('coupang', 'smartstore', 'shopify')

        Returns:
            마켓용으로 변환된 딕셔너리
            - 'html': sanitize된 HTML
            - 'images': 최적화된 이미지 URL 리스트
            - 'validation': 유효성 검사 결과
        """
        html = self.generate_detail_page(product)
        sanitized_html = self._sanitizer.sanitize(html, market)
        optimized_images = self._processor.batch_process(product.get('images', []), market)
        validation = self._sanitizer.validate(sanitized_html, market)

        return {
            'html': sanitized_html,
            'images': optimized_images,
            'validation': validation,
            'market': market,
            'sku': product.get('sku', ''),
        }
