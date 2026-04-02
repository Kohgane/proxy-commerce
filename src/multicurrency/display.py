"""src/multicurrency/display.py — Phase 45: 통화별 표시 형식."""
import logging
from typing import Dict

logger = logging.getLogger(__name__)

DISPLAY_FORMATS: Dict[str, dict] = {
    'KRW': {'symbol': '₩', 'decimals': 0, 'symbol_before': True, 'thousands_sep': ','},
    'USD': {'symbol': '$', 'decimals': 2, 'symbol_before': True, 'thousands_sep': ','},
    'JPY': {'symbol': '¥', 'decimals': 0, 'symbol_before': True, 'thousands_sep': ','},
    'CNY': {'symbol': '¥', 'decimals': 2, 'symbol_before': True, 'thousands_sep': ','},
    'EUR': {'symbol': '€', 'decimals': 2, 'symbol_before': True, 'thousands_sep': ','},
}


class CurrencyDisplay:
    """통화별 포맷팅.

    Examples:
        KRW 12300  → ₩12,300
        USD 12.30  → $12.30
        JPY 1230   → ¥1,230
    """

    def format(self, amount: float, currency_code: str) -> str:
        """통화 포맷팅."""
        currency_code = currency_code.upper()
        fmt = DISPLAY_FORMATS.get(currency_code, {
            'symbol': currency_code,
            'decimals': 2,
            'symbol_before': True,
            'thousands_sep': ',',
        })
        decimals = fmt['decimals']
        formatted_number = f"{amount:,.{decimals}f}" if fmt['thousands_sep'] == ',' else f"{amount:.{decimals}f}"
        symbol = fmt['symbol']
        if fmt['symbol_before']:
            return f"{symbol}{formatted_number}"
        return f"{formatted_number}{symbol}"

    def parse(self, formatted: str, currency_code: str) -> float:
        """포맷된 문자열에서 숫자 추출."""
        currency_code = currency_code.upper()
        fmt = DISPLAY_FORMATS.get(currency_code, {'symbol': currency_code})
        cleaned = formatted.replace(fmt['symbol'], '').replace(',', '').strip()
        return float(cleaned)
