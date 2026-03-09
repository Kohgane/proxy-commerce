"""
퍼센티(Percenty) CSV 생성기

퍼센티에서 요구하는 CSV 형식으로 상품 데이터를 변환하고 내보낸다.
"""

import csv
import logging
import os
from string import Template

from .base_channel import BaseChannel

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# 카테고리 매핑
# ──────────────────────────────────────────────────────────

COUPANG_CATEGORIES = {
    'bag': '패션잡화 > 남성가방 > 서류가방',
    'wallet': '패션잡화 > 남성지갑 > 장지갑',
    'perfume': '뷰티 > 향수/디퓨저 > 향수 > 남녀공용향수',
    'pouch': '패션잡화 > 파우치/케이스',
}

NAVER_CATEGORIES = {
    'bag': '50000804',      # 남성가방
    'wallet': '50000805',   # 남성지갑
    'perfume': '50000540',  # 향수
    'pouch': '50000807',    # 파우치
}

# ──────────────────────────────────────────────────────────
# 마켓별 가격 정책
# ──────────────────────────────────────────────────────────

MARKET_PRICE_POLICY = {
    'coupang': {
        'strategy': 'competitive',     # 최저가 경쟁
        'margin_adjust': -2.0,         # 기본 마진에서 -2%
        'commission_rate': 10.8,       # 쿠팡 수수료율
    },
    'smartstore': {
        'strategy': 'margin_first',    # 마진 우선
        'margin_adjust': 0.0,          # 기본 마진 유지
        'commission_rate': 5.0,        # 스마트스토어 수수료율
    },
    '11st': {
        'strategy': 'balanced',
        'margin_adjust': -1.0,
        'commission_rate': 12.0,
    },
}

# 퍼센티 CSV 컬럼 순서
PERCENTY_COLUMNS = [
    '상품명', '판매가', '할인가', '카테고리', '옵션', '상세설명HTML',
    '대표이미지URL', '추가이미지URL', '재고수량', '배송방법',
    '배송비', '출고지', '반품지', 'A/S정보', '원산지', '브랜드',
    '바코드/SKU', '키워드/태그',
]

# 상세페이지 HTML 템플릿 디렉토리
_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')


def _load_template(filename: str) -> str:
    """HTML 템플릿 파일을 읽어 반환한다."""
    path = os.path.join(_TEMPLATE_DIR, filename)
    with open(path, encoding='utf-8') as f:
        return f.read()


