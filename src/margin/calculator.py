"""마진 계산 엔진.

수입 구매대행 상품의 마진을 자동 계산합니다.

계산 공식:
    원가(KRW) = 해외가격 × 환율
    총비용 = 원가 + 국제배송비 + 통관비 + 국내배송비
    순수익 = 판매가 × (1 - 마켓수수료율/100) - 총비용
    마진율 = 순수익 / 판매가 × 100
"""

import logging
from typing import List

from .fee_structure import FeeStructure
from .shipping_cost import ShippingCost

logger = logging.getLogger(__name__)


class MarginCalculator:
    """마진 계산 엔진 클래스.

    수입 구매대행 상품의 원가, 수수료, 배송비를 계산하여 마진을 산출합니다.
    역계산(목표 마진율 → 최적 판매가)도 지원합니다.
    """

    def __init__(self, fx_service=None, krw_per_usd: float = 1350.0):
        """초기화.

        Args:
            fx_service: RealtimeRates 인스턴스 (None이면 기본 환율 사용)
            krw_per_usd: USD→KRW 환율 (fx_service 없을 때 사용, 기본 1350)
        """
        self._fx = fx_service
        self._fee_structure = FeeStructure()
        self._shipping = ShippingCost(krw_per_usd=krw_per_usd)
        self._default_krw_per_usd = krw_per_usd

    # ── public API ───────────────────────────────────────────

    def calculate(
        self,
        foreign_price: float,
        sale_price_krw: float,
        currency: str = 'USD',
        marketplace: str = 'amazon_us',
        platform: str = 'coupang',
        category: str = 'default',
        weight_kg: float = 0.5,
        platform_options: dict = None,
    ) -> dict:
        """마진 계산.

        Args:
            foreign_price: 해외 상품가격 (해당 통화)
            sale_price_krw: 국내 판매가 (KRW)
            currency: 해외 통화 코드 (USD, JPY, CNY 등)
            marketplace: 마켓플레이스 (amazon_us, taobao 등)
            platform: 판매 플랫폼 (coupang, naver)
            category: 상품 카테고리
            weight_kg: 상품 무게 (kg)
            platform_options: 플랫폼별 추가 옵션

        Returns:
            {
                'foreign_price': 해외가격,
                'currency': 통화코드,
                'exchange_rate': 적용 환율,
                'cost_krw': 원가(KRW),
                'international_shipping': 국제배송비(KRW),
                'customs_total': 통관비용(KRW),
                'domestic_shipping': 국내배송비(KRW),
                'total_cost': 총비용(KRW),
                'sale_price_krw': 판매가(KRW),
                'fee_rate': 수수료율(%),
                'fee_amount': 수수료 금액(KRW),
                'net_revenue': 순수익(KRW),
                'margin_rate': 마진율(%),
                'is_profitable': 수익성 여부,
            }
        """
        platform_options = platform_options or {}

        # 1. 환율 적용 → 원가(KRW)
        exchange_rate = self._get_exchange_rate(currency)
        cost_krw = float(foreign_price) * float(exchange_rate)

        # 2. 배송/통관비 계산
        # 해외가격을 USD로 환산 (통관비 계산용)
        price_in_usd = self._to_usd(foreign_price, currency, exchange_rate)
        shipping_result = self._shipping.calculate_total_shipping(
            weight_kg=weight_kg,
            product_price_usd=price_in_usd,
            marketplace=marketplace,
            sale_price_krw=sale_price_krw,
        )

        # 3. 수수료 계산
        fee_breakdown = self._fee_structure.get_fee_breakdown(
            platform=platform,
            sale_price=sale_price_krw,
            category=category,
            options=platform_options,
        )

        # 4. 마진 계산
        total_cost = cost_krw + shipping_result['total']
        net_revenue = sale_price_krw * (1 - fee_breakdown['total_fee_rate'] / 100) - total_cost
        margin_rate = (net_revenue / sale_price_krw * 100) if sale_price_krw > 0 else 0.0

        return {
            'foreign_price': foreign_price,
            'currency': currency,
            'exchange_rate': float(exchange_rate),
            'cost_krw': cost_krw,
            'international_shipping': shipping_result['international_shipping'],
            'customs_total': shipping_result['customs']['total'],
            'domestic_shipping': shipping_result['domestic_shipping'],
            'total_cost': total_cost,
            'sale_price_krw': sale_price_krw,
            'fee_rate': fee_breakdown['total_fee_rate'],
            'fee_amount': fee_breakdown['total_fee'],
            'net_revenue': net_revenue,
            'margin_rate': margin_rate,
            'is_profitable': net_revenue > 0,
        }

    def reverse_calculate(
        self,
        foreign_price: float,
        target_margin_rate: float,
        currency: str = 'USD',
        marketplace: str = 'amazon_us',
        platform: str = 'coupang',
        category: str = 'default',
        weight_kg: float = 0.5,
        platform_options: dict = None,
    ) -> dict:
        """역계산: 목표 마진율에서 최적 판매가 산출.

        목표 마진율을 달성하기 위한 최소 판매가를 계산합니다.

        공식:
            판매가 = 총비용 / (1 - 수수료율/100 - 마진율/100)

        Args:
            foreign_price: 해외 상품가격 (해당 통화)
            target_margin_rate: 목표 마진율 (%)
            currency: 해외 통화 코드
            marketplace: 마켓플레이스
            platform: 판매 플랫폼
            category: 상품 카테고리
            weight_kg: 상품 무게 (kg)
            platform_options: 플랫폼별 추가 옵션

        Returns:
            {
                'target_margin_rate': 목표 마진율,
                'optimal_sale_price': 최적 판매가(KRW),
                'rounded_sale_price': 반올림된 판매가(KRW, 100원 단위),
                'cost_krw': 원가(KRW),
                'total_cost': 총비용(KRW),
                'fee_rate': 수수료율(%),
                'actual_margin_rate': 실제 마진율(%),
            }
        """
        platform_options = platform_options or {}

        exchange_rate = self._get_exchange_rate(currency)
        cost_krw = float(foreign_price) * float(exchange_rate)

        # 임시 판매가로 배송비 추정
        estimated_sale_price = cost_krw * 2.0  # 원가의 2배로 초기 추정
        price_in_usd = self._to_usd(foreign_price, currency, exchange_rate)
        shipping_result = self._shipping.calculate_total_shipping(
            weight_kg=weight_kg,
            product_price_usd=price_in_usd,
            marketplace=marketplace,
            sale_price_krw=estimated_sale_price,
        )
        total_cost = cost_krw + shipping_result['total']

        fee_rate = self._fee_structure.get_total_fee_rate(platform, category, platform_options)

        # 역계산 공식
        # net_revenue = sale_price × (1 - fee_rate/100) - total_cost
        # margin_rate = net_revenue / sale_price × 100
        # target_margin_rate/100 = (sale_price × (1 - fee_rate/100) - total_cost) / sale_price
        # sale_price × target_margin_rate/100 = sale_price × (1 - fee_rate/100) - total_cost
        # total_cost = sale_price × (1 - fee_rate/100 - target_margin_rate/100)
        # sale_price = total_cost / (1 - fee_rate/100 - target_margin_rate/100)
        denominator = 1 - (fee_rate / 100) - (target_margin_rate / 100)
        if denominator <= 0:
            raise ValueError(f"목표 마진율({target_margin_rate}%)과 수수료율({fee_rate}%)의 합이 100%를 초과합니다")

        optimal_sale_price = total_cost / denominator
        # 100원 단위 반올림 (올림)
        rounded_sale_price = int((optimal_sale_price + 99) // 100) * 100

        # 실제 마진율 검증
        actual_result = self.calculate(
            foreign_price=foreign_price,
            sale_price_krw=rounded_sale_price,
            currency=currency,
            marketplace=marketplace,
            platform=platform,
            category=category,
            weight_kg=weight_kg,
            platform_options=platform_options,
        )

        return {
            'target_margin_rate': target_margin_rate,
            'optimal_sale_price': optimal_sale_price,
            'rounded_sale_price': rounded_sale_price,
            'cost_krw': cost_krw,
            'total_cost': total_cost,
            'fee_rate': fee_rate,
            'actual_margin_rate': actual_result['margin_rate'],
        }

    def bulk_calculate(self, products: List[dict]) -> List[dict]:
        """다수 상품 일괄 마진 계산.

        Args:
            products: 상품 목록. 각 딕셔너리는 calculate()의 파라미터 포함.

        Returns:
            마진 계산 결과 목록
        """
        results = []
        for i, product in enumerate(products):
            try:
                result = self.calculate(**product)
                result['product_index'] = i
                result['success'] = True
                results.append(result)
            except Exception as exc:
                logger.warning("마진 계산 실패 (index=%d): %s", i, exc)
                results.append({
                    'product_index': i,
                    'success': False,
                    'error': str(exc),
                })
        return results

    def generate_report(self, products: List[dict]) -> dict:
        """마진 계산 리포트 생성.

        Args:
            products: 상품 목록

        Returns:
            {
                'total_products': 총 상품 수,
                'profitable_count': 수익 상품 수,
                'avg_margin_rate': 평균 마진율,
                'max_margin_rate': 최대 마진율,
                'min_margin_rate': 최소 마진율,
                'results': 상세 결과 목록,
            }
        """
        results = self.bulk_calculate(products)
        successful = [r for r in results if r.get('success')]
        margin_rates = [r['margin_rate'] for r in successful]
        profitable = [r for r in successful if r.get('is_profitable')]

        return {
            'total_products': len(products),
            'successful_count': len(successful),
            'profitable_count': len(profitable),
            'avg_margin_rate': sum(margin_rates) / len(margin_rates) if margin_rates else 0.0,
            'max_margin_rate': max(margin_rates) if margin_rates else 0.0,
            'min_margin_rate': min(margin_rates) if margin_rates else 0.0,
            'results': results,
        }

    # ── 내부 메서드 ──────────────────────────────────────────

    def _get_exchange_rate(self, currency: str) -> float:
        """통화별 환율 조회 (KRW 기준).

        Args:
            currency: 통화 코드

        Returns:
            환율 (float)
        """
        if currency == 'KRW':
            return 1.0
        if self._fx is not None:
            try:
                rate = self._fx.get_rate(currency, 'KRW')
                return float(rate)
            except Exception as exc:
                logger.warning("환율 조회 실패 (%s): %s — 기본값 사용", currency, exc)

        # fallback: 기본값
        from ..fx.supported_currencies import DEFAULT_RATES_TO_KRW
        return DEFAULT_RATES_TO_KRW.get(currency, self._default_krw_per_usd)

    def _to_usd(self, amount: float, currency: str, exchange_rate: float) -> float:
        """금액을 USD로 환산 (통관비 계산용).

        Args:
            amount: 금액
            currency: 통화 코드
            exchange_rate: KRW 환율

        Returns:
            USD 금액
        """
        if currency == 'USD':
            return amount
        if currency == 'KRW':
            return amount / self._default_krw_per_usd
        # 먼저 KRW로 변환 후 USD로
        krw_amount = amount * exchange_rate
        krw_per_usd = self._get_exchange_rate('USD')
        if krw_per_usd == 0:
            return 0.0
        return krw_amount / krw_per_usd
