"""src/fx 패키지 단위 테스트."""

import os
import sys
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ──────────────────────────────────────────────────────────
# FXProvider
# ──────────────────────────────────────────────────────────

class TestFXProviderFrankfurter:
    """frankfurter.app API 응답 mock 테스트."""

    def _make_resp(self, from_cur, to_cur, rate):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {'base': from_cur, 'rates': {to_cur: rate}}
        return m

    @patch('src.fx.provider.requests.get')
    def test_get_rates_success(self, mock_get):
        mock_get.side_effect = [
            self._make_resp('USD', 'KRW', 1345.5),
            self._make_resp('JPY', 'KRW', 8.95),
            self._make_resp('EUR', 'KRW', 1462.3),
        ]
        from src.fx.provider import FXProvider
        p = FXProvider(primary_provider='frankfurter')
        rates = p.get_rates()

        assert rates['USDKRW'] == Decimal('1345.5')
        assert rates['JPYKRW'] == Decimal('8.95')
        assert rates['EURKRW'] == Decimal('1462.3')
        assert rates['provider'] == 'frankfurter'
        assert 'fetched_at' in rates

    @patch('src.fx.provider.requests.get')
    def test_get_rate_single(self, mock_get):
        mock_get.side_effect = [
            self._make_resp('USD', 'KRW', 1340.0),
            self._make_resp('JPY', 'KRW', 9.1),
            self._make_resp('EUR', 'KRW', 1460.0),
        ]
        from src.fx.provider import FXProvider
        p = FXProvider(primary_provider='frankfurter')
        rate = p.get_rate('USDKRW')
        assert rate == Decimal('1340.0')

    def test_get_rate_unsupported_pair(self):
        from src.fx.provider import FXProvider
        p = FXProvider(primary_provider='env')
        with pytest.raises(ValueError, match='지원하지 않는 통화쌍'):
            p.get_rate('GBPKRW')


class TestFXProviderExchangeRateAPI:
    """exchangerate-api.com 응답 mock 테스트."""

    def _make_resp(self, from_cur, to_cur, rate):
        m = MagicMock()
        m.raise_for_status = MagicMock()
        m.json.return_value = {
            'result': 'success',
            'base_code': from_cur,
            'target_code': to_cur,
            'conversion_rate': rate,
        }
        return m

    @patch('src.fx.provider.requests.get')
    def test_get_rates_exchangerate_api(self, mock_get):
        mock_get.side_effect = [
            self._make_resp('USD', 'KRW', 1350.0),
            self._make_resp('JPY', 'KRW', 9.0),
            self._make_resp('EUR', 'KRW', 1470.0),
        ]
        from src.fx.provider import FXProvider
        with patch.dict(os.environ, {'EXCHANGERATE_API_KEY': 'test-key'}):
            p = FXProvider(primary_provider='exchangerate-api')
            rates = p.get_rates()

        assert rates['USDKRW'] == Decimal('1350.0')
        assert rates['provider'] == 'exchangerate-api'

    def test_exchangerate_api_no_key_raises(self):
        from src.fx.provider import FXProvider
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('EXCHANGERATE_API_KEY', None)
            p = FXProvider(primary_provider='exchangerate-api')
            with pytest.raises(ValueError, match='EXCHANGERATE_API_KEY not set'):
                p._fetch_exchangerate_api()


