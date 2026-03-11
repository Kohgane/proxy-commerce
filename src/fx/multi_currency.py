"""다통화 환율 지원 확장.

기존 fx/cache.py는 USDKRW, JPYKRW, EURKRW만 지원.
이 모듈은 shipping/country_config.py의 13개국 통화를 모두 지원:
THB, VND, IDR, PHP, AED, SAR, SGD, MYR, PLN, CNY, GBP + 기존 USD, JPY, EUR
"""
from decimal import Decimal

from ..shipping import SUPPORTED_COUNTRIES, get_country

# 13개국 통화별 기본 환율 (KRW 기준, 2026-03 기준 근사치)
DEFAULT_MULTI_FX_RATES = {
    'USDKRW': Decimal('1350'),
    'JPYKRW': Decimal('9.0'),
    'EURKRW': Decimal('1470'),
    'GBPKRW': Decimal('1710'),
    'THBKRW': Decimal('38'),
    'VNDKRW': Decimal('0.054'),
    'IDRKRW': Decimal('0.085'),
    'PHPKRW': Decimal('24'),
    'AEDKRW': Decimal('368'),
    'SARKRW': Decimal('360'),
    'SGDKRW': Decimal('1005'),
    'MYRKRW': Decimal('305'),
    'PLNKRW': Decimal('340'),
    'CNYKRW': Decimal('186'),
}


class MultiCurrencyConverter:
    """다통화 환율 변환기."""

    def __init__(self, fx_rates: dict = None):
        self.fx_rates = {**DEFAULT_MULTI_FX_RATES, **(fx_rates or {})}

    # ── 핵심 변환 메서드 ──────────────────────────────────────────────────────

    def convert(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal:
        """KRW 피벗 방식으로 모든 통화 쌍 변환.

        Args:
            amount: 변환할 금액
            from_currency: 원본 통화 (ISO 4217)
            to_currency: 목적 통화 (ISO 4217)

        Returns:
            변환된 금액 (Decimal)
        """
        amount = Decimal(str(amount))
        from_currency = from_currency.upper().strip()
        to_currency = to_currency.upper().strip()

        if from_currency == to_currency:
            return amount

        # from_currency → KRW
        amount_krw = self.to_krw(amount, from_currency) if from_currency != 'KRW' else amount

        # KRW → to_currency
        if to_currency == 'KRW':
            return amount_krw
        return self.from_krw(amount_krw, to_currency)

    def to_krw(self, amount: Decimal, currency: str) -> Decimal:
        """외화 → KRW.

        Args:
            amount: 변환할 금액
            currency: 원본 통화 (ISO 4217)

        Returns:
            KRW 환산 금액
        """
        amount = Decimal(str(amount))
        currency = currency.upper().strip()
        if currency == 'KRW':
            return amount
        rate = self.get_rate(currency)
        return amount * rate

    def from_krw(self, amount_krw: Decimal, currency: str) -> Decimal:
        """KRW → 외화.

        Args:
            amount_krw: KRW 금액
            currency: 목적 통화 (ISO 4217)

        Returns:
            외화 환산 금액
        """
        amount_krw = Decimal(str(amount_krw))
        currency = currency.upper().strip()
        if currency == 'KRW':
            return amount_krw
        rate = self.get_rate(currency)
        return amount_krw / rate

    def get_rate(self, currency: str) -> Decimal:
        """특정 통화의 KRW 환율 조회.

        Args:
            currency: ISO 4217 통화 코드 (예: 'USD', 'JPY')

        Returns:
            1 단위 외화 = ? KRW

        Raises:
            ValueError: 지원하지 않는 통화
        """
        currency = currency.upper().strip()
        if currency == 'KRW':
            return Decimal('1')
        key = f'{currency}KRW'
        if key not in self.fx_rates:
            raise ValueError(f'지원하지 않는 통화: {currency}. 지원 통화: {self.get_supported_currencies()}')
        return Decimal(str(self.fx_rates[key]))

    def get_supported_currencies(self) -> list:
        """지원 통화 리스트.

        Returns:
            ISO 4217 통화 코드 리스트 (KRW 포함)
        """
        currencies = ['KRW']
        for key in self.fx_rates:
            if key.endswith('KRW') and len(key) == 6:
                currencies.append(key[:3])
        return sorted(currencies)

    def get_country_currencies(self) -> dict:
        """13개국 국가코드 → 통화 매핑.

        Returns:
            {'US': 'USD', 'GB': 'GBP', ...}
        """
        return {code: get_country(code).currency for code in SUPPORTED_COUNTRIES}
