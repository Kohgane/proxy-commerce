"""국가별 배송비/리드타임 추정기."""
import math
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class ShippingEstimate:
    """배송 견적."""

    country_code: str
    method: str              # 'EMS', 'K-Packet', 'registered_mail'
    cost_krw: Decimal        # 배송비 (KRW)
    delivery_days_min: int   # 최소 소요일
    delivery_days_max: int   # 최대 소요일
    weight_kg: Decimal       # 기준 중량
    tracking: bool           # 추적 가능 여부


class ShippingEstimator:
    """국가별 배송비/리드타임 추정기.

    실제 API 연동 전까지는 우체국 국제우편 + EMS + K-Packet 기준 테이블 사용.
    """

    # 지역별 배송비 테이블 (KRW, 0.5kg 기준)
    ZONE_RATES = {
        # zone: {method: cost_krw}
        'asia_near': {  # JP, CN, TW, HK
            'ems': Decimal('18000'),
            'k_packet': Decimal('8000'),
            'registered': Decimal('5500'),
        },
        'asia_far': {  # TH, VN, ID, PH, SG, MY
            'ems': Decimal('22000'),
            'k_packet': Decimal('10000'),
            'registered': Decimal('6500'),
        },
        'americas': {  # US, CA
            'ems': Decimal('28000'),
            'k_packet': Decimal('13000'),
            'registered': Decimal('8000'),
        },
        'europe': {  # GB, PL, FR, DE
            'ems': Decimal('28000'),
            'k_packet': Decimal('13000'),
            'registered': Decimal('8000'),
        },
        'middle_east': {  # AE, SA
            'ems': Decimal('25000'),
            'k_packet': Decimal('11000'),
            'registered': Decimal('7000'),
        },
    }

    COUNTRY_ZONE = {
        'JP': 'asia_near', 'CN': 'asia_near',
        'TH': 'asia_far', 'VN': 'asia_far', 'ID': 'asia_far',
        'PH': 'asia_far', 'SG': 'asia_far', 'MY': 'asia_far',
        'US': 'americas',
        'GB': 'europe', 'PL': 'europe',
        'AE': 'middle_east', 'SA': 'middle_east',
    }

    DELIVERY_DAYS = {
        # zone: {method: (min, max)}
        'asia_near': {'ems': (2, 4), 'k_packet': (5, 10), 'registered': (7, 14)},
        'asia_far': {'ems': (3, 5), 'k_packet': (7, 14), 'registered': (10, 21)},
        'americas': {'ems': (5, 8), 'k_packet': (10, 18), 'registered': (14, 28)},
        'europe': {'ems': (5, 8), 'k_packet': (10, 18), 'registered': (14, 28)},
        'middle_east': {'ems': (5, 10), 'k_packet': (10, 20), 'registered': (14, 30)},
    }

    # 방법 코드 → 사람이 읽을 수 있는 이름 + 추적 가능 여부
    _METHOD_META = {
        'ems': ('EMS', True),
        'k_packet': ('K-Packet', True),
        'registered': ('registered_mail', True),
    }

    # 기준 중량 (kg) — 이 단위로 요금 구간이 나뉜다
    _BASE_WEIGHT_KG = Decimal('0.5')

    def _get_zone(self, country_code: str) -> str:
        code = country_code.upper().strip()
        if code not in self.COUNTRY_ZONE:
            raise ValueError(f'지원하지 않는 국가: {country_code}')
        return self.COUNTRY_ZONE[code]

    def _weight_multiplier(self, weight_kg: Decimal) -> int:
        """0.5kg 단위로 올림한 요금 배수 (최소 1)."""
        return max(1, math.ceil(float(weight_kg) / float(self._BASE_WEIGHT_KG)))

    def estimate(self, country_code: str, weight_kg: Decimal = Decimal('0.5'),
                 method: str = None) -> list[ShippingEstimate]:
        """국가/중량 기준 배송 견적 리스트 반환.

        Args:
            country_code: ISO alpha-2
            weight_kg: 상품 중량 (kg)
            method: 특정 방법만 ('ems', 'k_packet', 'registered'). None이면 전체.

        Returns:
            ShippingEstimate 리스트 (가격 오름차순)
        """
        zone = self._get_zone(country_code)
        rates = self.ZONE_RATES[zone]
        days = self.DELIVERY_DAYS[zone]
        multiplier = self._weight_multiplier(Decimal(str(weight_kg)))

        methods = [method.lower()] if method else list(rates.keys())
        estimates = []
        for m in methods:
            if m not in rates:
                raise ValueError(f'지원하지 않는 배송 방법: {m}')
            display_name, has_tracking = self._METHOD_META[m]
            cost = rates[m] * multiplier
            d_min, d_max = days[m]
            estimates.append(ShippingEstimate(
                country_code=country_code.upper(),
                method=display_name,
                cost_krw=cost,
                delivery_days_min=d_min,
                delivery_days_max=d_max,
                weight_kg=Decimal(str(weight_kg)),
                tracking=has_tracking,
            ))

        return sorted(estimates, key=lambda e: e.cost_krw)

    def cheapest(self, country_code: str, weight_kg: Decimal = Decimal('0.5')) -> ShippingEstimate:
        """가장 저렴한 배송 옵션."""
        return self.estimate(country_code, weight_kg)[0]

    def fastest(self, country_code: str, weight_kg: Decimal = Decimal('0.5')) -> ShippingEstimate:
        """가장 빠른 배송 옵션 (최소 소요일 기준)."""
        estimates = self.estimate(country_code, weight_kg)
        return min(estimates, key=lambda e: (e.delivery_days_min, e.delivery_days_max))
