"""tests/test_realtime_fx.py — 실시간 환율 서비스 단위 테스트."""

import os
import sys
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ──────────────────────────────────────────────────────────
# RateCache
# ──────────────────────────────────────────────────────────

class TestRateCache:
    """TTL 기반 환율 캐시 테스트."""

    def test_set_and_get(self):
        """저장 후 조회."""
        from src.fx.rate_cache import RateCache
        cache = RateCache(ttl_seconds=60)
        cache.set('USD', 'KRW', Decimal('1350'))
        assert cache.get('USD', 'KRW') == Decimal('1350')

    def test_get_missing_returns_none(self):
        """캐시 미스 시 None 반환."""
        from src.fx.rate_cache import RateCache
        cache = RateCache(ttl_seconds=60)
        assert cache.get('USD', 'KRW') is None

    def test_ttl_expiry(self):
        """TTL 만료 시 None 반환."""
        from src.fx.rate_cache import RateCache
        cache = RateCache(ttl_seconds=1)
        cache.set('USD', 'KRW', Decimal('1350'))
        assert cache.get('USD', 'KRW') == Decimal('1350')
        time.sleep(1.1)
        assert cache.get('USD', 'KRW') is None

    def test_is_valid_true(self):
        """유효한 캐시."""
        from src.fx.rate_cache import RateCache
        cache = RateCache(ttl_seconds=60)
        cache.set('USD', 'KRW', Decimal('1350'))
        assert cache.is_valid('USD', 'KRW') is True

    def test_is_valid_false_missing(self):
        """캐시 없을 때 False."""
        from src.fx.rate_cache import RateCache
        cache = RateCache(ttl_seconds=60)
        assert cache.is_valid('USD', 'KRW') is False

    def test_invalidate_specific(self):
        """특정 통화쌍 무효화."""
        from src.fx.rate_cache import RateCache
        cache = RateCache(ttl_seconds=60)
        cache.set('USD', 'KRW', Decimal('1350'))
        cache.set('JPY', 'KRW', Decimal('9.0'))
        cache.invalidate('USD', 'KRW')
        assert cache.get('USD', 'KRW') is None
        assert cache.get('JPY', 'KRW') == Decimal('9.0')

    def test_invalidate_all(self):
        """전체 캐시 무효화."""
        from src.fx.rate_cache import RateCache
        cache = RateCache(ttl_seconds=60)
        cache.set('USD', 'KRW', Decimal('1350'))
        cache.set('JPY', 'KRW', Decimal('9.0'))
        cache.invalidate()
        assert cache.get('USD', 'KRW') is None
        assert cache.get('JPY', 'KRW') is None

    def test_ttl_remaining_positive(self):
        """유효한 캐시의 남은 TTL > 0."""
        from src.fx.rate_cache import RateCache
        cache = RateCache(ttl_seconds=60)
        cache.set('USD', 'KRW', Decimal('1350'))
        remaining = cache.ttl_remaining('USD', 'KRW')
        assert 0 < remaining <= 60

    def test_ttl_remaining_zero_for_missing(self):
        """캐시 없을 때 TTL = 0."""
        from src.fx.rate_cache import RateCache
        cache = RateCache(ttl_seconds=60)
        assert cache.ttl_remaining('USD', 'KRW') == 0.0

    def test_size_empty(self):
        """빈 캐시의 크기 = 0."""
        from src.fx.rate_cache import RateCache
        cache = RateCache(ttl_seconds=60)
        assert cache.size() == 0

    def test_size_with_entries(self):
        """항목 추가 후 크기 확인."""
        from src.fx.rate_cache import RateCache
        cache = RateCache(ttl_seconds=60)
        cache.set('USD', 'KRW', Decimal('1350'))
        cache.set('JPY', 'KRW', Decimal('9.0'))
        assert cache.size() == 2

    def test_make_key_format(self):
        """캐시 키 형식 확인."""
        from src.fx.rate_cache import RateCache
        assert RateCache._make_key('usd', 'krw') == 'USD_KRW'
        assert RateCache._make_key('JPY', 'KRW') == 'JPY_KRW'

    def test_ttl_from_env(self, monkeypatch):
        """환경변수에서 TTL 로드."""
        monkeypatch.setenv('FX_CACHE_TTL_SECONDS', '120')
        from src.fx.rate_cache import RateCache
        cache = RateCache()
        assert cache._ttl == 120

    def test_overwrite_existing(self):
        """기존 캐시 덮어쓰기."""
        from src.fx.rate_cache import RateCache
        cache = RateCache(ttl_seconds=60)
        cache.set('USD', 'KRW', Decimal('1350'))
        cache.set('USD', 'KRW', Decimal('1400'))
        assert cache.get('USD', 'KRW') == Decimal('1400')


