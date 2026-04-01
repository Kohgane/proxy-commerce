"""국제배송비 + 통관비용 + 국내배송비 계산 모듈."""

from typing import Dict

# 국제배송비 기준표 (USD/kg, 대략적인 운임)
# 실제 서비스에서는 포워더별 API 연동 권장
_INTL_SHIPPING_RATES_USD_PER_KG: Dict[str, float] = {
    'us': 8.0,    # 미국 → 한국
    'jp': 3.0,    # 일본 → 한국 (가까운 거리)
    'cn': 2.5,    # 중국 → 한국 (가까운 거리)
    'de': 9.0,    # 독일 → 한국
    'fr': 9.0,    # 프랑스 → 한국
    'gb': 9.0,    # 영국 → 한국
    'ca': 9.5,    # 캐나다 → 한국
    'mx': 10.0,   # 멕시코 → 한국
    'au': 8.5,    # 호주 → 한국
    'sg': 5.0,    # 싱가포르 → 한국
    'default': 9.0,
}

# 마켓별 출발국 매핑
_MARKETPLACE_ORIGIN: Dict[str, str] = {
    'amazon_us': 'us',
    'amazon_jp': 'jp',
    'amazon_de': 'de',
    'amazon_fr': 'fr',
    'amazon_it': 'de',   # 이탈리아는 독일 운임 적용
    'amazon_es': 'de',   # 스페인
    'amazon_uk': 'gb',
    'amazon_ca': 'ca',
    'amazon_mx': 'mx',
    'amazon_au': 'au',
    'taobao': 'cn',
    'tmall': 'cn',
    'aliexpress': 'cn',
    '1688': 'cn',
    'rakuten': 'jp',
    'zozotown': 'jp',
}

# 통관비용 기준 (KRW)
_CUSTOMS_FEE_KRW = 15000        # 기본 통관 수수료
_CUSTOMS_DUTY_THRESHOLD = 150   # USD 면세 한도 (개인 직구)
_CUSTOMS_DUTY_RATE = 0.20       # 관세율 (약 20% 평균, 품목별 상이)
_VAT_RATE = 0.10                # 부가세 10%

# 국내배송비 (KRW)
_DOMESTIC_SHIPPING_KRW = 3000       # 기본 국내배송비
_DOMESTIC_FREE_SHIPPING_THRESHOLD = 50000  # 이 금액 이상이면 무료배송 가능


class ShippingCost:
    """국제배송비 + 통관비용 + 국내배송비 계산 클래스."""

    def __init__(self, krw_per_usd: float = 1350.0):
        """초기화.

        Args:
            krw_per_usd: USD→KRW 환율 (기본 1350)
        """
        self._krw_per_usd = float(krw_per_usd)

    # ── public API ───────────────────────────────────────────

    def calculate_international_shipping(
        self,
        weight_kg: float,
        origin_country: str = 'us',
        marketplace: str = None,
    ) -> float:
        """국제배송비 계산 (KRW).

        Args:
            weight_kg: 상품 무게 (kg)
            origin_country: 출발국 코드 (us, jp, cn 등)
            marketplace: 마켓플레이스명 (origin_country 대신 사용 가능)

        Returns:
            국제배송비 (KRW)
        """
        if marketplace:
            origin = _MARKETPLACE_ORIGIN.get(marketplace.lower(), origin_country)
        else:
            origin = origin_country.lower()

        rate_usd_per_kg = _INTL_SHIPPING_RATES_USD_PER_KG.get(
            origin, _INTL_SHIPPING_RATES_USD_PER_KG['default']
        )
        shipping_usd = max(weight_kg, 0.5) * rate_usd_per_kg  # 최소 0.5kg 적용
        return shipping_usd * self._krw_per_usd

    def calculate_customs_fee(
        self,
        product_price_usd: float,
        weight_kg: float = 0.5,
        include_vat: bool = True,
    ) -> dict:
        """통관비용 계산 (KRW).

        미화 150달러 이하 개인 직구는 관세/부가세 면제 (목록통관).

        Args:
            product_price_usd: 상품가격 (USD)
            weight_kg: 무게 (kg, 미사용 현재는 참고용)
            include_vat: 부가세 포함 여부

        Returns:
            {
                'customs_fee': 통관 수수료 (KRW),
                'import_duty': 관세 (KRW),
                'vat': 부가세 (KRW),
                'total': 총 통관비용 (KRW),
                'is_duty_free': 면세 여부,
            }
        """
        is_duty_free = product_price_usd <= _CUSTOMS_DUTY_THRESHOLD
        customs_fee = _CUSTOMS_FEE_KRW  # 기본 통관 수수료

        if is_duty_free:
            return {
                'customs_fee': customs_fee,
                'import_duty': 0.0,
                'vat': 0.0,
                'total': float(customs_fee),
                'is_duty_free': True,
            }

        # 과세 대상
        dutiable_value_krw = product_price_usd * self._krw_per_usd
        import_duty = dutiable_value_krw * _CUSTOMS_DUTY_RATE
        vat = (dutiable_value_krw + import_duty) * _VAT_RATE if include_vat else 0.0
        total = customs_fee + import_duty + vat

        return {
            'customs_fee': float(customs_fee),
            'import_duty': import_duty,
            'vat': vat,
            'total': total,
            'is_duty_free': False,
        }

    def calculate_domestic_shipping(
        self,
        sale_price_krw: float,
        free_shipping: bool = False,
    ) -> float:
        """국내배송비 계산 (KRW).

        Args:
            sale_price_krw: 판매가 (KRW)
            free_shipping: 무료배송 여부 (강제 설정)

        Returns:
            국내배송비 (KRW)
        """
        if free_shipping:
            return 0.0
        if sale_price_krw >= _DOMESTIC_FREE_SHIPPING_THRESHOLD:
            return 0.0
        return float(_DOMESTIC_SHIPPING_KRW)

    def calculate_total_shipping(
        self,
        weight_kg: float,
        product_price_usd: float,
        origin_country: str = 'us',
        marketplace: str = None,
        sale_price_krw: float = 0.0,
        free_domestic: bool = False,
    ) -> dict:
        """총 배송/통관 비용 계산.

        Args:
            weight_kg: 무게 (kg)
            product_price_usd: 상품가격 (USD)
            origin_country: 출발국 코드
            marketplace: 마켓플레이스명
            sale_price_krw: 판매가 (KRW, 국내배송비 계산용)
            free_domestic: 무료 국내배송 여부

        Returns:
            {
                'international_shipping': 국제배송비 (KRW),
                'customs': 통관비용 상세,
                'domestic_shipping': 국내배송비 (KRW),
                'total': 총 배송비 (KRW),
            }
        """
        intl = self.calculate_international_shipping(weight_kg, origin_country, marketplace)
        customs = self.calculate_customs_fee(product_price_usd, weight_kg)
        domestic = self.calculate_domestic_shipping(sale_price_krw, free_domestic)
        total = intl + customs['total'] + domestic

        return {
            'international_shipping': intl,
            'customs': customs,
            'domestic_shipping': domestic,
            'total': total,
        }

    def set_exchange_rate(self, krw_per_usd: float):
        """환율 업데이트.

        Args:
            krw_per_usd: 새로운 USD→KRW 환율
        """
        self._krw_per_usd = float(krw_per_usd)

    @property
    def exchange_rate(self) -> float:
        """현재 USD→KRW 환율."""
        return self._krw_per_usd
