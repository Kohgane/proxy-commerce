"""tests/test_auto_pricing.py — Phase 7 AutoPricingEngine 테스트."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.analytics.auto_pricing import AutoPricingEngine  # noqa: E402

# ──────────────────────────────────────────────────────────
# 공통 픽스처
# ──────────────────────────────────────────────────────────

SAMPLE_FX = {'USDKRW': 1400.0, 'JPYKRW': 9.5, 'EURKRW': 1520.0}

SAMPLE_CATALOG = [
    {
        'sku': 'PTR-TNK-001',
        'buy_price': 30000,
        'buy_currency': 'JPY',
        'sell_price_krw': 360000,
        'margin_pct': 20.0,
        'status': 'active',
    },
    {
        'sku': 'MMP-EDP-001',
        'buy_price': 200.0,
        'buy_currency': 'EUR',
        'sell_price_krw': 450000,
        'margin_pct': 25.0,
        'status': 'active',
    },
    {
        'sku': 'PTR-LFT-001',
        'buy_price': 15000,
        'buy_currency': 'JPY',
        'sell_price_krw': 165000,
        'margin_pct': 8.0,  # MIN_MARGIN_PCT 이하
        'status': 'active',
    },
]


def _make_engine(dry_run=True, min_margin=10.0, max_change=8.0):
    with patch.dict(os.environ, {
        'AUTO_PRICING_MODE': 'DRY_RUN' if dry_run else 'APPLY',
        'MIN_MARGIN_PCT': str(min_margin),
        'MAX_PRICE_CHANGE_PCT': str(max_change),
    }):
        engine = AutoPricingEngine(sheet_id='dummy')
    engine._get_current_fx = MagicMock(return_value=SAMPLE_FX)
    engine._get_catalog_rows = MagicMock(return_value=list(SAMPLE_CATALOG))
    return engine


# ══════════════════════════════════════════════════════════
# calculate_new_prices 테스트
# ══════════════════════════════════════════════════════════

class TestCalculateNewPrices:
    def test_returns_list(self):
        engine = _make_engine()
        result = engine.calculate_new_prices()
        assert isinstance(result, list)

    def test_each_item_has_required_keys(self):
        engine = _make_engine()
        result = engine.calculate_new_prices()
        required = {
            'sku', 'buy_currency', 'fx_rate', 'cost_krw',
            'old_price_krw', 'new_price_krw', 'change_pct',
            'margin_current', 'margin_new', 'needs_update',
        }
        for item in result:
            assert required.issubset(item.keys()), f"Missing keys in {item}"

    def test_sku_matches_catalog(self):
        engine = _make_engine()
        result = engine.calculate_new_prices()
        skus = {item['sku'] for item in result}
        assert 'PTR-TNK-001' in skus
        assert 'MMP-EDP-001' in skus

    def test_cost_krw_calculation(self):
        engine = _make_engine()
        result = engine.calculate_new_prices()
        ptr_item = next(i for i in result if i['sku'] == 'PTR-TNK-001')
        # 30000 JPY × 9.5 = 285000
        assert ptr_item['cost_krw'] == 285000

    def test_max_price_change_enforced(self):
        """가격 변동폭이 MAX_PRICE_CHANGE_PCT를 초과하지 않아야 한다."""
        engine = _make_engine(max_change=5.0)
        result = engine.calculate_new_prices()
        for item in result:
            assert abs(item['change_pct']) <= 5.0 + 0.01  # float 오차 허용

    def test_min_margin_protection(self):
        """마진이 MIN 이하인 경우 새 가격이 MIN 마진을 보장해야 한다.

        PTR-LFT-001의 catalog margin_pct=8.0%는 MIN_MARGIN_PCT=10.0% 미만이므로
        새 판매가의 margin_new는 MIN_MARGIN에 맞춰 조정되어야 한다.
        단, MAX_PRICE_CHANGE_PCT=8%가 상한선으로 작용할 수 있으므로
        margin_new < MIN - 1.0이면 안 된다.
        """
        engine = _make_engine(min_margin=10.0, max_change=20.0)  # 충분한 max_change로 MIN_MARGIN 보장
        result = engine.calculate_new_prices()
        lft_item = next((i for i in result if i['sku'] == 'PTR-LFT-001'), None)
        assert lft_item is not None
        # margin_new는 MIN_MARGIN(10.0%) 이상이어야 한다 (float 오차 0.1% 허용)
        assert lft_item['margin_new'] >= 10.0 - 0.1

    def test_needs_update_flag(self):
        """change_pct >= 0.5 이면 needs_update=True."""
        engine = _make_engine()
        result = engine.calculate_new_prices()
        for item in result:
            if abs(item['change_pct']) >= 0.5:
                assert item['needs_update'] is True
            else:
                assert item['needs_update'] is False

    def test_empty_catalog_returns_empty_list(self):
        engine = _make_engine()
        engine._get_catalog_rows = MagicMock(return_value=[])
        result = engine.calculate_new_prices()
        assert result == []

    def test_eur_currency_uses_eurkrw_rate(self):
        engine = _make_engine()
        result = engine.calculate_new_prices()
        mmp_item = next(i for i in result if i['sku'] == 'MMP-EDP-001')
        # 200 EUR × 1520 = 304000
        assert mmp_item['cost_krw'] == 304000
        assert mmp_item['fx_rate'] == SAMPLE_FX['EURKRW']


# ══════════════════════════════════════════════════════════
# apply_price_changes 테스트
# ══════════════════════════════════════════════════════════

class TestApplyPriceChanges:
    def test_dry_run_no_changes(self):
        engine = _make_engine(dry_run=True)
        changes = engine.calculate_new_prices()
        result = engine.apply_price_changes(changes)
        assert result['dry_run'] is True
        assert result['updated_sheets'] == 0
        assert result['updated_shopify'] == 0
        assert result['updated_woo'] == 0

    def test_result_has_required_keys(self):
        engine = _make_engine()
        changes = engine.calculate_new_prices()
        result = engine.apply_price_changes(changes)
        required = {
            'dry_run', 'total_checked', 'needs_update',
            'updated_sheets', 'updated_shopify', 'updated_woo', 'errors',
        }
        assert required.issubset(result.keys())

    def test_total_checked_matches_input(self):
        engine = _make_engine()
        changes = engine.calculate_new_prices()
        result = engine.apply_price_changes(changes)
        assert result['total_checked'] == len(changes)

    def test_empty_changes_returns_zero_counts(self):
        engine = _make_engine()
        result = engine.apply_price_changes([])
        assert result['total_checked'] == 0
        assert result['needs_update'] == 0


# ══════════════════════════════════════════════════════════
# generate_report 테스트
# ══════════════════════════════════════════════════════════

class TestGenerateReport:
    def test_returns_string(self):
        engine = _make_engine()
        changes = engine.calculate_new_prices()
        report = engine.generate_report(changes)
        assert isinstance(report, str)

    def test_report_contains_mode_label(self):
        engine = _make_engine(dry_run=True)
        changes = engine.calculate_new_prices()
        report = engine.generate_report(changes)
        assert 'DRY RUN' in report

    def test_report_contains_sku_info(self):
        engine = _make_engine()
        # 강제로 needs_update=True인 변경 생성
        changes = [
            {
                'sku': 'PTR-TNK-001',
                'old_price_krw': 360000,
                'new_price_krw': 375000,
                'change_pct': 4.2,
                'margin_new': 20.5,
                'needs_update': True,
            }
        ]
        report = engine.generate_report(changes)
        assert 'PTR-TNK-001' in report

    def test_report_shows_risk_skus(self):
        engine = _make_engine(min_margin=30.0)  # 높은 MIN 마진으로 위험 SKU 생성
        changes = [
            {
                'sku': 'PTR-TNK-001',
                'old_price_krw': 360000,
                'new_price_krw': 375000,
                'change_pct': 4.2,
                'margin_new': 15.0,  # < 30.0
                'needs_update': True,
            }
        ]
        report = engine.generate_report(changes)
        assert '마진 위험' in report

    def test_empty_changes_report(self):
        engine = _make_engine()
        report = engine.generate_report([])
        assert isinstance(report, str)
        assert '0개' in report


# ══════════════════════════════════════════════════════════
# check_and_adjust 테스트
# ══════════════════════════════════════════════════════════

class TestCheckAndAdjust:
    @patch.dict(os.environ, {'AUTO_PRICING_ENABLED': '0'})
    def test_disabled_returns_skipped(self):
        engine = _make_engine()
        result = engine.check_and_adjust()
        assert result == {'skipped': True}

    @patch.dict(os.environ, {'AUTO_PRICING_ENABLED': '1', 'TELEGRAM_ENABLED': '0'})
    def test_enabled_returns_result(self):
        engine = _make_engine()
        result = engine.check_and_adjust()
        assert 'report' in result
        assert 'dry_run' in result

    @patch.dict(os.environ, {'AUTO_PRICING_ENABLED': '1', 'TELEGRAM_ENABLED': '1'})
    def test_telegram_error_does_not_raise(self):
        engine = _make_engine()
        with patch('src.analytics.auto_pricing.AutoPricingEngine.generate_report', return_value='test'):
            with patch('src.utils.telegram.send_tele', side_effect=Exception("network error")):
                # Should not raise
                try:
                    engine.check_and_adjust()
                except Exception:
                    pytest.fail("check_and_adjust raised an exception")


# ══════════════════════════════════════════════════════════
# _get_current_fx 테스트
# ══════════════════════════════════════════════════════════

class TestGetCurrentFx:
    def test_fallback_to_env_vars(self):
        engine = AutoPricingEngine(sheet_id='')
        with patch.dict(os.environ, {
            'FX_USDKRW': '1400',
            'FX_JPYKRW': '9.5',
            'FX_EURKRW': '1520',
        }):
            fx = engine._get_current_fx()
        assert fx['USDKRW'] == 1400.0
        assert fx['JPYKRW'] == 9.5
        assert fx['EURKRW'] == 1520.0

    def test_returns_required_keys(self):
        engine = AutoPricingEngine(sheet_id='')
        fx = engine._get_current_fx()
        assert 'USDKRW' in fx
        assert 'JPYKRW' in fx
        assert 'EURKRW' in fx