# ──────────────────────────────────────────────────────────
# SupportedCurrencies
# ──────────────────────────────────────────────────────────

class TestSupportedCurrencies:
    """지원 통화 목록 테스트."""

    def test_supported_currencies_contains_key_currencies(self):
        """핵심 통화 포함 여부."""
        from src.fx.supported_currencies import SUPPORTED_CURRENCIES
        for currency in ['KRW', 'USD', 'JPY', 'CNY', 'EUR', 'GBP', 'CAD', 'MXN']:
            assert currency in SUPPORTED_CURRENCIES

    def test_default_rates_has_usd(self):
        """기본 환율에 USD 포함."""
        from src.fx.supported_currencies import DEFAULT_RATES_TO_KRW
        assert 'USD' in DEFAULT_RATES_TO_KRW
        assert DEFAULT_RATES_TO_KRW['USD'] > 0

    def test_get_currency_symbol(self):
        """통화 기호 반환."""
        from src.fx.supported_currencies import get_currency_symbol
        assert get_currency_symbol('USD') == '$'
        assert get_currency_symbol('KRW') == '₩'
        assert get_currency_symbol('JPY') == '¥'
        assert get_currency_symbol('EUR') == '€'

    def test_is_supported_true(self):
        """지원 통화 확인."""
        from src.fx.supported_currencies import is_supported
        assert is_supported('USD') is True
        assert is_supported('JPY') is True

    def test_is_supported_false(self):
        """미지원 통화 확인."""
        from src.fx.supported_currencies import is_supported
        assert is_supported('XYZ') is False

    def test_is_supported_case_insensitive(self):
        """대소문자 무관 확인."""
        from src.fx.supported_currencies import is_supported
        assert is_supported('usd') is True
        assert is_supported('Jpy') is True

    def test_get_marketplace_currency(self):
        """마켓별 통화 반환."""
        from src.fx.supported_currencies import get_marketplace_currency
        assert get_marketplace_currency('amazon_us') == 'USD'
        assert get_marketplace_currency('amazon_jp') == 'JPY'
        assert get_marketplace_currency('taobao') == 'CNY'
        assert get_marketplace_currency('amazon_uk') == 'GBP'

    def test_marketplace_currency_unknown_default(self):
        """알 수 없는 마켓 기본값."""
        from src.fx.supported_currencies import get_marketplace_currency
        result = get_marketplace_currency('unknown_market')
        assert result == 'USD'


# ──────────────────────────────────────────────────────────
# RealtimeRates
# ──────────────────────────────────────────────────────────

