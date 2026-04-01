"""src/editor/image_processor.py — 수집 이미지 후처리 (Cloudinary URL 변환)."""

# 마켓별 이미지 최대 사이즈 규격
MARKET_SPECS = {
    'coupang': {'width': 1000, 'height': 1000, 'format': 'jpg'},
    'smartstore': {'width': 1000, 'height': 1000, 'format': 'jpg'},
    'shopify': {'width': 2048, 'height': 2048, 'format': 'jpg'},
}


class ImageProcessor:
    """수집 이미지 후처리 — Cloudinary transform URL 생성."""

    def __init__(self, cloud_name: str = ''):
        self._cloud_name = cloud_name

    def _cloudinary_url(self, image_url: str, transforms: str) -> str:
        """Cloudinary fetch URL에 변환 파라미터를 적용한 URL을 생성한다."""
        cloud = self._cloud_name or 'demo'
        encoded = image_url.replace('/', '%2F').replace(':', '%3A')
        return f'https://res.cloudinary.com/{cloud}/image/fetch/{transforms}/{encoded}'

    def resize(self, image_url: str, width: int, height: int) -> str:
        """이미지 리사이즈 — Cloudinary transform URL 반환.

        Args:
            image_url: 원본 이미지 URL
            width: 목표 너비 (px)
            height: 목표 높이 (px)

        Returns:
            Cloudinary resize URL 문자열
        """
        transforms = f'w_{width},h_{height},c_fit,f_auto,q_auto'
        return self._cloudinary_url(image_url, transforms)

    def add_watermark(self, image_url: str, text: str) -> str:
        """워터마크 추가 — Cloudinary overlay URL 반환.

        Args:
            image_url: 원본 이미지 URL
            text: 워터마크 텍스트

        Returns:
            Cloudinary watermark URL 문자열
        """
        safe_text = text.replace(' ', '_').replace('/', '_')
        transforms = f'l_text:Arial_20:{safe_text},g_south_east,x_10,y_10,o_60'
        return self._cloudinary_url(image_url, transforms)

    def optimize_for_market(self, image_url: str, market: str) -> str:
        """마켓별 이미지 최적화 URL 반환.

        마켓별 규격:
        - 쿠팡: 최대 1000x1000, JPEG
        - 스마트스토어: 최대 1000x1000, JPEG/PNG
        - Shopify: 최대 2048x2048

        Args:
            image_url: 원본 이미지 URL
            market: 마켓명 ('coupang', 'smartstore', 'shopify')

        Returns:
            최적화된 Cloudinary URL 문자열
        """
        spec = MARKET_SPECS.get(market, MARKET_SPECS['shopify'])
        w, h, fmt = spec['width'], spec['height'], spec['format']
        transforms = f'w_{w},h_{h},c_fit,f_{fmt},q_auto'
        return self._cloudinary_url(image_url, transforms)

    def batch_process(self, image_urls: list, market: str) -> list:
        """이미지 목록 일괄 처리.

        Args:
            image_urls: 원본 이미지 URL 리스트
            market: 마켓명

        Returns:
            최적화된 URL 리스트
        """
        return [self.optimize_for_market(url, market) for url in image_urls]
