"""마켓별 수수료 구조 정의.

쿠팡, 네이버 스마트스토어의 카테고리별 수수료율을 관리합니다.
"""

from typing import Dict

# 쿠팡 카테고리별 판매수수료율 (%)
# 출처: 쿠팡 Wing 파트너 센터 기준
COUPANG_FEE_RATES: Dict[str, float] = {
    # 패션/의류
    'fashion': 10.8,
    'clothing': 10.8,
    'shoes': 10.8,
    'bags': 10.8,
    'accessories': 10.8,
    # 뷰티/건강
    'beauty': 12.0,
    'health': 12.0,
    'cosmetics': 12.0,
    # 전자/디지털
    'electronics': 10.8,
    'digital': 10.8,
    'mobile': 10.8,
    'computer': 10.8,
    'camera': 10.8,
    # 가전
    'appliance': 10.8,
    'kitchen': 10.8,
    # 스포츠/아웃도어
    'sports': 12.0,
    'outdoor': 12.0,
    # 자동차
    'automotive': 12.0,
    # 완구/유아
    'toys': 12.0,
    'baby': 12.0,
    # 도서/음반
    'books': 10.8,
    'music': 10.8,
    # 식품/음료
    'food': 18.0,
    'beverage': 18.0,
    # 생활용품
    'household': 12.0,
    'furniture': 10.8,
    # 펫
    'pet': 12.0,
    # 여행/레저
    'travel': 20.0,
    # 기타 (기본값)
    'default': 10.8,
}

# 쿠팡 정산수수료 (%)
COUPANG_SETTLEMENT_FEE = 0.0  # 별도 정산수수료 없음 (판매수수료에 포함)

# 쿠팡 추가 수수료 항목
COUPANG_ADDITIONAL_FEES: Dict[str, float] = {
    'rocket_delivery': 3.0,   # 로켓배송 이용 시 추가
    'free_delivery': 0.0,
}

# 네이버 스마트스토어 카테고리별 판매수수료율 (%)
# 출처: 네이버 스마트스토어 파트너 센터 기준
NAVER_FEE_RATES: Dict[str, float] = {
    # 패션/의류
    'fashion': 6.0,
    'clothing': 6.0,
    'shoes': 6.0,
    'bags': 6.0,
    'accessories': 6.0,
    # 뷰티/건강
    'beauty': 6.0,
    'health': 6.0,
    'cosmetics': 6.0,
    # 전자/디지털
    'electronics': 2.0,
    'digital': 2.0,
    'mobile': 2.0,
    'computer': 2.0,
    'camera': 2.0,
    # 가전
    'appliance': 2.0,
    'kitchen': 5.0,
    # 스포츠/아웃도어
    'sports': 6.0,
    'outdoor': 6.0,
    # 자동차
    'automotive': 6.0,
    # 완구/유아
    'toys': 6.0,
    'baby': 6.0,
    # 도서/음반
    'books': 8.0,
    'music': 8.0,
    # 식품/음료
    'food': 6.0,
    'beverage': 6.0,
    # 생활용품
    'household': 6.0,
    'furniture': 5.0,
    # 펫
    'pet': 6.0,
    # 기타 (기본값)
    'default': 6.0,
}

# 네이버페이 결제수수료 (%)
NAVER_PAY_FEE = 3.74

# 네이버 스마트스토어 기타 비용
NAVER_ADDITIONAL_FEES: Dict[str, float] = {
    'standard': 0.0,
    'naver_plus': 0.5,  # 네이버플러스 프로모션 참여 시
}