class TestRealtimeRates:
    """실시간 환율 서비스 테스트."""

    def test_same_currency_returns_one(self):
        """동일 통화 환율 = 1."""
        from src.fx.realtime_rates import RealtimeRates
        service = RealtimeRates()
        assert service.get_rate('USD', 'USD') == Decimal('1')
        assert service.get_rate('KRW', 'KRW') == Decimal('1')

    def test_unsupported_currency_raises(self):
        """미지원 통화 ValueError."""
        from src.fx.realtime_rates import RealtimeRates
        service = RealtimeRates()
        with pytest.raises(ValueError, match='지원하지 않는 통화'):
            service.get_rate('XYZ', 'KRW')

    def test_fallback_usd_to_krw(self, monkeypatch):
        """API 키 없을 때 기본값 사용."""
        monkeypatch.delenv('KOREAEXIM_API_KEY', raising=False)
        monkeypatch.delenv('EXCHANGERATE_API_KEY', raising=False)
        from src.fx.realtime_rates import RealtimeRates
        service = RealtimeRates()
        rate = service.get_rate('USD', 'KRW')
        assert rate > Decimal('0')
        assert rate > Decimal('1000')  # USD/KRW는 항상 1000 이상

    def test_fallback_jpy_to_krw(self, monkeypatch):
        """JPY → KRW fallback."""
        monkeypatch.delenv('KOREAEXIM_API_KEY', raising=False)
        monkeypatch.delenv('EXCHANGERATE_API_KEY', raising=False)
        from src.fx.realtime_rates import RealtimeRates
        service = RealtimeRates()
        rate = service.get_rate('JPY', 'KRW')
        assert rate > Decimal('0')
        assert rate < Decimal('100')  # JPY/KRW는 한 자릿수

    def test_fallback_cny_to_krw(self, monkeypatch):
        """CNY → KRW fallback."""
        monkeypatch.delenv('KOREAEXIM_API_KEY', raising=False)
        monkeypatch.delenv('EXCHANGERATE_API_KEY', raising=False)
        from src.fx.realtime_rates import RealtimeRates
        service = RealtimeRates()
        rate = service.get_rate('CNY', 'KRW')
        assert rate > Decimal('100')

    def test_convert_usd_to_krw(self, monkeypatch):
        """금액 변환 테스트."""
        monkeypatch.delenv('KOREAEXIM_API_KEY', raising=False)
        monkeypatch.delenv('EXCHANGERATE_API_KEY', raising=False)
        from src.fx.realtime_rates import RealtimeRates
        from src.fx.supported_currencies import DEFAULT_RATES_TO_KRW
        service = RealtimeRates()
        result = service.convert(100, 'USD', 'KRW')
        expected = Decimal('100') * Decimal(str(DEFAULT_RATES_TO_KRW['USD']))
        assert result == expected

    def test_caching_prevents_duplicate_fetch(self, monkeypatch):
        """동일 통화쌍은 캐시에서 반환."""
        monkeypatch.delenv('KOREAEXIM_API_KEY', raising=False)
        monkeypatch.delenv('EXCHANGERATE_API_KEY', raising=False)
        from src.fx.realtime_rates import RealtimeRates
        service = RealtimeRates()
        rate1 = service.get_rate('USD', 'KRW')
        rate2 = service.get_rate('USD', 'KRW')
        assert rate1 == rate2

    def test_invalidate_cache(self, monkeypatch):
        """캐시 무효화 후 재조회."""
        monkeypatch.delenv('KOREAEXIM_API_KEY', raising=False)
        monkeypatch.delenv('EXCHANGERATE_API_KEY', raising=False)
        from src.fx.realtime_rates import RealtimeRates
        service = RealtimeRates()
        service.get_rate('USD', 'KRW')
        service.invalidate_cache('USD', 'KRW')
        assert service._cache.is_valid('USD', 'KRW') is False

    @patch('src.fx.realtime_rates.requests.get')
    def test_exchangerate_api_success(self, mock_get, monkeypatch):
        """exchangerate-api 응답 처리."""
        monkeypatch.delenv('KOREAEXIM_API_KEY', raising=False)
        monkeypatch.setenv('EXCHANGERATE_API_KEY', 'test-key')
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {
            'result': 'success',
            'conversion_rates': {'KRW': 1350.0},
        }
        mock_get.return_value = m
        from src.fx.realtime_rates import RealtimeRates
        service = RealtimeRates()
        rate = service.get_rate('USD', 'KRW')
        assert rate == Decimal('1350.0')

    @patch('src.fx.realtime_rates.requests.get')
    def test_koreaexim_api_success(self, mock_get, monkeypatch):
        """한국수출입은행 API 응답 처리."""
        monkeypatch.setenv('KOREAEXIM_API_KEY', 'test-key')
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = [
            {'cur_unit': 'USD', 'deal_bas_r': '1,345.50'},
            {'cur_unit': 'JPY(100)', 'deal_bas_r': '900.00'},
        ]
        mock_get.return_value = m
        from src.fx.realtime_rates import RealtimeRates
        service = RealtimeRates()
        rate = service.get_rate('USD', 'KRW')
        assert rate == Decimal('1345.50')

    @patch('src.fx.realtime_rates.requests.get')
    def test_koreaexim_jpy_100_unit(self, mock_get, monkeypatch):
        """한국수출입은행 JPY는 100엔 단위."""
        monkeypatch.setenv('KOREAEXIM_API_KEY', 'test-key')
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = [
            {'cur_unit': 'JPY(100)', 'deal_bas_r': '900.00'},
        ]
        mock_get.return_value = m
        from src.fx.realtime_rates import RealtimeRates
        service = RealtimeRates()
        rate = service.get_rate('JPY', 'KRW')
        # 900 / 100 = 9.0
        assert rate == Decimal('9.0')

    @patch('src.fx.realtime_rates.requests.get')
    def test_fallback_when_api_fails(self, mock_get, monkeypatch):
        """API 실패 시 기본값 사용."""
        monkeypatch.setenv('KOREAEXIM_API_KEY', 'test-key')
        monkeypatch.setenv('EXCHANGERATE_API_KEY', 'test-key')
        import requests as req
        mock_get.side_effect = req.exceptions.RequestException("API 오류")
        from src.fx.realtime_rates import RealtimeRates
        service = RealtimeRates()
        rate = service.get_rate('USD', 'KRW')
        # fallback 기본값
        assert rate == Decimal('1350.0')

    def test_get_rates_to_krw_all_currencies(self, monkeypatch):
        """전체 통화 KRW 환율 조회."""
        monkeypatch.delenv('KOREAEXIM_API_KEY', raising=False)
        monkeypatch.delenv('EXCHANGERATE_API_KEY', raising=False)
        from src.fx.realtime_rates import RealtimeRates
        from src.fx.supported_currencies import SUPPORTED_CURRENCIES
        service = RealtimeRates()
        rates = service.get_rates_to_krw()
        for currency in SUPPORTED_CURRENCIES:
            assert currency in rates
            assert rates[currency] >= Decimal('0')

    def test_krw_rate_is_one(self, monkeypatch):
        """KRW → KRW 환율 = 1."""
        monkeypatch.delenv('KOREAEXIM_API_KEY', raising=False)
        monkeypatch.delenv('EXCHANGERATE_API_KEY', raising=False)
        from src.fx.realtime_rates import RealtimeRates
        service = RealtimeRates()
        rates = service.get_rates_to_krw()
        assert rates['KRW'] == Decimal('1')

    def test_resolve_rate_direct(self):
        """직접 환율 계산 (KRW 기준)."""
        from src.fx.realtime_rates import RealtimeRates
        rate_map = {'USD': Decimal('1350'), 'EUR': Decimal('1470')}
        result = RealtimeRates._resolve_rate('USD', 'KRW', rate_map)
        assert result == Decimal('1350')

    def test_resolve_rate_inverse(self):
        """역방향 환율 계산."""
        from src.fx.realtime_rates import RealtimeRates
        rate_map = {'USD': Decimal('1350')}
        result = RealtimeRates._resolve_rate('KRW', 'USD', rate_map)
        assert result == Decimal('1') / Decimal('1350')

    def test_resolve_rate_cross(self):
        """교차 환율 계산."""
        from src.fx.realtime_rates import RealtimeRates
        rate_map = {'USD': Decimal('1350'), 'JPY': Decimal('9.0')}
        result = RealtimeRates._resolve_rate('USD', 'JPY', rate_map)
        expected = Decimal('1350') / Decimal('9.0')
        assert result == expected

    def test_resolve_rate_missing_returns_none(self):
        """환율 맵에 없으면 None."""
        from src.fx.realtime_rates import RealtimeRates
        rate_map = {'USD': Decimal('1350')}
        result = RealtimeRates._resolve_rate('CNY', 'KRW', rate_map)
        assert result is None


