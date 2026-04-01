"""지원 통화 목록 및 메타데이터."""

from typing import Dict, List

# 지원 통화 목록 (수입 구매대행 중심)
SUPPORTED_CURRENCIES: List[str] = [
    'KRW',  # 한국 원
    'USD',  # 미국 달러 (아마존 US)
    'JPY',  # 일본 엔 (아마존 JP, 라쿠텐, 조조타운)
    'CNY',  # 중국 위안 (타오바오, 1688, 알리익스프레스)
    'EUR',  # 유로 (아마존 DE/FR/IT/ES)
    'GBP',  # 영국 파운드 (아마존 UK)
    'CAD',  # 캐나다 달러 (아마존 CA)
    'MXN',  # 멕시코 페소 (아마존 MX)
    'AUD',  # 호주 달러
    'SGD',  # 싱가포르 달러
]

# 기본 환율 (KRW 기준 fallback)
DEFAULT_RATES_TO_KRW: Dict[str, float] = {
    'USD': 1350.0,
    'JPY': 9.0,
    'CNY': 186.0,
    'EUR': 1470.0,
    'GBP': 1710.0,
    'CAD': 990.0,
    'MXN': 70.0,
    'AUD': 880.0,
    'SGD': 1000.0,
    'KRW': 1.0,
}

# 마켓별 기본 통화 매핑
MARKETPLACE_CURRENCY: Dict[str, str] = {
    'amazon_us': 'USD',
    'amazon_jp': 'JPY',
    'amazon_de': 'EUR',
    'amazon_fr': 'EUR',
    'amazon_it': 'EUR',
    'amazon_es': 'EUR',
    'amazon_uk': 'GBP',
    'amazon_ca': 'CAD',
    'amazon_mx': 'MXN',
    'amazon_au': 'AUD',
    'taobao': 'CNY',
    'tmall': 'CNY',
    'aliexpress': 'CNY',
    '1688': 'CNY',
    'rakuten': 'JPY',
    'zozotown': 'JPY',
    'qoo10_sg': 'SGD',
    'coupang': 'KRW',
    'naver': 'KRW',
}

# 통화 표시 기호
CURRENCY_SYMBOLS: Dict[str, str] = {
    'KRW': '₩',
    'USD': '$',
    'JPY': '¥',
    'CNY': '¥',
    'EUR': '€',
    'GBP': '£',
    'CAD': 'CA$',
    'MXN': 'MX$',
    'AUD': 'A$',
    'SGD': 'S$',
}

# 통화 소수점 자리수
CURRENCY_DECIMALS: Dict[str, int] = {
    'KRW': 0,
    'USD': 2,
    'JPY': 0,
    'CNY': 2,
    'EUR': 2,
    'GBP': 2,
    'CAD': 2,
    'MXN': 2,
    'AUD': 2,
    'SGD': 2,
}


def get_currency_symbol(currency: str) -> str:
    """통화 기호 반환."""
    return CURRENCY_SYMBOLS.get(currency.upper(), currency)


def is_supported(currency: str) -> bool:
    """지원 통화 여부 확인."""
    return currency.upper() in SUPPORTED_CURRENCIES


def get_marketplace_currency(marketplace: str) -> str:
    """마켓플레이스의 기본 통화 반환."""
    return MARKETPLACE_CURRENCY.get(marketplace.lower(), 'USD')