class FeeStructure:
    """마켓별 수수료 구조 관리 클래스."""

    PLATFORM_COUPANG = 'coupang'
    PLATFORM_NAVER = 'naver'

    def __init__(self):
        """초기화."""
        pass

    def get_total_fee_rate(
        self,
        platform: str,
        category: str = 'default',
        options: dict = None,
    ) -> float:
        """총 수수료율 계산 (%).

        Args:
            platform: 마켓 플랫폼 ('coupang' 또는 'naver')
            category: 상품 카테고리 (기본: 'default')
            options: 추가 옵션 딕셔너리

        Returns:
            총 수수료율 (%)
        """
        options = options or {}
        if platform == self.PLATFORM_COUPANG:
            return self._get_coupang_fee(category, options)
        if platform == self.PLATFORM_NAVER:
            return self._get_naver_fee(category, options)
        raise ValueError(f"지원하지 않는 플랫폼: {platform}")

    def get_sale_fee_rate(self, platform: str, category: str = 'default') -> float:
        """판매 수수료율만 반환 (%).

        Args:
            platform: 마켓 플랫폼
            category: 상품 카테고리

        Returns:
            판매 수수료율 (%)
        """
        if platform == self.PLATFORM_COUPANG:
            return COUPANG_FEE_RATES.get(category.lower(), COUPANG_FEE_RATES['default'])
        if platform == self.PLATFORM_NAVER:
            return NAVER_FEE_RATES.get(category.lower(), NAVER_FEE_RATES['default'])
        raise ValueError(f"지원하지 않는 플랫폼: {platform}")

    def get_fee_breakdown(
        self,
        platform: str,
        sale_price: float,
        category: str = 'default',
        options: dict = None,
    ) -> dict:
        """수수료 항목별 금액 반환.

        Args:
            platform: 마켓 플랫폼
            sale_price: 판매가 (KRW)
            category: 상품 카테고리
            options: 추가 옵션 딕셔너리

        Returns:
            {
                'sale_fee_rate': 판매수수료율,
                'sale_fee': 판매수수료 금액,
                'payment_fee_rate': 결제수수료율,
                'payment_fee': 결제수수료 금액,
                'total_fee_rate': 총수수료율,
                'total_fee': 총수수료 금액,
            }
        """
        options = options or {}
        if platform == self.PLATFORM_COUPANG:
            sale_fee_rate = COUPANG_FEE_RATES.get(category.lower(), COUPANG_FEE_RATES['default'])
            if options.get('rocket_delivery'):
                sale_fee_rate += COUPANG_ADDITIONAL_FEES['rocket_delivery']
            total_fee_rate = sale_fee_rate
            return {
                'sale_fee_rate': sale_fee_rate,
                'sale_fee': sale_price * sale_fee_rate / 100,
                'payment_fee_rate': 0.0,
                'payment_fee': 0.0,
                'total_fee_rate': total_fee_rate,
                'total_fee': sale_price * total_fee_rate / 100,
            }
        if platform == self.PLATFORM_NAVER:
            sale_fee_rate = NAVER_FEE_RATES.get(category.lower(), NAVER_FEE_RATES['default'])
            payment_fee_rate = NAVER_PAY_FEE
            total_fee_rate = sale_fee_rate + payment_fee_rate
            return {
                'sale_fee_rate': sale_fee_rate,
                'sale_fee': sale_price * sale_fee_rate / 100,
                'payment_fee_rate': payment_fee_rate,
                'payment_fee': sale_price * payment_fee_rate / 100,
                'total_fee_rate': total_fee_rate,
                'total_fee': sale_price * total_fee_rate / 100,
            }
        raise ValueError(f"지원하지 않는 플랫폼: {platform}")

    def list_categories(self, platform: str) -> list:
        """플랫폼별 지원 카테고리 목록 반환.

        Args:
            platform: 마켓 플랫폼

        Returns:
            카테고리 목록
        """
        if platform == self.PLATFORM_COUPANG:
            return sorted(COUPANG_FEE_RATES.keys())
        if platform == self.PLATFORM_NAVER:
            return sorted(NAVER_FEE_RATES.keys())
        raise ValueError(f"지원하지 않는 플랫폼: {platform}")

    # ── 내부 메서드 ──────────────────────────────────────────

    def _get_coupang_fee(self, category: str, options: dict) -> float:
        """쿠팡 총 수수료율 계산."""
        rate = COUPANG_FEE_RATES.get(category.lower(), COUPANG_FEE_RATES['default'])
        if options.get('rocket_delivery'):
            rate += COUPANG_ADDITIONAL_FEES['rocket_delivery']
        return rate

    def _get_naver_fee(self, category: str, options: dict) -> float:
        """네이버 총 수수료율 계산."""
        rate = NAVER_FEE_RATES.get(category.lower(), NAVER_FEE_RATES['default'])
        rate += NAVER_PAY_FEE
        if options.get('naver_plus'):
            rate += NAVER_ADDITIONAL_FEES['naver_plus']
        return rate