# ──────────────────────────────────────────────────────────
# fx 패키지 __init__ 수출 검증
# ──────────────────────────────────────────────────────────

class TestFXPackageExports:
    """fx 패키지 수출 검증."""

    def test_realtime_rates_importable(self):
        """RealtimeRates 임포트 가능."""
        from src.fx import RealtimeRates
        assert RealtimeRates is not None

    def test_rate_cache_importable(self):
        """RateCache 임포트 가능."""
        from src.fx import RateCache
        assert RateCache is not None

    def test_supported_currencies_importable(self):
        """SUPPORTED_CURRENCIES 임포트 가능."""
        from src.fx import SUPPORTED_CURRENCIES
        assert isinstance(SUPPORTED_CURRENCIES, list)
        assert len(SUPPORTED_CURRENCIES) > 0

    def test_default_rates_importable(self):
        """DEFAULT_RATES_TO_KRW 임포트 가능."""
        from src.fx import DEFAULT_RATES_TO_KRW
        assert isinstance(DEFAULT_RATES_TO_KRW, dict)

    def test_existing_exports_not_broken(self):
        """기존 수출 항목 유지."""
        from src.fx import FXProvider, FXCache, FXHistory, FXUpdater
        assert FXProvider is not None
        assert FXCache is not None
        assert FXHistory is not None
        assert FXUpdater is not None
