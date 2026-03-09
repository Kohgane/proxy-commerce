"""
포터 익스체인지 (요시다포터, yoshidakaban.com) 소싱 벤더 모듈.
Listly로 크롤링한 원시 데이터를 카탈로그 표준 형식으로 변환한다.
"""

import re
from .base_vendor import BaseVendor

# 포터 시리즈(카테고리) 매핑: 일본어명 → (영문명, SKU 코드)
PORTER_CATEGORIES = {
    'タンカー': ('TANKER', 'TNK'),
    'ヒート': ('HEAT', 'HET'),
    'ラゲッジレーベル': ('LUGGAGE LABEL', 'LGL'),
    'カレント': ('CURRENT', 'CRT'),
    'リフト': ('LIFT', 'LFT'),
    'フリースタイル': ('FREESTYLE', 'FRS'),
    'フラッシュ': ('FLASH', 'FLS'),
    'クラッシュ': ('CLASH', 'CLS'),
    'ドロー': ('DRAW', 'DRW'),
    'ユニオン': ('UNION', 'UNI'),
    'フォース': ('FORCE', 'FRC'),
}

# 영문 카테고리명 → SKU 코드 (normalize_row에서 영문 카테고리가 올 경우 대응)
_EN_CATEGORY_TO_CODE = {v[0]: v[1] for v in PORTER_CATEGORIES.values()}
_EN_CATEGORY_TO_CODE['OTHER'] = 'ETC'


def _clean_price(raw_price) -> float:
    """¥30,800 → 30800.0 형식으로 가격 문자열 정리."""
    if raw_price is None:
        return 0.0
    price_str = str(raw_price).replace('¥', '').replace(',', '').strip()
    match = re.search(r'[\d.]+', price_str)
    return float(match.group()) if match else 0.0


def _resolve_category(raw_row: dict) -> tuple:
    """
    원시 행에서 카테고리 정보를 추출한다.
    반환값: (영문 카테고리명, SKU 코드)
    """
    # 일본어 카테고리 필드 우선 시도
    ja_cat = raw_row.get('category_ja', '') or raw_row.get('series_ja', '') or ''
    for ja_key, (en_name, code) in PORTER_CATEGORIES.items():
        if ja_key in ja_cat:
            return en_name, code

    # 영문 카테고리 필드 시도
    en_cat = (raw_row.get('category', '') or raw_row.get('series', '') or '').upper()
    for en_key, code in _EN_CATEGORY_TO_CODE.items():
        if en_key in en_cat:
            return en_key, code

    return 'OTHER', 'ETC'


def _extract_product_number(raw_row: dict) -> str:
    """URL 또는 상품 코드 필드에서 숫자 상품번호 추출."""
    # 상품 코드 필드 직접 참조
    prod_code = raw_row.get('product_code', '') or raw_row.get('item_no', '') or ''
    digits = re.sub(r'\D', '', str(prod_code))
    if digits:
        return digits.zfill(3)[:6]

    # URL에서 숫자 추출
    url = raw_row.get('src_url', '') or raw_row.get('url', '') or ''
    nums = re.findall(r'\d+', url)
    if nums:
        return nums[-1].zfill(3)[:6]

    return '001'


class PorterVendor(BaseVendor):
    """포터 익스체인지 (요시다포터) 소싱 벤더."""

    vendor_name = "PORTER"
    source_country = "JP"
    buy_currency = "JPY"
    base_url = "https://www.yoshidakaban.com"
    forwarder = "zenmarket"

    def normalize_row(self, raw_row: dict) -> dict:
        """Listly에서 크롤링한 포터 원시 행 → 카탈로그 표준 형식."""
        en_cat, _ = _resolve_category(raw_row)
        images = self.extract_images(raw_row)

        # 태그 구성
        tags_list = ['porter']
        if en_cat and en_cat != 'OTHER':
            tags_list.append(en_cat.lower())
        product_type = raw_row.get('product_type', '') or raw_row.get('type', '') or ''
        if product_type:
            tags_list.append(product_type.lower())

        return {
            'sku': self.generate_sku(raw_row),
            'title_ko': raw_row.get('title_ko', ''),          # 번역은 catalog_sync에서 처리
            'title_en': raw_row.get('title_en', ''),          # 번역은 catalog_sync에서 처리
            'title_ja': raw_row.get('title_ja', '') or raw_row.get('title', '') or '',
            'title_fr': '',
            'src_url': raw_row.get('src_url', '') or raw_row.get('url', '') or '',
            'buy_currency': self.buy_currency,
            'buy_price': _clean_price(raw_row.get('price', '') or raw_row.get('buy_price', '')),
            'source_country': self.source_country,
            'images': ','.join(images),
            'stock': int(raw_row.get('stock', 0) or 0),
            'tags': ','.join(tags_list),
            'vendor': self.vendor_name,
            'status': raw_row.get('status', 'active'),
            'category': 'bag',
            'brand': 'PORTER',
            'forwarder': self.forwarder,
            'customs_category': 'bag',
        }

    def generate_sku(self, raw_row: dict) -> str:
        """형식: PTR-{카테고리코드}-{상품번호} (예: PTR-TNK-001)."""
        _, cat_code = _resolve_category(raw_row)
        prod_num = _extract_product_number(raw_row)
        return f"PTR-{cat_code}-{prod_num}"

    def extract_images(self, raw_row: dict) -> list:
        """
        이미지 URL 목록 추출 (최대 5장).
        요시다카반 사이트: 썸네일 URL → 원본 고해상도 URL 변환 시도.
        """
        images = []

        # 콤마 구분 이미지 문자열 처리
        raw_images = raw_row.get('images', '') or raw_row.get('image_urls', '') or ''
        if raw_images:
            for url in str(raw_images).split(','):
                url = url.strip()
                if url:
                    images.append(_upgrade_image_url(url))

        # 단일 이미지 필드 처리
        single = raw_row.get('image_url', '') or raw_row.get('thumbnail', '') or ''
        if single and single not in images:
            images.append(_upgrade_image_url(single.strip()))

        return images[:5]


def _upgrade_image_url(url: str) -> str:
    """
    yoshidakaban.com 썸네일 URL → 원본 고해상도 URL 변환.
    예: _thumb → _main 또는 쿼리 파라미터 제거
    """
    if not url:
        return url
    # 썸네일 패턴 변환 (사이트 구조에 따라 조정 가능)
    url = re.sub(r'_thumb(\.\w+)$', r'_main\1', url)
    url = re.sub(r'[?&]size=\w+', '', url)
    return url
