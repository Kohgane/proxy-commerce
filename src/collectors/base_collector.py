"""수집기 기본 클래스 — 모든 해외 쇼핑몰 수집기의 ABC."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone


class BaseCollector(ABC):
    """해외 쇼핑몰 상품 수집기 기본 클래스."""

    collector_name: str  # 'amazon_us', 'amazon_jp', 'taobao' 등
    marketplace: str     # 'amazon', 'taobao', 'aliexpress' 등
    country: str         # 'US', 'JP', 'CN' 등
    currency: str        # 'USD', 'JPY', 'CNY' 등
    base_url: str        # 'https://www.amazon.com' 등

    # 수집 결과의 표준 필드 정의
    COLLECTED_FIELDS = [
        'collector_id',          # 수집기 내부 ID (ASIN 등)
        'source_url',            # 원본 상품 URL
        'title_original',        # 원어 상품명
        'title_ko',              # 한글 번역 상품명
        'title_en',              # 영문 상품명 (이미 영문이면 그대로)
        'description_original',  # 원어 상세설명
        'description_ko',        # 한글 번역 상세설명
        'description_html',      # 상세페이지 HTML
        'price_original',        # 원본 가격 (현지 통화)
        'currency',              # 통화 코드
        'price_krw',             # KRW 환산 원가
        'sell_price_krw',        # 마진 포함 판매가 (KRW)
        'sell_price_usd',        # USD 판매가
        'images',                # 이미지 URL 리스트
        'category',              # 카테고리
        'brand',                 # 브랜드
        'rating',                # 평점
        'review_count',          # 리뷰 수
        'stock_status',          # 재고 상태
        'weight_kg',             # 중량 (kg)
        'dimensions',            # 사이즈 정보
        'options',               # 옵션 (색상, 사이즈 등)
        'tags',                  # 태그 목록
        'vendor',                # 벤더 식별자
        'collected_at',          # 수집 시각
        'marketplace',           # 마켓플레이스명
        'country',               # 국가코드
    ]

    @abstractmethod
    def collect_product(self, url: str) -> dict:
        """단일 상품 URL에서 상품 정보를 수집한다.

        Returns: COLLECTED_FIELDS 기반 딕셔너리
        에러 시 None 반환 (절대 크래시하지 않음)
        """

    @abstractmethod
    def search_products(self, keyword: str, max_results: int = 20) -> list:
        """키워드로 상품을 검색하여 수집한다."""

    @abstractmethod
    def collect_batch(self, urls: list) -> list:
        """여러 상품 URL을 배치로 수집한다."""

    def translate_product(self, product: dict) -> dict:
        """수집된 상품의 상품명/설명을 한글로 번역한다.

        기존 src/translate.py를 활용.
        번역 실패 시 원문을 유지하고 절대 크래시하지 않는다.
        """
        if not product:
            return product
        try:
            from src.translate import translate
            title_orig = product.get('title_original', '') or ''
            if title_orig and not product.get('title_ko'):
                product['title_ko'] = translate(title_orig, 'auto', 'KO') or title_orig
            if title_orig and not product.get('title_en'):
                country = product.get('country', 'US')
                if country == 'JP':
                    product['title_en'] = translate(title_orig, 'JA', 'EN') or title_orig
                else:
                    product['title_en'] = title_orig
            desc_orig = product.get('description_original', '') or ''
            if desc_orig and not product.get('description_ko'):
                product['description_ko'] = translate(desc_orig, 'auto', 'KO') or desc_orig
        except Exception:
            pass
        return product

    def calculate_prices(self, product: dict) -> dict:
        """수집된 상품의 가격을 KRW/USD로 계산한다.

        기존 src/price.py + src/fx/ 활용.
        마진율, 배송비, 관세를 포함한 최종 판매가 계산.
        """
        if not product:
            return product
        try:
            from src.price import calc_landed_cost, _build_fx_rates
            price_orig = product.get('price_original')
            currency = product.get('currency', 'USD')
            if price_orig is None:
                return product
            price_orig = float(price_orig)
            import os
            margin_pct = float(os.environ.get('IMPORT_MARGIN_PCT', '25'))
            fx_rates = _build_fx_rates()
            sell_krw = calc_landed_cost(
                buy_price=price_orig,
                buy_currency=currency,
                margin_pct=margin_pct,
                fx_rates=fx_rates,
            )
            product['sell_price_krw'] = int(sell_krw)
            # KRW 원가 계산 (마진/비용 제외)
            usd_krw = float(fx_rates.get('USDKRW', 1350))
            jpy_krw = float(fx_rates.get('JPYKRW', 9.0))
            eur_krw = float(fx_rates.get('EURKRW', 1470))
            if currency == 'USD':
                price_krw = price_orig * usd_krw
            elif currency == 'JPY':
                price_krw = price_orig * jpy_krw
            elif currency == 'EUR':
                price_krw = price_orig * eur_krw
            else:
                price_krw = price_orig
            product['price_krw'] = int(price_krw)
            product['sell_price_usd'] = round(sell_krw / usd_krw, 2)
        except Exception:
            pass
        return product

    def generate_sku(self, product: dict) -> str:
        """수집된 상품에 SKU를 부여한다.

        Amazon US: AMZ-US-{카테고리코드}-{번호}
        Amazon JP: AMZ-JP-{카테고리코드}-{번호}
        """
        if not product:
            return ''
        marketplace = product.get('marketplace', 'amazon').upper()
        country = product.get('country', 'US').upper()
        category_code = product.get('category_code', 'GEN')
        collector_id = product.get('collector_id', '')
        if marketplace == 'AMAZON':
            prefix = 'AMZ'
        else:
            prefix = marketplace[:3]
        # 번호: collector_id(ASIN) 마지막 3자리 숫자화, 없으면 타임스탬프 사용
        if collector_id:
            suffix = ''.join(filter(str.isdigit, collector_id[-4:])) or '001'
            suffix = suffix[-3:].zfill(3)
        else:
            suffix = datetime.now(timezone.utc).strftime('%H%M')
        return f'{prefix}-{country}-{category_code}-{suffix}'
