"""
메모파리 (Memo Paris, memoparis.com) 소싱 벤더 모듈.
Listly로 크롤링한 원시 데이터를 카탈로그 표준 형식으로 변환한다.
"""

import re
from .base_vendor import BaseVendor

# 메모파리 컬렉션 매핑: 컬렉션명 → SKU 컬렉션 코드
MEMO_COLLECTIONS = {
    'Graines Vagabondes': 'GRV',
    'Les Echappées': 'ECH',
    "Les Echapp\u00e9es": 'ECH',    # 유니코드 정규화 대응
    'Cuirs Nomades': 'CRN',
    'Art Land': 'ARL',
    'Moon Fever': 'MNF',
    'Siestes Andalouses': 'SAN',
    'Italian Leather': 'ITL',
    'Lalibela': 'LAL',
}

# 향수 라인(타입) → SKU 라인 코드
_FRAGRANCE_LINE_MAP = {
    'Eau de Parfum': 'EDP',
    'Eau de Toilette': 'EDT',
    'EDP': 'EDP',
    'EDT': 'EDT',
}


def _clean_price(raw_price) -> float:
    """€250.00 → 250.0 형식으로 가격 문자열 정리."""
    if raw_price is None:
        return 0.0
    price_str = str(raw_price).replace('€', '').replace(',', '').strip()
    match = re.search(r'[\d.]+', price_str)
    return float(match.group()) if match else 0.0


def _resolve_line_code(raw_row: dict) -> str:
    """
    원시 행에서 향수 라인 코드를 결정한다.
    반환값: 'EDP', 'EDT', 또는 'ETC'
    """
    for field in ('fragrance_type', 'line', 'type', 'title_en', 'title_fr', 'title'):
        val = str(raw_row.get(field, '') or '')
        for line_name, code in _FRAGRANCE_LINE_MAP.items():
            if line_name.lower() in val.lower():
                return code
    return 'ETC'


def _extract_volume_tag(raw_row: dict) -> str:
    """용량(ml) 태그 추출. 예: '75ml'."""
    for field in ('volume', 'size', 'title_en', 'title_fr', 'title', 'description'):
        val = str(raw_row.get(field, '') or '')
        match = re.search(r'(\d+)\s*ml', val, re.IGNORECASE)
        if match:
            return f"{match.group(1)}ml"
    return ''


def _extract_product_number(raw_row: dict) -> str:
    """URL 또는 상품 코드 필드에서 상품번호 추출."""
    prod_code = raw_row.get('product_code', '') or raw_row.get('item_no', '') or ''
    digits = re.sub(r'\D', '', str(prod_code))
    if digits:
        return digits.zfill(3)[:6]

    url = raw_row.get('src_url', '') or raw_row.get('url', '') or ''
    # URL 마지막 경로 세그먼트에서 숫자 추출
    nums = re.findall(r'\d+', url.rstrip('/').split('/')[-1])
    if nums:
        return nums[0].zfill(3)[:6]

    return '001'


class MemoPariVendor(BaseVendor):
    """메모파리 (Memo Paris) 소싱 벤더."""

    vendor_name = "MEMO_PARIS"
    source_country = "FR"
    buy_currency = "EUR"
    base_url = "https://www.memoparis.com"
    forwarder = ""   # 직배송 또는 유럽 배대지

    def normalize_row(self, raw_row: dict) -> dict:
        """Listly에서 크롤링한 메모파리 원시 행 → 카탈로그 표준 형식."""
        images = self.extract_images(raw_row)
        volume_tag = _extract_volume_tag(raw_row)
        line_code = _resolve_line_code(raw_row)

        # 태그 구성
        tags_list = ['perfume']
        if line_code != 'ETC':
            tags_list.append(line_code.lower())
        if volume_tag:
            tags_list.append(volume_tag)

        return {
            'sku': self.generate_sku(raw_row),
            'title_ko': raw_row.get('title_ko', ''),              # 번역은 catalog_sync에서 처리
            'title_en': raw_row.get('title_en', '') or raw_row.get('title', '') or '',
            'title_ja': '',
            'title_fr': raw_row.get('title_fr', '') or raw_row.get('title', '') or '',
            'src_url': raw_row.get('src_url', '') or raw_row.get('url', '') or '',
            'buy_currency': self.buy_currency,
            'buy_price': _clean_price(raw_row.get('price', '') or raw_row.get('buy_price', '')),
            'source_country': self.source_country,
            'images': ','.join(images),
            'stock': int(raw_row.get('stock', 0) or 0),
            'tags': ','.join(tags_list),
            'vendor': self.vendor_name,
            'status': raw_row.get('status', 'active'),
            'category': 'perfume',
            'brand': 'MEMO_PARIS',
            'forwarder': self.forwarder,
            'customs_category': 'perfume',
        }

    def generate_sku(self, raw_row: dict) -> str:
        """형식: MMP-{라인코드}-{번호} (예: MMP-EDP-001)."""
        line_code = _resolve_line_code(raw_row)
        prod_num = _extract_product_number(raw_row)
        return f"MMP-{line_code}-{prod_num}"

    def extract_images(self, raw_row: dict) -> list:
        """
        이미지 URL 목록 추출 (최대 3장).
        memoparis.com 이미지 URL 패턴 처리.
        """
        images = []

        # 콤마 구분 이미지 문자열 처리
        raw_images = raw_row.get('images', '') or raw_row.get('image_urls', '') or ''
        if raw_images:
            for url in str(raw_images).split(','):
                url = url.strip()
                if url:
                    images.append(url)

        # 단일 이미지 필드 처리
        single = raw_row.get('image_url', '') or raw_row.get('thumbnail', '') or ''
        if single and single not in images:
            images.append(single.strip())

        return images[:3]
