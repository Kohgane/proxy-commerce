"""마켓별 수수료/배송비/배대지비 테이블.

환경변수 오버라이드: MARKET_FEE_{MARKET}_{CAT}, SHIPPING_{COUNTRY}_{METHOD} 등.
"""

import os
from decimal import Decimal


MARKET_FEES: dict[str, dict] = {
    'coupang': {
        'default': Decimal('10.8'),
        'fashion': Decimal('10.8'),
        'electronics': Decimal('10.8'),
        'beauty': Decimal('10.8'),
        'food': Decimal('10.8'),
    },
    'smartstore': {
        'default': Decimal('5.5'),
        'fashion': Decimal('5.5'),
        'electronics': Decimal('5.5'),
        'beauty': Decimal('5.5'),
        'food': Decimal('5.5'),
    },
    'elevenst': {
        'default': Decimal('13'),
        'fashion': Decimal('13'),
        'electronics': Decimal('13'),
    },
    'gmarket': {
        'default': Decimal('12'),
    },
    'auction': {
        'default': Decimal('12'),
    },
    'lotteon': {
        'default': Decimal('10'),
    },
    'talkstore': {
        'default': Decimal('5'),
    },
}

SHIPPING_COSTS: dict[str, dict] = {
    'US': {
        'standard': Decimal('15000'),
        'express': Decimal('25000'),
        'economy': Decimal('10000'),
    },
    'JP': {
        'standard': Decimal('8000'),
        'express': Decimal('15000'),
        'economy': Decimal('5000'),
    },
    'CN': {
        'standard': Decimal('6000'),
        'express': Decimal('12000'),
        'economy': Decimal('4000'),
    },
    'DE': {
        'standard': Decimal('18000'),
        'express': Decimal('30000'),
    },
    'UK': {
        'standard': Decimal('18000'),
        'express': Decimal('30000'),
    },
}

FORWARDER_FEES: dict[str, Decimal] = {
    'US': Decimal('5000'),
    'JP': Decimal('2700'),
    'CN': Decimal('3000'),
    'DE': Decimal('6000'),
    'UK': Decimal('6000'),
}

CUSTOMS_THRESHOLDS: dict[str, dict] = {
    'US': {'threshold_usd': Decimal('200'), 'rate': Decimal('0')},
    'JP': {'threshold_usd': Decimal('150'), 'rate': Decimal('0.20')},
    'CN': {'threshold_usd': Decimal('150'), 'rate': Decimal('0.20')},
    'DE': {'threshold_usd': Decimal('150'), 'rate': Decimal('0.20')},
    'UK': {'threshold_usd': Decimal('150'), 'rate': Decimal('0.20')},
}


def get_commission_rate(market: str, category: str = 'default') -> Decimal:
    env_key = f'MARKET_FEE_{market.upper()}_{category.upper()}'
    env_val = os.getenv(env_key)
    if env_val:
        return Decimal(env_val)
    fees = MARKET_FEES.get(market, {})
    return fees.get(category, fees.get('default', Decimal('10')))


def get_shipping_cost(country: str, method: str = 'standard') -> Decimal:
    env_key = f'SHIPPING_{country.upper()}_{method.upper()}'
    env_val = os.getenv(env_key)
    if env_val:
        return Decimal(env_val)
    costs = SHIPPING_COSTS.get(country, {})
    return costs.get(method, costs.get('standard', Decimal('15000')))


def get_forwarder_fee(country: str) -> Decimal:
    env_key = f'FORWARDER_FEE_{country.upper()}'
    env_val = os.getenv(env_key)
    if env_val:
        return Decimal(env_val)
    return FORWARDER_FEES.get(country, Decimal('5000'))