class PercentyExporter(BaseChannel):
    """퍼센티 통합 마켓 CSV 내보내기 채널."""

    channel_name = 'percenty'
    target_currency = 'KRW'
    supported_markets = ['coupang', 'smartstore', '11st', 'gmarket']

    # ──────────────────────────────────────────────────────
    # BaseChannel 구현
    # ──────────────────────────────────────────────────────

    def prepare_product(self, catalog_row: dict, sell_price: float) -> dict:
        """카탈로그 표준 형식 → 퍼센티 CSV 필드 매핑.

        Args:
            catalog_row: CATALOG_FIELDS 형식의 카탈로그 행
            sell_price: calc_landed_cost()로 미리 계산된 KRW 판매가

        Returns:
            퍼센티 CSV 한 행에 해당하는 dict (키: PERCENTY_COLUMNS)
        """
        source_country = catalog_row.get('source_country', '')
        _origin_map = {'JP': '일본', 'FR': '프랑스'}
        origin_ko = _origin_map.get(source_country, source_country)

        # 이미지 파싱: 콤마 구분 문자열 또는 리스트 허용
        images_raw = catalog_row.get('images', '') or ''
        if isinstance(images_raw, list):
            image_list = [u.strip() for u in images_raw if u.strip()]
        else:
            image_list = [u.strip() for u in images_raw.split(',') if u.strip()]

        main_image = image_list[0] if image_list else ''
        extra_images = ','.join(image_list[1:]) if len(image_list) > 1 else ''

        return {
            '상품명': catalog_row.get('title_ko') or catalog_row.get('title_en') or '',
            '판매가': int(sell_price),
            '할인가': '',
            '카테고리': self.get_category_mapping(catalog_row.get('category', '')),
            '옵션': '',
            '상세설명HTML': self.generate_description_html(catalog_row),
            '대표이미지URL': main_image,
            '추가이미지URL': extra_images,
            '재고수량': catalog_row.get('stock', 0),
            '배송방법': '해외배송',
            '배송비': 0,
            '출고지': os.getenv('WAREHOUSE_ADDRESS', ''),
            '반품지': os.getenv('RETURN_ADDRESS', ''),
            'A/S정보': '해외 직구 상품으로 국내 A/S 불가',
            '원산지': origin_ko,
            '브랜드': catalog_row.get('brand', ''),
            '바코드/SKU': catalog_row.get('sku', ''),
            '키워드/태그': catalog_row.get('tags', ''),
        }

    def export_batch(self, products: list, output_path: str) -> str:
        """변환된 상품 리스트 → UTF-8 BOM CSV 파일로 내보내기.

        Args:
            products: prepare_product()로 변환된 상품 dict 리스트
            output_path: 출력 파일 경로

        Returns:
            생성된 CSV 파일의 절대 경로
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # UTF-8 with BOM — 한글 엑셀 호환
        with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=PERCENTY_COLUMNS, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(products)

        logger.info('CSV 내보내기 완료: %s (%d개)', output_path, len(products))
        return os.path.abspath(output_path)

    def get_category_mapping(self, catalog_category: str) -> str:
        """카탈로그 카테고리 → 퍼센티(쿠팡 기본) 카테고리 문자열 매핑."""
        return COUPANG_CATEGORIES.get(catalog_category, catalog_category)

    # ──────────────────────────────────────────────────────
    # 퍼센티 전용 메서드
    # ──────────────────────────────────────────────────────

    def generate_description_html(self, catalog_row: dict) -> str:
        """벤더별 상세페이지 HTML을 생성한다.

        포터 상품은 porter_detail.html 템플릿을,
        메모파리 상품은 memo_detail.html 템플릿을 사용한다.
        """
        vendor = (catalog_row.get('vendor') or '').upper()
        source_country = catalog_row.get('source_country', '')

        if vendor == 'PORTER' or source_country == 'JP':
            return self._render_porter_html(catalog_row)
        elif vendor == 'MEMO_PARIS' or source_country == 'FR':
            return self._render_memo_html(catalog_row)
        else:
            # 알 수 없는 벤더: 빈 HTML 반환 (경고 로그)
            logger.warning('알 수 없는 벤더/국가 — 상세 HTML 생성 생략: vendor=%s, country=%s', vendor, source_country)
            return ''

    def _render_porter_html(self, row: dict) -> str:
        """포터 상품 상세 HTML 렌더링."""
        try:
            tmpl = _load_template('porter_detail.html')
        except FileNotFoundError:
            return ''
        return Template(tmpl).safe_substitute(
            brand=row.get('brand', 'PORTER'),
            title_ko=row.get('title_ko') or row.get('title_ja', ''),
            category=row.get('category', ''),
        )

    def _render_memo_html(self, row: dict) -> str:
        """메모파리 상품 상세 HTML 렌더링."""
        try:
            tmpl = _load_template('memo_detail.html')
        except FileNotFoundError:
            return ''
        tags = row.get('tags', '')
        # 용량 정보 추출 (태그에서 ml/L 포함 값)
        volume = ''
        for tag in tags.split(','):
            tag = tag.strip()
            if 'ml' in tag.lower() or 'l' in tag.lower():
                volume = tag
                break
        return Template(tmpl).safe_substitute(
            title_ko=row.get('title_ko') or row.get('title_en', ''),
            collection=row.get('category', ''),
            volume=volume,
            fragrance_type=row.get('fragrance_type', ''),
        )

    def export_for_market(self, products: list, market: str, output_path: str) -> str:
        """마켓별 특화 CSV 생성.

        쿠팡/스마트스토어/11st 등 마켓 고유 카테고리 코드와
        가격 정책을 적용한 CSV를 생성한다.

        Args:
            products: prepare_product()로 변환된 상품 dict 리스트
            market: 'coupang' | 'smartstore' | '11st'
            output_path: 출력 파일 경로

        Returns:
            생성된 CSV 파일의 절대 경로
        """
        market_lower = market.lower()
        policy = MARKET_PRICE_POLICY.get(market_lower, {})
        margin_adjust_pct = float(
            os.getenv(
                'COUPANG_MARGIN_ADJUST' if market_lower == 'coupang' else 'NAVER_MARGIN_ADJUST',
                str(policy.get('margin_adjust', 0.0)),
            )
        )

        market_products = []
        for prod in products:
            adjusted = dict(prod)
            sell_price = float(adjusted.get('판매가', 0))

            # 마켓별 가격 조정
            if sell_price and margin_adjust_pct != 0.0:
                adjusted['판매가'] = int(sell_price * (1 + margin_adjust_pct / 100))

            # 마켓별 카테고리 코드 적용
            category_key = ''
            for cat_ko, cat_code in COUPANG_CATEGORIES.items():
                if adjusted.get('카테고리') == cat_code:
                    category_key = cat_ko
                    break
            if not category_key:
                category_key = adjusted.get('카테고리', '')

            if market_lower == 'smartstore':
                adjusted['카테고리'] = NAVER_CATEGORIES.get(category_key, category_key)
            else:
                adjusted['카테고리'] = COUPANG_CATEGORIES.get(category_key, adjusted.get('카테고리', ''))

            market_products.append(adjusted)

        logger.info('마켓별 CSV 생성: market=%s, 상품수=%d', market, len(market_products))
        return self.export_batch(market_products, output_path)
