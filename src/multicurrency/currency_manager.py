"""src/multicurrency/currency_manager.py — Phase 45: 지원 통화 관리."""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CURRENCIES = {
    'KRW': {'name': '대한민국 원', 'symbol': '₩', 'decimals': 0},
    'USD': {'name': '미국 달러', 'symbol': '$', 'decimals': 2},
    'JPY': {'name': '일본 엔', 'symbol': '¥', 'decimals': 0},
    'CNY': {'name': '중국 위안', 'symbol': '¥', 'decimals': 2},
    'EUR': {'name': '유로', 'symbol': '€', 'decimals': 2},
}


class CurrencyManager:
    """지원 통화 등록/조회, 기본 통화 설정."""

    def __init__(self, base_currency: str = 'KRW'):
        self._currencies: Dict[str, dict] = {}
        self._base_currency = base_currency
        for code, info in DEFAULT_CURRENCIES.items():
            self.register(code, **info)

    def register(self, code: str, name: str = '', symbol: str = '',
                 decimals: int = 2) -> dict:
        """통화 등록."""
        code = code.upper()
        currency = {
            'code': code,
            'name': name or code,
            'symbol': symbol or code,
            'decimals': decimals,
            'active': True,
        }
        self._currencies[code] = currency
        return currency

    def get(self, code: str) -> Optional[dict]:
        return self._currencies.get(code.upper())

    def list_all(self, active_only: bool = False) -> List[dict]:
        currencies = list(self._currencies.values())
        if active_only:
            currencies = [c for c in currencies if c['active']]
        return currencies

    def set_base_currency(self, code: str):
        code = code.upper()
        if code not in self._currencies:
            raise ValueError(f"등록되지 않은 통화: {code}")
        self._base_currency = code

    @property
    def base_currency(self) -> str:
        return self._base_currency

    def deactivate(self, code: str) -> bool:
        currency = self._currencies.get(code.upper())
        if currency is None:
            return False
        currency['active'] = False
        return True
