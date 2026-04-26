"""실시간 환율 조회 프로바이더."""

import logging
import os
from decimal import Decimal

import requests

logger = logging.getLogger(__name__)

# 기본 환율 (모두 KRW 기준) — src/price.py와 동기화
_DEFAULT_RATES = {
    'USDKRW': Decimal('1350'),
    'JPYKRW': Decimal('9.0'),
    'EURKRW': Decimal('1470'),
    'CNYKRW': Decimal('190'),
}

_REQUEST_TIMEOUT = 10


class FXProvider:
    """실시간 환율 조회 프로바이더.

    우선순위:
      1) primary_provider (또는 FX_PROVIDER 환경변수)
      2) 다음 프로바이더로 자동 폴백
      3) 모두 실패 시 환경변수(FX_USDKRW 등) / 기본값 반환
    """

    PROVIDER_EXCHANGERATE_API = 'exchangerate-api'
    PROVIDER_FRANKFURTER = 'frankfurter'
    PROVIDER_FALLBACK_ENV = 'env'

    SUPPORTED_PAIRS = ['USDKRW', 'JPYKRW', 'EURKRW', 'CNYKRW']

    def __init__(self, primary_provider: str = None):
        self._primary = (
            primary_provider
            or os.getenv('FX_PROVIDER', self.PROVIDER_FRANKFURTER)
        )

    # ── public API ───────────────────────────────────────────

    def get_rates(self) -> dict:
        """모든 지원 통화쌍의 현재 환율 조회.

        Returns:
            {
                'USDKRW': Decimal('1345.50'),
                'JPYKRW': Decimal('8.95'),
                'EURKRW': Decimal('1462.30'),
                'CNYKRW': Decimal('189.50'),
                'fetched_at': '2026-03-09T18:00:00+09:00',
                'provider': 'frankfurter',
            }
        실패 시 다음 프로바이더로 자동 폴백.
        모든 API 실패 시 환경변수 값(기본값) 반환.
        """
        ordered = self._provider_order()
        for provider in ordered:
            try:
                if provider == self.PROVIDER_FRANKFURTER:
                    return self._fetch_frankfurter()
                elif provider == self.PROVIDER_EXCHANGERATE_API:
                    return self._fetch_exchangerate_api()
                elif provider == self.PROVIDER_FALLBACK_ENV:
                    return self._fallback_env()
            except Exception as exc:
                logger.warning("FX provider '%s' failed: %s — trying next", provider, exc)
        # 최후 수단: 환경변수
        return self._fallback_env()

    def get_rate(self, pair: str) -> Decimal:
        """단일 통화쌍 환율 조회. pair: 'USDKRW' 등."""
        rates = self.get_rates()
        if pair not in rates:
            raise ValueError(f'지원하지 않는 통화쌍: {pair}')
        return Decimal(str(rates[pair]))

    # ── provider implementations ─────────────────────────────

    def _fetch_frankfurter(self) -> dict:
        """frankfurter.app API 호출 (ECB 기준, 완전 무료).

        CNY는 frankfurter에서 지원하지 않으므로 별도 소스 또는 환경변수 폴백.
        """
        from datetime import datetime, timezone

        pairs = {'USDKRW': ('USD', 'KRW'), 'JPYKRW': ('JPY', 'KRW'), 'EURKRW': ('EUR', 'KRW')}
        rates: dict = {}
        for pair, (from_cur, to_cur) in pairs.items():
            url = f'https://api.frankfurter.app/latest?from={from_cur}&to={to_cur}'
            resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            rate_val = data['rates'].get(to_cur)
            if rate_val is None:
                raise ValueError(f'frankfurter: {to_cur} not in response for {from_cur}')
            rates[pair] = Decimal(str(rate_val))

        # CNY: frankfurter는 CNY 미지원 → USD 기준 교차 환율 계산
        rates['CNYKRW'] = self._fetch_cny_rate(rates.get('USDKRW'))

        now = datetime.now(tz=timezone.utc).isoformat()
        rates['fetched_at'] = now
        rates['provider'] = self.PROVIDER_FRANKFURTER
        logger.info("FX rates fetched from frankfurter: %s", {k: str(v) for k, v in rates.items() if k in self.SUPPORTED_PAIRS})
        return rates

    def _fetch_cny_rate(self, usdkrw: Decimal = None) -> Decimal:
        """CNY/KRW 환율 조회.

        방법 1: frankfurter USD/CNY → USDKRW / USDCNY 교차환율
        방법 2: 환경변수 FX_CNYKRW 폴백
        """
        if usdkrw:
            try:
                url = 'https://api.frankfurter.app/latest?from=USD&to=CNY'
                resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
                usdcny = data['rates'].get('CNY')
                if usdcny and usdcny > 0:
                    cnykrw = usdkrw / Decimal(str(usdcny))
                    logger.info("CNY/KRW calculated via cross rate: %s", cnykrw)
                    return cnykrw.quantize(Decimal('0.01'))
            except Exception as exc:
                logger.warning("CNY cross rate calculation failed: %s", exc)

        # 폴백: 환경변수
        return Decimal(os.getenv('FX_CNYKRW', str(_DEFAULT_RATES['CNYKRW'])))

    def _fetch_exchangerate_api(self) -> dict:
        """exchangerate-api.com 호출 (무료 1500회/월).

        EXCHANGERATE_API_KEY 환경변수 필요.
        """
        from datetime import datetime, timezone

        api_key = os.getenv('EXCHANGERATE_API_KEY', '')
        if not api_key:
            raise ValueError('EXCHANGERATE_API_KEY not set')

        pairs = {
            'USDKRW': ('USD', 'KRW'),
            'JPYKRW': ('JPY', 'KRW'),
            'EURKRW': ('EUR', 'KRW'),
            'CNYKRW': ('CNY', 'KRW'),
        }
        rates: dict = {}
        for pair, (from_cur, to_cur) in pairs.items():
            url = f'https://v6.exchangerate-api.com/v6/{api_key}/pair/{from_cur}/{to_cur}'
            resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get('result') != 'success':
                raise ValueError(f'exchangerate-api error: {data.get("error-type")}')
            rate_val = data.get('conversion_rate')
            if rate_val is None:
                raise ValueError(f'exchangerate-api: conversion_rate missing for {pair}')
            rates[pair] = Decimal(str(rate_val))

        now = datetime.now(tz=timezone.utc).isoformat()
        rates['fetched_at'] = now
        rates['provider'] = self.PROVIDER_EXCHANGERATE_API
        logger.info("FX rates fetched from exchangerate-api: %s", {k: str(v) for k, v in rates.items() if k in self.SUPPORTED_PAIRS})
        return rates

    def _fallback_env(self) -> dict:
        """환경변수에서 환율 로드 (최후 수단)."""
        from datetime import datetime, timezone

        rates = {
            'USDKRW': Decimal(os.getenv('FX_USDKRW', str(_DEFAULT_RATES['USDKRW']))),
            'JPYKRW': Decimal(os.getenv('FX_JPYKRW', str(_DEFAULT_RATES['JPYKRW']))),
            'EURKRW': Decimal(os.getenv('FX_EURKRW', str(_DEFAULT_RATES['EURKRW']))),
            'CNYKRW': Decimal(os.getenv('FX_CNYKRW', str(_DEFAULT_RATES['CNYKRW']))),
            'fetched_at': datetime.now(tz=timezone.utc).isoformat(),
            'provider': self.PROVIDER_FALLBACK_ENV,
        }
        logger.info("FX rates loaded from env/defaults")
        return rates

    # ── helpers ──────────────────────────────────────────────

    def _provider_order(self) -> list:
        """primary 프로바이더를 앞에 두고 나머지를 뒤에 나열."""
        all_providers = [
            self.PROVIDER_FRANKFURTER,
            self.PROVIDER_EXCHANGERATE_API,
            self.PROVIDER_FALLBACK_ENV,
        ]
        ordered = [self._primary] + [p for p in all_providers if p != self._primary]
        return ordered
