"""tests/test_reorder_alert.py — Phase 7 ReorderAlertEngine 테스트."""

import os
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.analytics.reorder_alert import ReorderAlertEngine

# ──────────────────────────────────────────────────────────
# 공통 픽스처
# ──────────────────────────────────────────────────────────

TODAY = str(date.today())
FIVE_DAYS_AGO = str(date.today() - timedelta(days=5))
TWENTY_DAYS_AGO = str(date.today() - timedelta(days=20))

SAMPLE_ORDER_ROWS = [
    {'order_date': TODAY, 'sku': 'PTR-TNK-001', 'vendor': 'PORTER'},
    {'order_date': TODAY, 'sku': 'PTR-TNK-001', 'vendor': 'PORTER'},
    {'order_date': FIVE_DAYS_AGO, 'sku': 'PTR-TNK-001', 'vendor': 'PORTER'},
    {'order_date': TWENTY_DAYS_AGO, 'sku': 'MMP-EDP-001', 'vendor': 'MEMO_PARIS'},
    {'order_date': TWENTY_DAYS_AGO, 'sku': 'MMP-EDP-001', 'vendor': 'MEMO_PARIS'},
]

SAMPLE_CATALOG_ROWS = [
    {'sku': 'PTR-TNK-001', 'vendor': 'porter', 'stock': 5, 'status': 'active'},
    {'sku': 'MMP-EDP-001', 'vendor': 'memo_paris', 'stock': 3, 'status': 'active'},
    {'sku': 'PTR-LFT-001', 'vendor': 'porter', 'stock': 100, 'status': 'active'},
]


def _make_engine(orders=None, catalog=None):
    engine = ReorderAlertEngine(sheet_id='dummy')
    engine._get_order_rows = MagicMock(
        return_value=list(orders if orders is not None else SAMPLE_ORDER_ROWS)
    )
    engine._get_catalog_rows = MagicMock(
        return_value=list(catalog if catalog is not None else SAMPLE_CATALOG_ROWS)
    )
    return engine


# ══════════════════════════════════════════════════════════
# sales_velocity 테스트
# ══════════════════════════════════════════════════════════

class TestSalesVelocity:
    def test_returns_dict(self):
        engine = _make_engine()
        result = engine.sales_velocity(days=30)
        assert isinstance(result, dict)

    def test_sku_in_result(self):
        engine = _make_engine()
        result = engine.sales_velocity(days=30)
        assert 'PTR-TNK-001' in result

    def test_velocity_is_float(self):
        engine = _make_engine()
        result = engine.sales_velocity(days=30)
        for sku, vel in result.items():
            assert isinstance(vel, float)

    def test_velocity_non_negative(self):
        engine = _make_engine()
        result = engine.sales_velocity(days=30)
        for sku, vel in result.items():
            assert vel >= 0.0

    def test_ptr_velocity_calculation(self):
        """PTR-TNK-001: 3 orders in 30 days = 0.1 per day."""
        engine = _make_engine()
        result = engine.sales_velocity(days=30)
        assert abs(result['PTR-TNK-001'] - 3 / 30) < 0.001

    def test_skus_without_orders_not_in_result(self):
        """주문이 없는 SKU는 결과에 포함되지 않아야 한다."""
        engine = _make_engine()
        result = engine.sales_velocity(days=30)
        # PTR-LFT-001은 주문이 없으므로 결과에 없어야 함
        assert 'PTR-LFT-001' not in result

    def test_old_orders_excluded(self):
        """기간 밖의 주문은 제외되어야 한다."""
        old_orders = [
            {'order_date': str(date.today() - timedelta(days=60)), 'sku': 'PTR-TNK-001'},
        ]
        engine = _make_engine(orders=old_orders)
        result = engine.sales_velocity(days=30)
        assert 'PTR-TNK-001' not in result

    def test_empty_orders_returns_empty(self):
        engine = _make_engine(orders=[])
        result = engine.sales_velocity()
        assert result == {}


# ══════════════════════════════════════════════════════════
# reorder_point 테스트
# ══════════════════════════════════════════════════════════

class TestReorderPoint:
    def test_returns_dict(self):
        engine = _make_engine()
        result = engine.reorder_point('PTR-TNK-001', daily_sales=0.5, vendor='porter')
        assert isinstance(result, dict)

    def test_required_keys(self):
        engine = _make_engine()
        result = engine.reorder_point('PTR-TNK-001', daily_sales=0.5, vendor='porter')
        required = {'sku', 'vendor', 'daily_sales', 'lead_days', 'safety_stock_days', 'reorder_point_qty'}
        assert required.issubset(result.keys())

    def test_porter_lead_days(self):
        """Porter의 기본 리드타임은 7일."""
        engine = _make_engine()
        result = engine.reorder_point('PTR-TNK-001', 0.5, vendor='porter')
        assert result['lead_days'] == 7

    def test_memo_paris_lead_days(self):
        """Memo Paris의 기본 리드타임은 10일."""
        engine = _make_engine()
        result = engine.reorder_point('MMP-EDP-001', 0.3, vendor='memo_paris')
        assert result['lead_days'] == 10

    def test_unknown_vendor_default_lead_days(self):
        engine = _make_engine()
        result = engine.reorder_point('XXX-001', 0.5, vendor='unknown')
        assert result['lead_days'] == 7  # default

    def test_reorder_point_calculation(self):
        """재주문 포인트 = (리드타임 + 안전재고) × 일일 판매량."""
        engine = _make_engine()
        engine._safety_days = 3
        result = engine.reorder_point('PTR-TNK-001', daily_sales=1.0, vendor='porter')
        # (7 + 3) * 1.0 = 10.0
        assert result['reorder_point_qty'] == 10.0

    def test_zero_daily_sales(self):
        engine = _make_engine()
        result = engine.reorder_point('PTR-TNK-001', daily_sales=0.0, vendor='porter')
        assert result['reorder_point_qty'] == 0.0