class TestFXProviderFallback:
    """자동 폴백 및 환경변수 폴백 테스트."""

    @patch('src.fx.provider.requests.get', side_effect=Exception('network error'))
    def test_fallback_to_env_when_all_fail(self, mock_get):
        from src.fx.provider import FXProvider
        with patch.dict(os.environ, {
            'FX_USDKRW': '1400',
            'FX_JPYKRW': '9.5',
            'FX_EURKRW': '1500',
        }):
            p = FXProvider(primary_provider='frankfurter')
            rates = p.get_rates()

        assert rates['USDKRW'] == Decimal('1400')
        assert rates['JPYKRW'] == Decimal('9.5')
        assert rates['EURKRW'] == Decimal('1500')
        assert rates['provider'] == 'env'

    def test_env_fallback_uses_defaults_when_no_env(self):
        from src.fx.provider import FXProvider
        env = {k: v for k, v in os.environ.items()
               if k not in ('FX_USDKRW', 'FX_JPYKRW', 'FX_EURKRW')}
        with patch.dict(os.environ, env, clear=True):
            p = FXProvider(primary_provider='env')
            rates = p._fallback_env()

        assert 'USDKRW' in rates
        assert isinstance(rates['USDKRW'], Decimal)

    @patch('src.fx.provider.requests.get')
    def test_primary_failure_falls_back_to_secondary(self, mock_get):
        """primary 실패 → secondary 성공."""
        # frankfurter fails, exchangerate-api succeeds
        def side_effect(url, timeout):
            if 'frankfurter' in url:
                raise Exception('frankfurter down')
            m = MagicMock()
            m.raise_for_status = MagicMock()
            m.json.return_value = {
                'result': 'success',
                'conversion_rate': 1340.0,
            }
            return m

        mock_get.side_effect = side_effect

        from src.fx.provider import FXProvider
        with patch.dict(os.environ, {'EXCHANGERATE_API_KEY': 'key'}):
            p = FXProvider(primary_provider='frankfurter')
            rates = p.get_rates()

        # All three pairs should be fetched from exchangerate-api
        assert rates['provider'] == 'exchangerate-api'


# ──────────────────────────────────────────────────────────
# FXCache
# ──────────────────────────────────────────────────────────

class TestFXCache:
    """TTL 기반 캐시 테스트."""

    def _sample_rates(self):
        return {
            'USDKRW': Decimal('1350'),
            'JPYKRW': Decimal('9.0'),
            'EURKRW': Decimal('1470'),
            'fetched_at': '2026-03-09T00:00:00+00:00',
            'provider': 'frankfurter',
        }

    def test_set_and_get(self):
        from src.fx.cache import FXCache
        cache = FXCache(ttl_seconds=60)
        with patch.object(cache, '_save_to_sheets'):
            cache.set(self._sample_rates())
            result = cache.get()

        assert result is not None
        assert result['USDKRW'] == Decimal('1350')

    def test_ttl_expiry_returns_none_from_memory(self):
        from src.fx.cache import FXCache
        cache = FXCache(ttl_seconds=0)
        with patch.object(cache, '_save_to_sheets'), \
             patch.object(cache, '_load_from_sheets', return_value=None):
            cache.set(self._sample_rates())
            time.sleep(0.01)
            result = cache.get()

        assert result is None

    def test_is_valid_true_within_ttl(self):
        from src.fx.cache import FXCache
        cache = FXCache(ttl_seconds=3600)
        with patch.object(cache, '_save_to_sheets'):
            cache.set(self._sample_rates())

        assert cache.is_valid() is True

    def test_is_valid_false_when_empty(self):
        from src.fx.cache import FXCache
        cache = FXCache(ttl_seconds=3600)
        assert cache.is_valid() is False

    def test_invalidate(self):
        from src.fx.cache import FXCache
        cache = FXCache(ttl_seconds=3600)
        with patch.object(cache, '_save_to_sheets'):
            cache.set(self._sample_rates())

        cache.invalidate()
        assert cache.is_valid() is False

    def test_get_returns_copy(self):
        """get()은 내부 상태를 노출하지 않는다."""
        from src.fx.cache import FXCache
        cache = FXCache(ttl_seconds=3600)
        rates = self._sample_rates()
        with patch.object(cache, '_save_to_sheets'):
            cache.set(rates)
        result = cache.get()
        result['USDKRW'] = Decimal('9999')
        assert cache._data['USDKRW'] == Decimal('1350')


# ──────────────────────────────────────────────────────────
# FXHistory
# ──────────────────────────────────────────────────────────