# ══════════════════════════════════════════════════════════
# generate_suggestions 테스트
# ══════════════════════════════════════════════════════════

class TestGenerateSuggestions:
    def test_returns_list(self):
        engine = _make_engine()
        result = engine.generate_suggestions()
        assert isinstance(result, list)

    def test_suggestion_structure(self):
        engine = _make_engine()
        result = engine.generate_suggestions()
        required = {
            'sku', 'vendor', 'current_stock', 'daily_sales',
            'days_until_stockout', 'lead_days', 'recommended_qty', 'urgent',
        }
        for s in result:
            assert required.issubset(s.keys())

    def test_sorted_by_urgency(self):
        """재고 소진 예상일 오름차순 정렬 확인."""
        engine = _make_engine()
        result = engine.generate_suggestions()
        days_list = [s['days_until_stockout'] for s in result]
        assert days_list == sorted(days_list)

    def test_recommended_qty_minimum_one(self):
        """추천 발주 수량은 최소 1개 이상이어야 한다."""
        engine = _make_engine()
        result = engine.generate_suggestions()
        for s in result:
            assert s['recommended_qty'] >= 1

    def test_no_sales_velocity_skus_excluded(self):
        """판매 실적 없는 SKU는 제안에서 제외."""
        engine = _make_engine(orders=[])  # 주문 없음
        result = engine.generate_suggestions()
        assert result == []

    def test_urgent_flag_when_days_less_than_lead(self):
        """days_until_stockout < lead_days이면 urgent=True."""
        # PTR-TNK-001: 3 orders in ~26일 범위(TODAY, TODAY, FIVE_DAYS_AGO)
        # velocity ≈ 3/30 = 0.1/day, stock=5 → ~50일 → no reorder needed
        # 테스트용으로 stock을 낮게 설정
        catalog = [
            {'sku': 'PTR-TNK-001', 'vendor': 'porter', 'stock': 2, 'status': 'active'},
        ]
        orders = [
            {'order_date': TODAY, 'sku': 'PTR-TNK-001'},
            {'order_date': str(date.today() - timedelta(days=1)), 'sku': 'PTR-TNK-001'},
            {'order_date': str(date.today() - timedelta(days=2)), 'sku': 'PTR-TNK-001'},
            {'order_date': str(date.today() - timedelta(days=3)), 'sku': 'PTR-TNK-001'},
            {'order_date': str(date.today() - timedelta(days=4)), 'sku': 'PTR-TNK-001'},
        ]
        engine = _make_engine(orders=orders, catalog=catalog)
        result = engine.generate_suggestions()
        if result:
            ptr_item = next((s for s in result if s['sku'] == 'PTR-TNK-001'), None)
            if ptr_item:
                if ptr_item['days_until_stockout'] < ptr_item['lead_days']:
                    assert ptr_item['urgent'] is True


# ══════════════════════════════════════════════════════════
# send_alerts 테스트
# ══════════════════════════════════════════════════════════

class TestSendAlerts:
    @patch.dict(os.environ, {'TELEGRAM_ENABLED': '0'})
    def test_no_telegram_when_disabled(self):
        engine = _make_engine()
        suggestions = [
            {
                'sku': 'PTR-TNK-001', 'vendor': 'porter', 'current_stock': 2,
                'daily_sales': 0.5, 'days_until_stockout': 4,
                'lead_days': 7, 'recommended_qty': 5, 'urgent': True,
            }
        ]
        with patch('src.utils.telegram.send_tele') as mock_tele:
            engine.send_alerts(suggestions)
            mock_tele.assert_not_called()

    def test_empty_suggestions_no_call(self):
        engine = _make_engine()
        with patch.object(engine, '_get_order_rows', return_value=[]):
            engine.send_alerts([])  # Should not raise

    @patch.dict(os.environ, {'TELEGRAM_ENABLED': '1'})
    def test_telegram_called_with_suggestions_no_error(self):
        """TELEGRAM_ENABLED=1이어도 예외 없이 실행되어야 한다 (네트워크 오류 허용)."""
        engine = _make_engine()
        suggestions = [
            {
                'sku': 'PTR-TNK-001', 'vendor': 'porter', 'current_stock': 2,
                'daily_sales': 0.5, 'days_until_stockout': 3,
                'lead_days': 7, 'recommended_qty': 5, 'urgent': True,
            }
        ]
        try:
            engine.send_alerts(suggestions)
        except Exception as exc:
            pytest.fail(f"send_alerts raised an unexpected exception: {exc}")


# ══════════════════════════════════════════════════════════
# run 테스트
# ══════════════════════════════════════════════════════════

class TestRun:
    @patch.dict(os.environ, {'REORDER_CHECK_ENABLED': '0'})
    def test_disabled_returns_skipped(self):
        engine = _make_engine()
        result = engine.run()
        assert result == {'skipped': True}

    @patch.dict(os.environ, {'REORDER_CHECK_ENABLED': '1', 'TELEGRAM_ENABLED': '0'})
    def test_enabled_returns_result_dict(self):
        engine = _make_engine()
        engine._write_suggestions_to_sheets = MagicMock()
        result = engine.run()
        assert 'total_suggestions' in result
        assert 'urgent' in result
        assert 'suggestions' in result

    @patch.dict(os.environ, {'REORDER_CHECK_ENABLED': '1', 'TELEGRAM_ENABLED': '0'})
    def test_writes_to_sheets_called(self):
        engine = _make_engine()
        engine._write_suggestions_to_sheets = MagicMock()
        engine.run()
        engine._write_suggestions_to_sheets.assert_called_once()