class TestFXHistory:
    """환율 이력 관리 테스트."""

    def _sample_rates(self, usd='1350', jpy='9.0', eur='1470'):
        return {
            'USDKRW': Decimal(usd),
            'JPYKRW': Decimal(jpy),
            'EURKRW': Decimal(eur),
            'provider': 'frankfurter',
            'fetched_at': '2026-03-09T00:00:00+00:00',
        }

    def test_record_calls_append_row(self):
        from src.fx.history import FXHistory
        history = FXHistory(sheet_id='test-id')
        mock_ws = MagicMock()
        with patch.object(history, '_get_worksheet', return_value=mock_ws):
            history.record(self._sample_rates())

        mock_ws.append_row.assert_called_once()
        call_args = mock_ws.append_row.call_args[0][0]
        assert call_args[1] == '1350'
        assert call_args[2] == '9.0'
        assert call_args[3] == '1470'

    def test_get_history_filters_by_days(self):
        from src.fx.history import FXHistory
        from datetime import datetime, timedelta, timezone
        history = FXHistory(sheet_id='test-id')

        today = datetime.now(tz=timezone.utc)
        records = [
            {'date': (today - timedelta(days=i)).strftime('%Y-%m-%d'),
             'USDKRW': '1350', 'JPYKRW': '9.0', 'EURKRW': '1470',
             'provider': 'frankfurter', 'fetched_at': ''}
            for i in range(40)
        ]
        with patch.object(history, '_get_all_records', return_value=records):
            result = history.get_history(days=7)

        assert len(result) <= 8  # 최대 8일치

    def test_get_change_pct_no_history(self):
        from src.fx.history import FXHistory
        history = FXHistory(sheet_id='test-id')
        with patch.object(history, '_get_all_records', return_value=[]):
            pct = history.get_change_pct('USDKRW', days=1)
        assert pct == Decimal('0')

    def test_detect_significant_changes_above_threshold(self):
        from src.fx.history import FXHistory
        from datetime import datetime, timedelta, timezone
        history = FXHistory(sheet_id='test-id')

        today = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
        yesterday = (datetime.now(tz=timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')
        records = [
            {'date': yesterday, 'USDKRW': '1000', 'JPYKRW': '9.0', 'EURKRW': '1470',
             'provider': 'frankfurter', 'fetched_at': ''},
            {'date': today, 'USDKRW': '1100', 'JPYKRW': '9.0', 'EURKRW': '1470',
             'provider': 'frankfurter', 'fetched_at': ''},
        ]
        with patch.object(history, '_get_all_records', return_value=records):
            changes = history.detect_significant_changes(threshold_pct=3.0)

        assert len(changes) == 1
        assert changes[0]['pair'] == 'USDKRW'
        assert '+10.00%' in changes[0]['change_pct']

    def test_detect_significant_changes_below_threshold(self):
        from src.fx.history import FXHistory
        from datetime import datetime, timedelta, timezone
        history = FXHistory(sheet_id='test-id')

        today = datetime.now(tz=timezone.utc).strftime('%Y-%m-%d')
        yesterday = (datetime.now(tz=timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')
        records = [
            {'date': yesterday, 'USDKRW': '1350', 'JPYKRW': '9.0', 'EURKRW': '1470',
             'provider': 'frankfurter', 'fetched_at': ''},
            {'date': today, 'USDKRW': '1355', 'JPYKRW': '9.0', 'EURKRW': '1470',
             'provider': 'frankfurter', 'fetched_at': ''},
        ]
        with patch.object(history, '_get_all_records', return_value=records):
            changes = history.detect_significant_changes(threshold_pct=3.0)

        assert len(changes) == 0

    def test_get_average(self):
        from src.fx.history import FXHistory
        from datetime import datetime, timedelta, timezone
        history = FXHistory(sheet_id='test-id')

        today = datetime.now(tz=timezone.utc)
        records = [
            {'date': (today - timedelta(days=i)).strftime('%Y-%m-%d'),
             'USDKRW': str(1350 + i * 10), 'JPYKRW': '9.0', 'EURKRW': '1470',
             'provider': 'frankfurter', 'fetched_at': ''}
            for i in range(3)
        ]
        # values: 1350, 1360, 1370 → avg 1360
        with patch.object(history, '_get_all_records', return_value=records):
            avg = history.get_average('USDKRW', days=7)

        assert avg == Decimal('1360')


# ──────────────────────────────────────────────────────────
# FXUpdater
# ──────────────────────────────────────────────────────────

class TestFXUpdater:
    """FXUpdater 통합 테스트."""

    def _sample_rates(self):
        return {
            'USDKRW': Decimal('1350'),
            'JPYKRW': Decimal('9.0'),
            'EURKRW': Decimal('1470'),
            'fetched_at': '2026-03-09T00:00:00+00:00',
            'provider': 'frankfurter',
        }

    def test_update_normal_flow(self):
        from src.fx.updater import FXUpdater
        updater = FXUpdater()

        with patch.object(updater.cache, 'is_valid', return_value=False), \
             patch.object(updater.provider, 'get_rates', return_value=self._sample_rates()), \
             patch.object(updater.cache, 'set'), \
             patch.object(updater.history, 'record'), \
             patch.object(updater.history, 'detect_significant_changes', return_value=[]), \
             patch.object(updater, 'recalculate_prices', return_value=[]):

            result = updater.update()

        assert result['provider'] == 'frankfurter'
        assert result['rates']['USDKRW'] == '1350'
        assert result['alerts_sent'] is False
        assert result['dry_run'] is False

    def test_update_force_invalidates_cache(self):
        from src.fx.updater import FXUpdater
        updater = FXUpdater()

        with patch.object(updater.cache, 'invalidate') as mock_invalidate, \
             patch.object(updater.cache, 'is_valid', return_value=True), \
             patch.object(updater.provider, 'get_rates', return_value=self._sample_rates()), \
             patch.object(updater.cache, 'set'), \
             patch.object(updater.history, 'record'), \
             patch.object(updater.history, 'detect_significant_changes', return_value=[]), \
             patch.object(updater, 'recalculate_prices', return_value=[]):

            updater.update(force=True)

        mock_invalidate.assert_called_once()

    def test_update_dry_run_skips_record(self):
        from src.fx.updater import FXUpdater
        updater = FXUpdater()

        with patch.object(updater.cache, 'is_valid', return_value=False), \
             patch.object(updater.provider, 'get_rates', return_value=self._sample_rates()), \
             patch.object(updater.cache, 'set'), \
             patch.object(updater.history, 'record') as mock_record, \
             patch.object(updater.history, 'detect_significant_changes', return_value=[]), \
             patch.object(updater, 'recalculate_prices', return_value=[]):

            result = updater.update(dry_run=True)

        mock_record.assert_not_called()
        assert result['dry_run'] is True

    def test_update_sends_alert_on_changes(self):
        from src.fx.updater import FXUpdater
        updater = FXUpdater()
        changes = [{'pair': 'JPYKRW', 'previous': '9.2', 'current': '8.8', 'change_pct': '-4.35%'}]

        with patch.object(updater.cache, 'is_valid', return_value=False), \
             patch.object(updater.provider, 'get_rates', return_value=self._sample_rates()), \
             patch.object(updater.cache, 'set'), \
             patch.object(updater.history, 'record'), \
             patch.object(updater.history, 'detect_significant_changes', return_value=changes), \
             patch.object(updater, '_send_fx_alert') as mock_alert, \
             patch.object(updater, 'recalculate_prices', return_value=[]):

            result = updater.update()

        mock_alert.assert_called_once()
        assert result['alerts_sent'] is True

    def test_recalculate_prices_dry_run(self):
        from src.fx.updater import FXUpdater
        updater = FXUpdater()

        mock_rows = [
            {'sku': 'TEST-001', 'status': 'active', 'buy_price': '10000',
             'buy_currency': 'JPY', 'sell_price_krw': '', 'sell_price_usd': ''},
        ]
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = mock_rows

        with patch.dict(os.environ, {'GOOGLE_SHEET_ID': 'test-id', 'TARGET_MARGIN_PCT': '22'}), \
             patch('src.fx.updater.open_sheet', return_value=mock_ws):

            rates = self._sample_rates()
            results = updater.recalculate_prices(rates, dry_run=True)

        assert len(results) == 1
        assert results[0]['sku'] == 'TEST-001'
        assert results[0]['shopify_updated'] is False
        assert results[0]['woo_updated'] is False

    def test_get_current_rates_from_cache(self):
        from src.fx.updater import FXUpdater
        updater = FXUpdater()
        cached = self._sample_rates()

        with patch.object(updater.cache, 'get', return_value=cached):
            rates = updater.get_current_rates()

        assert rates['USDKRW'] == Decimal('1350')


# ──────────────────────────────────────────────────────────
# price.py 통합 — _build_fx_rates(use_live=True)
# ──────────────────────────────────────────────────────────

class TestBuildFxRatesWithLive:
    """_build_fx_rates(use_live=True) 시 FXCache에서 환율 로드."""

    def test_use_live_true_loads_from_cache(self):
        from src.price import _build_fx_rates
        cached = {
            'USDKRW': Decimal('1400'),
            'JPYKRW': Decimal('10.0'),
            'EURKRW': Decimal('1500'),
            'provider': 'frankfurter',
            'fetched_at': '2026-03-09T00:00:00+00:00',
        }
        mock_cache = MagicMock()
        mock_cache.return_value.get.return_value = cached

        with patch('src.price.FXCache', mock_cache):
            rates = _build_fx_rates(use_live=True)

        assert rates['USDKRW'] == Decimal('1400')
        assert rates['JPYKRW'] == Decimal('10.0')
        assert rates['EURKRW'] == Decimal('1500')

    def test_use_live_true_cache_miss_falls_back_to_env(self):
        from src.price import _build_fx_rates
        mock_cache = MagicMock()
        mock_cache.return_value.get.return_value = None

        with patch('src.price.FXCache', mock_cache), \
             patch.dict(os.environ, {'FX_USDKRW': '1380', 'FX_JPYKRW': '9.2', 'FX_EURKRW': '1480'}):
            rates = _build_fx_rates(use_live=True)

        assert rates['USDKRW'] == Decimal('1380')

    def test_use_live_false_uses_env(self):
        from src.price import _build_fx_rates
        with patch.dict(os.environ, {'FX_USDKRW': '1360', 'FX_USE_LIVE': '0'}):
            rates = _build_fx_rates()

        assert rates['USDKRW'] == Decimal('1360')

    def test_explicit_params_take_priority_over_live(self):
        from src.price import _build_fx_rates
        cached = {
            'USDKRW': Decimal('9999'),
            'JPYKRW': Decimal('9999'),
            'EURKRW': Decimal('9999'),
        }
        mock_cache = MagicMock()
        mock_cache.return_value.get.return_value = cached

        with patch('src.price.FXCache', mock_cache):
            # 파라미터 직접 지정 시 캐시보다 우선
            rates = _build_fx_rates(
                fx_usdkrw=Decimal('1350'),
                fx_jpykrw=Decimal('9.0'),
                fx_eurkrw=Decimal('1470'),
                use_live=True,
            )

        assert rates['USDKRW'] == Decimal('1350')
        assert rates['JPYKRW'] == Decimal('9.0')

    def test_use_live_env_variable(self):
        """FX_USE_LIVE=1 환경변수로 실시간 환율 활성화."""
        from src.price import _build_fx_rates
        cached = {
            'USDKRW': Decimal('1420'),
            'JPYKRW': Decimal('9.5'),
            'EURKRW': Decimal('1490'),
            'provider': 'frankfurter',
            'fetched_at': '',
        }
        mock_cache = MagicMock()
        mock_cache.return_value.get.return_value = cached

        with patch.dict(os.environ, {'FX_USE_LIVE': '1'}), \
             patch('src.price.FXCache', mock_cache):
            rates = _build_fx_rates()

        assert rates['USDKRW'] == Decimal('1420')


# ──────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────

class TestFXCLI:
    """CLI 기본 동작 테스트."""

    def test_action_current(self, capsys):
        from src.fx import cli as fx_cli
        mock_rates = {
            'USDKRW': Decimal('1350'),
            'JPYKRW': Decimal('9.0'),
            'EURKRW': Decimal('1470'),
            'provider': 'frankfurter',
            'fetched_at': '2026-03-09T00:00:00+00:00',
        }
        with patch('src.fx.updater.FXUpdater.get_current_rates', return_value=mock_rates):
            fx_cli.main(['--action', 'current'])

        out = capsys.readouterr().out
        assert 'USDKRW' in out

    def test_action_check_changes_no_changes(self, capsys):
        from src.fx import cli as fx_cli
        with patch('src.fx.history.FXHistory.detect_significant_changes', return_value=[]):
            fx_cli.main(['--action', 'check-changes', '--threshold', '3.0'])

        out = capsys.readouterr().out
        assert '급변 없음' in out

    def test_action_check_changes_with_changes(self, capsys):
        from src.fx import cli as fx_cli
        changes = [{'pair': 'JPYKRW', 'previous': '9.2', 'current': '8.8', 'change_pct': '-4.35%'}]
        with patch('src.fx.history.FXHistory.detect_significant_changes', return_value=changes):
            fx_cli.main(['--action', 'check-changes', '--threshold', '3.0'])

        out = capsys.readouterr().out
        assert 'JPYKRW' in out

    def test_action_update(self, capsys):
        from src.fx import cli as fx_cli
        result = {
            'rates': {'USDKRW': '1350', 'JPYKRW': '9.0', 'EURKRW': '1470'},
            'provider': 'frankfurter',
            'changes_detected': [],
            'prices_recalculated': 0,
            'shopify_updated': 0,
            'woo_updated': 0,
            'alerts_sent': False,
            'dry_run': False,
        }
        with patch('src.fx.updater.FXUpdater.update', return_value=result):
            fx_cli.main(['--action', 'update'])

        out = capsys.readouterr().out
        assert 'frankfurter' in out

    def test_action_history(self, capsys):
        from src.fx import cli as fx_cli
        records = [
            {'date': '2026-03-09', 'USDKRW': Decimal('1350'),
             'JPYKRW': Decimal('9.0'), 'EURKRW': Decimal('1470'),
             'provider': 'frankfurter', 'fetched_at': ''}
        ]
        with patch('src.fx.history.FXHistory.get_history', return_value=records):
            fx_cli.main(['--action', 'history', '--days', '7'])

        out = capsys.readouterr().out
        assert '2026-03-09' in out


# ──────────────────────────────────────────────────────────
# E2E: 환율 변동 → 가격 재계산 흐름
# ──────────────────────────────────────────────────────────

class TestFXE2E:
    """환율 변동 → 가격 재계산 E2E 테스트."""

    def test_price_recalculation_reflects_new_rates(self):
        """환율이 변동되면 재계산된 KRW 가격이 달라진다."""
        from src.price import calc_price

        old_rates = {'USDKRW': Decimal('1350'), 'JPYKRW': Decimal('9.0'), 'EURKRW': Decimal('1470')}
        new_rates = {'USDKRW': Decimal('1400'), 'JPYKRW': Decimal('9.0'), 'EURKRW': Decimal('1470')}

        old_price = calc_price(100, 'USD', None, 22, 'KRW', fx_rates=old_rates)
        new_price = calc_price(100, 'USD', None, 22, 'KRW', fx_rates=new_rates)

        assert new_price > old_price
        # $100 × 1400 × 1.22 = 170800
        assert new_price == Decimal('170800.00')

    def test_fx_updater_recalculate_dry_run_returns_items(self):
        """dry_run=True에서 recalculate_prices가 결과 리스트를 반환한다."""
        from src.fx.updater import FXUpdater
        updater = FXUpdater()

        mock_rows = [
            {'sku': 'EUR-001', 'status': 'active', 'buy_price': '200',
             'buy_currency': 'EUR', 'sell_price_krw': '', 'sell_price_usd': ''},
        ]
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = mock_rows

        rates = {
            'USDKRW': Decimal('1350'),
            'JPYKRW': Decimal('9.0'),
            'EURKRW': Decimal('1470'),
            'provider': 'frankfurter',
        }

        with patch.dict(os.environ, {'GOOGLE_SHEET_ID': 'test-id', 'TARGET_MARGIN_PCT': '22'}), \
             patch('src.fx.updater.open_sheet', return_value=mock_ws):
            results = updater.recalculate_prices(rates, dry_run=True)

        assert len(results) == 1
        # €200 × 1470 × 1.22 = 358680
        assert results[0]['sell_price_krw'] == Decimal('358680.00')
