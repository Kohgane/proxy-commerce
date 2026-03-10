"""tests/test_inventory.py — Phase 4-2 재고 자동 동기화 테스트"""
import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ──────────────────────────────────────────────────────────
# 공통 픽스처
# ──────────────────────────────────────────────────────────

CATALOG_ROWS = [
    {
        'sku': 'PTR-TNK-001',
        'title_ko': '포터 탱커 가방',
        'title_en': 'Porter Tanker Bag',
        'src_url': 'https://www.yoshidakaban.com/product/100000.html',
        'buy_currency': 'JPY',
        'buy_price': 15000,
        'stock': 5,
        'stock_status': 'in_stock',
        'vendor': 'porter',
        'status': 'active',
        'price_history': '',
        'last_stock_check': '',
    },
    {
        'sku': 'MMP-PER-003',
        'title_ko': '메모파리 향수',
        'title_en': 'Memo Paris Perfume',
        'src_url': 'https://www.memoparis.com/products/perfume-001',
        'buy_currency': 'EUR',
        'buy_price': 120,
        'stock': 3,
        'stock_status': 'in_stock',
        'vendor': 'memo_paris',
        'status': 'active',
        'price_history': '',
        'last_stock_check': '',
    },
    {
        'sku': 'PTR-WAL-005',
        'title_ko': '포터 지갑',
        'title_en': 'Porter Wallet',
        'src_url': 'https://www.yoshidakaban.com/product/200000.html',
        'buy_currency': 'JPY',
        'buy_price': 8000,
        'stock': 0,
        'stock_status': 'out_of_stock',
        'vendor': 'porter',
        'status': 'active',
        'price_history': '',
        'last_stock_check': '',
    },
]

PORTER_IN_STOCK_HTML = """
<html><body>
<h1>Porter Tanker Bag</h1>
<span class="price">¥15,000</span>
<button>カートに入れる</button>
</body></html>
"""

PORTER_OUT_OF_STOCK_HTML = """
<html><body>
<h1>Porter Wallet</h1>
<span class="price">¥8,000</span>
<p>売り切れ</p>
</body></html>
"""

MEMO_IN_STOCK_HTML = """
<html><body>
<h1>Memo Paris Perfume</h1>
<span class="price">€120.00</span>
<button>Add to bag</button>
</body></html>
"""

MEMO_OUT_OF_STOCK_HTML = """
<html><body>
<h1>Memo Paris Perfume</h1>
<p>Out of stock</p>
</body></html>
"""


# ══════════════════════════════════════════════════════════
# StockChecker テスト
# ══════════════════════════════════════════════════════════

class TestStockCheckerPorter:
    def _make_checker(self):
        from src.inventory.stock_checker import StockChecker
        return StockChecker()

    def test_porter_in_stock(self):
        checker = self._make_checker()
        with patch.object(checker, '_fetch_html', return_value=PORTER_IN_STOCK_HTML):
            result = checker.check_single('PTR-TNK-001', 'https://example.com', 'porter')
        assert result['status'] == 'in_stock'
        assert result['sku'] == 'PTR-TNK-001'
        assert result['vendor'] == 'porter'

    def test_porter_out_of_stock(self):
        checker = self._make_checker()
        with patch.object(checker, '_fetch_html', return_value=PORTER_OUT_OF_STOCK_HTML):
            result = checker.check_single('PTR-WAL-005', 'https://example.com', 'porter')
        assert result['status'] == 'out_of_stock'

    def test_porter_price_extracted(self):
        checker = self._make_checker()
        with patch.object(checker, '_fetch_html', return_value=PORTER_IN_STOCK_HTML):
            result = checker.check_single('PTR-TNK-001', 'https://example.com', 'porter')
        assert result['current_price'] == Decimal('15000')

    def test_porter_timeout_returns_unknown(self):
        checker = self._make_checker()
        with patch.object(checker, '_fetch_html', return_value=None):
            result = checker.check_single('PTR-TNK-001', 'https://example.com', 'porter')
        assert result['status'] == 'unknown'

    def test_porter_exception_returns_unknown(self):
        checker = self._make_checker()
        with patch.object(checker, '_fetch_html', side_effect=Exception("network error")):
            result = checker.check_single('PTR-TNK-001', 'https://example.com', 'porter')
        assert result['status'] == 'unknown'
        assert result['sku'] == 'PTR-TNK-001'

    def test_porter_checked_at_present(self):
        checker = self._make_checker()
        with patch.object(checker, '_fetch_html', return_value=PORTER_IN_STOCK_HTML):
            result = checker.check_single('PTR-TNK-001', 'https://example.com', 'porter')
        assert 'checked_at' in result
        assert result['checked_at']


class TestStockCheckerMemo:
    def _make_checker(self):
        from src.inventory.stock_checker import StockChecker
        return StockChecker()

    def test_memo_in_stock(self):
        checker = self._make_checker()
        with patch.object(checker, '_fetch_html', return_value=MEMO_IN_STOCK_HTML):
            result = checker.check_single('MMP-PER-003', 'https://example.com', 'memo_paris')
        assert result['status'] == 'in_stock'

    def test_memo_out_of_stock(self):
        checker = self._make_checker()
        with patch.object(checker, '_fetch_html', return_value=MEMO_OUT_OF_STOCK_HTML):
            result = checker.check_single('MMP-PER-003', 'https://example.com', 'memo_paris')
        assert result['status'] == 'out_of_stock'

    def test_memo_price_extracted(self):
        checker = self._make_checker()
        with patch.object(checker, '_fetch_html', return_value=MEMO_IN_STOCK_HTML):
            result = checker.check_single('MMP-PER-003', 'https://example.com', 'memo_paris')
        assert result['current_price'] == Decimal('120.00')

    def test_memo_unknown_vendor_returns_unknown(self):
        checker = self._make_checker()
        result = checker.check_single('XYZ-001', 'https://example.com', 'unknown_vendor')
        assert result['status'] == 'unknown'

    def test_memo_no_pattern_match_returns_unknown(self):
        checker = self._make_checker()
        with patch.object(checker, '_fetch_html', return_value="<html>no match here</html>"):
            result = checker.check_single('MMP-PER-003', 'https://example.com', 'memo_paris')
        assert result['status'] == 'unknown'


class TestStockCheckerBatch:
    def _make_checker(self):
        from src.inventory.stock_checker import StockChecker
        return StockChecker()

    def test_batch_returns_all_results(self):
        checker = self._make_checker()
        inputs = [
            {'sku': 'PTR-TNK-001', 'src_url': 'https://p1.com', 'vendor': 'porter'},
            {'sku': 'PTR-WAL-005', 'src_url': 'https://p2.com', 'vendor': 'porter'},
            {'sku': 'MMP-PER-003', 'src_url': 'https://m1.com', 'vendor': 'memo_paris'},
        ]
        side_effects = [PORTER_IN_STOCK_HTML, PORTER_OUT_OF_STOCK_HTML, MEMO_IN_STOCK_HTML]
        with patch.object(checker, '_fetch_html', side_effect=side_effects):
            with patch('src.inventory.stock_checker.time'):
                results = checker.check_batch(inputs)
        assert len(results) == 3

    def test_batch_respects_delay(self):
        checker = self._make_checker()
        inputs = [
            {'sku': 'PTR-TNK-001', 'src_url': 'https://p1.com', 'vendor': 'porter'},
            {'sku': 'PTR-WAL-005', 'src_url': 'https://p2.com', 'vendor': 'porter'},
        ]
        with patch.object(checker, '_fetch_html', return_value=PORTER_IN_STOCK_HTML):
            with patch('src.inventory.stock_checker.time') as mock_time:
                checker.check_batch(inputs)
                assert mock_time.sleep.called

    def test_batch_empty_input(self):
        checker = self._make_checker()
        results = checker.check_batch([])
        assert results == []

    def test_batch_statuses(self):
        checker = self._make_checker()
        inputs = [
            {'sku': 'PTR-TNK-001', 'src_url': 'https://p1.com', 'vendor': 'porter'},
            {'sku': 'PTR-WAL-005', 'src_url': 'https://p2.com', 'vendor': 'porter'},
        ]
        with patch.object(checker, '_fetch_html', side_effect=[PORTER_IN_STOCK_HTML, PORTER_OUT_OF_STOCK_HTML]):
            with patch('src.inventory.stock_checker.time'):
                results = checker.check_batch(inputs)
        assert results[0]['status'] == 'in_stock'
        assert results[1]['status'] == 'out_of_stock'


class TestPriceChangeDetection:
    def _make_checker(self):
        from src.inventory.stock_checker import StockChecker
        return StockChecker()

    def test_price_changed_flag_present(self):
        checker = self._make_checker()
        with patch.object(checker, '_fetch_html', return_value=PORTER_IN_STOCK_HTML):
            result = checker.check_single('PTR-TNK-001', 'https://example.com', 'porter')
        assert 'price_changed' in result

    def test_current_price_none_on_no_price_in_html(self):
        checker = self._make_checker()
        html_no_price = "<html><body>カートに入れる</body></html>"
        with patch.object(checker, '_fetch_html', return_value=html_no_price):
            result = checker.check_single('PTR-TNK-001', 'https://example.com', 'porter')
        assert result['current_price'] is None


# ══════════════════════════════════════════════════════════
# InventorySync テスト
# ══════════════════════════════════════════════════════════

class TestInventorySync:
    def _make_syncer(self, rows=None):
        from src.inventory.inventory_sync import InventorySync
        syncer = InventorySync(sheet_id='dummy', worksheet='catalog')
        syncer._get_active_rows = MagicMock(return_value=list(rows if rows is not None else CATALOG_ROWS))
        syncer.alert_manager = MagicMock()
        return syncer

    def _mock_check_batch(self, statuses: list):
        """check_batch 결과를 직접 반환하는 mock 생성."""
        return statuses

    # ── full_sync ──────────────────────────────────────────

    def test_full_sync_returns_result_dict(self):
        syncer = self._make_syncer()
        syncer.checker.check_batch = MagicMock(return_value=[
            {'sku': r['sku'], 'status': 'in_stock', 'quantity': None,
             'price_changed': False, 'current_price': None, 'vendor': r['vendor'],
             'checked_at': '2026-03-09T17:00:00+00:00'}
            for r in CATALOG_ROWS
        ])
        result = syncer.full_sync(dry_run=True)
        assert 'total_checked' in result
        assert 'changes' in result
        assert 'dry_run' in result
        assert result['dry_run'] is True

    def test_full_sync_detects_out_of_stock(self):
        syncer = self._make_syncer()
        # PTR-TNK-001: was in_stock → now out_of_stock
        checked = [
            {'sku': 'PTR-TNK-001', 'status': 'out_of_stock', 'quantity': 0,
             'price_changed': False, 'current_price': None, 'vendor': 'porter',
             'checked_at': '2026-03-09T17:00:00+00:00'},
            {'sku': 'MMP-PER-003', 'status': 'in_stock', 'quantity': 3,
             'price_changed': False, 'current_price': None, 'vendor': 'memo_paris',
             'checked_at': '2026-03-09T17:00:00+00:00'},
            {'sku': 'PTR-WAL-005', 'status': 'out_of_stock', 'quantity': 0,
             'price_changed': False, 'current_price': None, 'vendor': 'porter',
             'checked_at': '2026-03-09T17:00:00+00:00'},
        ]
        syncer.checker.check_batch = MagicMock(return_value=checked)
        result = syncer.full_sync(dry_run=True)
        oos_changes = [c for c in result['changes'] if c['change'] == 'out_of_stock']
        assert any(c['sku'] == 'PTR-TNK-001' for c in oos_changes)

    def test_full_sync_detects_restock(self):
        syncer = self._make_syncer()
        # PTR-WAL-005: was out_of_stock → now in_stock
        checked = [
            {'sku': 'PTR-TNK-001', 'status': 'in_stock', 'quantity': 5,
             'price_changed': False, 'current_price': None, 'vendor': 'porter',
             'checked_at': '2026-03-09T17:00:00+00:00'},
            {'sku': 'MMP-PER-003', 'status': 'in_stock', 'quantity': 3,
             'price_changed': False, 'current_price': None, 'vendor': 'memo_paris',
             'checked_at': '2026-03-09T17:00:00+00:00'},
            {'sku': 'PTR-WAL-005', 'status': 'in_stock', 'quantity': 5,
             'price_changed': False, 'current_price': Decimal('8000'), 'vendor': 'porter',
             'checked_at': '2026-03-09T17:00:00+00:00'},
        ]
        syncer.checker.check_batch = MagicMock(return_value=checked)
        result = syncer.full_sync(dry_run=True)
        restock_changes = [c for c in result['changes'] if c['change'] == 'restock']
        assert any(c['sku'] == 'PTR-WAL-005' for c in restock_changes)

    def test_full_sync_detects_price_change(self):
        syncer = self._make_syncer()
        # PTR-TNK-001: price 15000 → 14000 (6.7% drop > 5% threshold)
        checked = [
            {'sku': 'PTR-TNK-001', 'status': 'in_stock', 'quantity': 5,
             'price_changed': False, 'current_price': Decimal('14000'), 'vendor': 'porter',
             'checked_at': '2026-03-09T17:00:00+00:00'},
            {'sku': 'MMP-PER-003', 'status': 'in_stock', 'quantity': 3,
             'price_changed': False, 'current_price': None, 'vendor': 'memo_paris',
             'checked_at': '2026-03-09T17:00:00+00:00'},
            {'sku': 'PTR-WAL-005', 'status': 'out_of_stock', 'quantity': 0,
             'price_changed': False, 'current_price': None, 'vendor': 'porter',
             'checked_at': '2026-03-09T17:00:00+00:00'},
        ]
        syncer.checker.check_batch = MagicMock(return_value=checked)
        result = syncer.full_sync(dry_run=True)
        price_changes = [c for c in result['changes'] if c['change'] == 'price_changed']
        assert any(c['sku'] == 'PTR-TNK-001' for c in price_changes)

    def test_full_sync_dry_run_no_updates(self):
        syncer = self._make_syncer()
        syncer.update_catalog_stock = MagicMock(return_value=True)
        syncer.update_shopify_stock = MagicMock(return_value=True)
        syncer.update_woo_stock = MagicMock(return_value=True)
        checked = [
            {'sku': r['sku'], 'status': 'out_of_stock', 'quantity': 0,
             'price_changed': False, 'current_price': None, 'vendor': r['vendor'],
             'checked_at': '2026-03-09T17:00:00+00:00'}
            for r in CATALOG_ROWS
        ]
        syncer.checker.check_batch = MagicMock(return_value=checked)
        syncer.full_sync(dry_run=True)
        syncer.update_catalog_stock.assert_not_called()
        syncer.update_shopify_stock.assert_not_called()
        syncer.update_woo_stock.assert_not_called()

    def test_full_sync_calls_update_on_change(self):
        syncer = self._make_syncer()
        syncer.update_catalog_stock = MagicMock(return_value=True)
        syncer.update_shopify_stock = MagicMock(return_value=True)
        syncer.update_woo_stock = MagicMock(return_value=True)
        # PTR-TNK-001 goes out of stock
        checked = [
            {'sku': 'PTR-TNK-001', 'status': 'out_of_stock', 'quantity': 0,
             'price_changed': False, 'current_price': None, 'vendor': 'porter',
             'checked_at': '2026-03-09T17:00:00+00:00'},
            {'sku': 'MMP-PER-003', 'status': 'in_stock', 'quantity': 3,
             'price_changed': False, 'current_price': None, 'vendor': 'memo_paris',
             'checked_at': '2026-03-09T17:00:00+00:00'},
            {'sku': 'PTR-WAL-005', 'status': 'out_of_stock', 'quantity': 0,
             'price_changed': False, 'current_price': None, 'vendor': 'porter',
             'checked_at': '2026-03-09T17:00:00+00:00'},
        ]
        syncer.checker.check_batch = MagicMock(return_value=checked)
        syncer.full_sync(dry_run=False)
        # PTR-TNK-001 changed (in_stock → out_of_stock)
        syncer.update_catalog_stock.assert_any_call(
            'PTR-TNK-001', 'out_of_stock', quantity=0, price=None)

    def test_full_sync_alerts_on_out_of_stock(self):
        syncer = self._make_syncer()
        syncer.update_catalog_stock = MagicMock(return_value=True)
        syncer.update_shopify_stock = MagicMock(return_value=False)
        syncer.update_woo_stock = MagicMock(return_value=False)
        checked = [
            {'sku': 'PTR-TNK-001', 'status': 'out_of_stock', 'quantity': 0,
             'price_changed': False, 'current_price': None, 'vendor': 'porter',
             'checked_at': '2026-03-09T17:00:00+00:00'},
            {'sku': 'MMP-PER-003', 'status': 'in_stock', 'quantity': 3,
             'price_changed': False, 'current_price': None, 'vendor': 'memo_paris',
             'checked_at': '2026-03-09T17:00:00+00:00'},
            {'sku': 'PTR-WAL-005', 'status': 'out_of_stock', 'quantity': 0,
             'price_changed': False, 'current_price': None, 'vendor': 'porter',
             'checked_at': '2026-03-09T17:00:00+00:00'},
        ]
        syncer.checker.check_batch = MagicMock(return_value=checked)
        syncer.full_sync(dry_run=False)
        syncer.alert_manager.notify_out_of_stock.assert_called_once()

    def test_full_sync_no_change_no_alert(self):
        syncer = self._make_syncer()
        # All statuses match existing catalog
        checked = [
            {'sku': 'PTR-TNK-001', 'status': 'in_stock', 'quantity': 5,
             'price_changed': False, 'current_price': None, 'vendor': 'porter',
             'checked_at': '2026-03-09T17:00:00+00:00'},
            {'sku': 'MMP-PER-003', 'status': 'in_stock', 'quantity': 3,
             'price_changed': False, 'current_price': None, 'vendor': 'memo_paris',
             'checked_at': '2026-03-09T17:00:00+00:00'},
            {'sku': 'PTR-WAL-005', 'status': 'out_of_stock', 'quantity': 0,
             'price_changed': False, 'current_price': None, 'vendor': 'porter',
             'checked_at': '2026-03-09T17:00:00+00:00'},
        ]
        syncer.checker.check_batch = MagicMock(return_value=checked)
        result = syncer.full_sync(dry_run=False)
        assert result['changes'] == []
        syncer.alert_manager.notify_out_of_stock.assert_not_called()

    def test_full_sync_catalog_load_error(self):
        syncer = self._make_syncer()
        syncer._get_active_rows = MagicMock(side_effect=RuntimeError("Sheets error"))
        result = syncer.full_sync(dry_run=True)
        assert len(result['errors']) > 0

    # ── sync_single ────────────────────────────────────────

    def test_sync_single_sku_found(self):
        syncer = self._make_syncer()
        syncer.checker.check_single = MagicMock(return_value={
            'sku': 'PTR-TNK-001', 'status': 'out_of_stock', 'quantity': 0,
            'price_changed': False, 'current_price': None, 'vendor': 'porter',
            'checked_at': '2026-03-09T17:00:00+00:00',
        })
        result = syncer.sync_single('PTR-TNK-001', dry_run=True)
        assert result['sku'] == 'PTR-TNK-001'
        assert result['checked']['status'] == 'out_of_stock'

    def test_sync_single_sku_not_found(self):
        syncer = self._make_syncer()
        result = syncer.sync_single('UNKNOWN-SKU', dry_run=True)
        assert 'error' in result

    # ── update_catalog_stock ───────────────────────────────

    def test_update_catalog_stock_calls_open_sheet(self):
        from src.inventory.inventory_sync import InventorySync
        syncer = InventorySync(sheet_id='dummy', worksheet='catalog')
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = [
            {'sku': 'PTR-TNK-001', 'stock_status': 'in_stock', 'stock': 5,
             'last_stock_check': '', 'buy_price': '15000', 'price_history': ''}
        ]
        mock_ws.row_values.return_value = [
            'sku', 'stock_status', 'stock', 'last_stock_check', 'buy_price', 'price_history'
        ]
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = syncer.update_catalog_stock('PTR-TNK-001', 'out_of_stock', quantity=0)
        assert result is True
        mock_ws.update_cell.assert_called()

    def test_update_catalog_stock_sku_not_found(self):
        from src.inventory.inventory_sync import InventorySync
        syncer = InventorySync(sheet_id='dummy', worksheet='catalog')
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = []
        mock_ws.row_values.return_value = ['sku', 'stock_status']
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = syncer.update_catalog_stock('UNKNOWN', 'out_of_stock')
        assert result is False

    def test_update_catalog_stock_exception_returns_false(self):
        from src.inventory.inventory_sync import InventorySync
        syncer = InventorySync(sheet_id='dummy', worksheet='catalog')
        with patch('src.inventory.inventory_sync.open_sheet', side_effect=RuntimeError("Sheets error")):
            result = syncer.update_catalog_stock('PTR-TNK-001', 'out_of_stock')
        assert result is False

    # ── update_shopify_stock ───────────────────────────────

    def test_update_shopify_stock_no_credentials(self):
        from src.inventory.inventory_sync import InventorySync
        syncer = InventorySync(sheet_id='dummy', worksheet='catalog')
        with patch.dict(os.environ, {}, clear=True):
            result = syncer.update_shopify_stock('PTR-TNK-001', 5)
        assert result is False

    def test_update_shopify_stock_sku_not_found(self):
        from src.inventory.inventory_sync import InventorySync
        syncer = InventorySync(sheet_id='dummy', worksheet='catalog')
        with patch.dict(os.environ, {'SHOPIFY_ACCESS_TOKEN': 'tok', 'SHOPIFY_SHOP': 'store.myshopify.com'}):
            with patch('src.vendors.shopify_client._find_by_sku', return_value=None):
                result = syncer.update_shopify_stock('UNKNOWN', 5)
        assert result is False

    # ── update_woo_stock ───────────────────────────────────

    def test_update_woo_stock_no_credentials(self):
        from src.inventory.inventory_sync import InventorySync
        syncer = InventorySync(sheet_id='dummy', worksheet='catalog')
        with patch.dict(os.environ, {}, clear=True):
            result = syncer.update_woo_stock('PTR-TNK-001', 5)
        assert result is False

    def test_update_woo_stock_sku_not_found(self):
        from src.inventory.inventory_sync import InventorySync
        syncer = InventorySync(sheet_id='dummy', worksheet='catalog')
        with patch.dict(os.environ, {
            'WOO_CK': 'ck', 'WOO_CS': 'cs', 'WOO_BASE_URL': 'https://example.com'
        }):
            with patch('src.vendors.woocommerce_client._find_by_sku', return_value=None):
                result = syncer.update_woo_stock('UNKNOWN', 5)
        assert result is False

    # ── get_sync_report ────────────────────────────────────

    def test_get_sync_report_empty_before_sync(self):
        from src.inventory.inventory_sync import InventorySync
        syncer = InventorySync(sheet_id='dummy', worksheet='catalog')
        report = syncer.get_sync_report()
        assert report == {}

    def test_get_sync_report_after_sync(self):
        syncer = self._make_syncer()
        syncer.checker.check_batch = MagicMock(return_value=[])
        syncer.full_sync(dry_run=True)
        report = syncer.get_sync_report()
        assert 'total_checked' in report


# ══════════════════════════════════════════════════════════
# StockAlertManager テスト
# ══════════════════════════════════════════════════════════

class TestStockAlertManager:
    def _make_manager(self):
        from src.inventory.stock_alerts import StockAlertManager
        return StockAlertManager()

    def test_notify_out_of_stock_sends_telegram(self):
        manager = self._make_manager()
        products = [
            {'sku': 'PTR-TNK-001', 'title': '포터 탱커 가방', 'vendor': 'porter'},
            {'sku': 'MMP-PER-003', 'title': '메모파리 향수', 'vendor': 'memo_paris'},
        ]
        with patch('src.inventory.stock_alerts.send_tele') as mock_tele, \
             patch('src.inventory.stock_alerts.send_mail'):
            manager.notify_out_of_stock(products)
            mock_tele.assert_called_once()
            msg = mock_tele.call_args[0][0]
            assert '🚫' in msg
            assert '품절' in msg
            assert 'PTR-TNK-001' in msg

    def test_notify_restock_sends_telegram(self):
        manager = self._make_manager()
        products = [
            {'sku': 'PTR-TNK-001', 'title': '포터 탱커 가방', 'quantity': 5},
        ]
        with patch('src.inventory.stock_alerts.send_tele') as mock_tele, \
             patch('src.inventory.stock_alerts.send_mail'):
            manager.notify_restock(products)
            mock_tele.assert_called_once()
            msg = mock_tele.call_args[0][0]
            assert '📦' in msg
            assert '재입고' in msg

    def test_notify_price_change_sends_telegram(self):
        manager = self._make_manager()
        products = [
            {'sku': 'PTR-TNK-001', 'title': '포터 탱커 가방',
             'old_price': '15000', 'new_price': '14500', 'currency': 'JPY'},
        ]
        with patch('src.inventory.stock_alerts.send_tele') as mock_tele, \
             patch('src.inventory.stock_alerts.send_mail'):
            manager.notify_price_change(products)
            mock_tele.assert_called_once()
            msg = mock_tele.call_args[0][0]
            assert '💰' in msg
            assert '가격 변동' in msg

    def test_notify_out_of_stock_empty_list(self):
        manager = self._make_manager()
        with patch('src.inventory.stock_alerts.send_tele') as mock_tele, \
             patch('src.inventory.stock_alerts.send_mail'):
            manager.notify_out_of_stock([])
            mock_tele.assert_not_called()

    def test_notify_restock_empty_list(self):
        manager = self._make_manager()
        with patch('src.inventory.stock_alerts.send_tele') as mock_tele, \
             patch('src.inventory.stock_alerts.send_mail'):
            manager.notify_restock([])
            mock_tele.assert_not_called()

    def test_send_sync_summary_sends_telegram(self):
        manager = self._make_manager()
        sync_result = {
            'total_checked': 50,
            'changes': [
                {'sku': 'PTR-TNK-001', 'change': 'out_of_stock'},
                {'sku': 'MMP-PER-003', 'change': 'restock'},
                {'sku': 'PTR-WAL-005', 'change': 'price_changed'},
            ],
            'shopify_updated': 5,
            'woo_updated': 5,
        }
        with patch('src.inventory.stock_alerts.send_tele') as mock_tele, \
             patch('src.inventory.stock_alerts.send_mail'):
            manager.send_sync_summary(sync_result)
            mock_tele.assert_called_once()
            msg = mock_tele.call_args[0][0]
            assert '✅' in msg
            assert '50' in msg

    def test_telegram_failure_does_not_raise(self):
        manager = self._make_manager()
        products = [{'sku': 'PTR-TNK-001', 'title': 'test', 'vendor': 'porter'}]
        with patch('src.inventory.stock_alerts.send_tele', side_effect=Exception("network error")), \
             patch('src.inventory.stock_alerts.send_mail'):
            manager.notify_out_of_stock(products)  # should not raise

    def test_price_change_shows_percentage(self):
        manager = self._make_manager()
        products = [
            {'sku': 'PTR-TNK-001', 'title': '포터 탱커',
             'old_price': '15000', 'new_price': '14000', 'currency': 'JPY'},
        ]
        with patch('src.inventory.stock_alerts.send_tele') as mock_tele, \
             patch('src.inventory.stock_alerts.send_mail'):
            manager.notify_price_change(products)
            msg = mock_tele.call_args[0][0]
            assert '%' in msg


# ══════════════════════════════════════════════════════════
# CLI テスト
# ══════════════════════════════════════════════════════════

class TestInventoryCLI:
    def _run_cli(self, args):
        """CLI를 subprocess로 실행하고 결과 반환."""
        import subprocess
        cmd = [sys.executable, '-m', 'src.inventory.cli'] + args
        proc = subprocess.run(
            cmd,
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), '..'),
        )
        return proc

    def test_cli_full_sync_dry_run(self):
        import argparse
        import io
        from contextlib import redirect_stdout
        from src.inventory.cli import cmd_full_sync

        args = argparse.Namespace(dry_run=True, vendor=None)
        mock_syncer = MagicMock()
        mock_syncer.full_sync.return_value = {
            'total_checked': 0, 'changes': [], 'shopify_updated': 0,
            'woo_updated': 0, 'sheets_updated': 0, 'errors': [], 'dry_run': True,
        }
        with patch('src.inventory.cli.InventorySync', return_value=mock_syncer):
            f = io.StringIO()
            with redirect_stdout(f):
                cmd_full_sync(args)
            output = f.getvalue()
        assert 'dry_run' in output

    def test_cli_check_missing_sku(self):
        import argparse
        from src.inventory.cli import cmd_check
        args = argparse.Namespace(sku=None, dry_run=False)
        with pytest.raises(SystemExit):
            cmd_check(args)

    def test_cli_report_no_result(self):
        import argparse
        import io
        from contextlib import redirect_stdout
        from src.inventory.cli import cmd_report

        args = argparse.Namespace()
        mock_syncer = MagicMock()
        mock_syncer.get_sync_report.return_value = {}
        with patch('src.inventory.cli.InventorySync', return_value=mock_syncer):
            f = io.StringIO()
            with redirect_stdout(f):
                cmd_report(args)
        assert 'No sync report' in f.getvalue()

    def test_cli_report_with_result(self):
        import argparse
        import io
        from contextlib import redirect_stdout
        from src.inventory.cli import cmd_report

        args = argparse.Namespace()
        mock_syncer = MagicMock()
        mock_syncer.get_sync_report.return_value = {
            'total_checked': 10, 'changes': [], 'dry_run': False
        }
        with patch('src.inventory.cli.InventorySync', return_value=mock_syncer):
            f = io.StringIO()
            with redirect_stdout(f):
                cmd_report(args)
        assert 'total_checked' in f.getvalue()


# ══════════════════════════════════════════════════════════
# E2E 시나리오 — 벤더 재고 변동 → 카탈로그/스토어 반영
# ══════════════════════════════════════════════════════════

class TestE2EInventoryFlow:
    """E2E: 벤더 재고 변동 → 카탈로그 업데이트 → 스토어 반영 → 알림 발송."""

    def test_out_of_stock_flow(self):
        """품절 시나리오: 벤더 사이트 sold out → 카탈로그+스토어 업데이트 + 알림."""
        from src.inventory.inventory_sync import InventorySync

        syncer = InventorySync(sheet_id='dummy', worksheet='catalog')
        syncer._get_active_rows = MagicMock(return_value=[CATALOG_ROWS[0]])  # PTR-TNK-001 in_stock
        syncer.update_catalog_stock = MagicMock(return_value=True)
        syncer.update_shopify_stock = MagicMock(return_value=True)
        syncer.update_woo_stock = MagicMock(return_value=True)
        syncer.alert_manager = MagicMock()

        # 벤더 사이트에서 sold out 감지
        syncer.checker.check_batch = MagicMock(return_value=[{
            'sku': 'PTR-TNK-001', 'status': 'out_of_stock', 'quantity': 0,
            'price_changed': False, 'current_price': None, 'vendor': 'porter',
            'checked_at': '2026-03-09T17:00:00+00:00',
        }])

        result = syncer.full_sync(dry_run=False)

        # 변경사항 감지
        assert any(c['change'] == 'out_of_stock' for c in result['changes'])
        # 카탈로그 업데이트 호출
        syncer.update_catalog_stock.assert_called_once_with(
            'PTR-TNK-001', 'out_of_stock', quantity=0, price=None)
        # 스토어 업데이트 호출
        syncer.update_shopify_stock.assert_called_once_with('PTR-TNK-001', 0)
        syncer.update_woo_stock.assert_called_once_with('PTR-TNK-001', 0, 'outofstock')
        # 알림 발송
        syncer.alert_manager.notify_out_of_stock.assert_called_once()

    def test_restock_flow(self):
        """재입고 시나리오: 이전 out_of_stock → 벤더 in_stock → 업데이트 + 알림."""
        from src.inventory.inventory_sync import InventorySync

        out_of_stock_row = dict(CATALOG_ROWS[2])  # PTR-WAL-005 out_of_stock
        syncer = InventorySync(sheet_id='dummy', worksheet='catalog')
        syncer._get_active_rows = MagicMock(return_value=[out_of_stock_row])
        syncer.update_catalog_stock = MagicMock(return_value=True)
        syncer.update_shopify_stock = MagicMock(return_value=True)
        syncer.update_woo_stock = MagicMock(return_value=True)
        syncer.alert_manager = MagicMock()

        syncer.checker.check_batch = MagicMock(return_value=[{
            'sku': 'PTR-WAL-005', 'status': 'in_stock', 'quantity': 5,
            'price_changed': False, 'current_price': None, 'vendor': 'porter',
            'checked_at': '2026-03-09T17:00:00+00:00',
        }])

        result = syncer.full_sync(dry_run=False)

        assert any(c['change'] == 'restock' for c in result['changes'])
        syncer.alert_manager.notify_restock.assert_called_once()

    def test_price_change_flow(self):
        """가격 변동 시나리오: 벤더 가격 변동 → 카탈로그 업데이트 + 알림."""
        from src.inventory.inventory_sync import InventorySync

        syncer = InventorySync(sheet_id='dummy', worksheet='catalog')
        syncer._get_active_rows = MagicMock(return_value=[CATALOG_ROWS[0]])  # PTR-TNK-001 price=15000
        syncer.update_catalog_stock = MagicMock(return_value=True)
        syncer.update_shopify_stock = MagicMock(return_value=True)
        syncer.update_woo_stock = MagicMock(return_value=True)
        syncer.alert_manager = MagicMock()

        syncer.checker.check_batch = MagicMock(return_value=[{
            'sku': 'PTR-TNK-001', 'status': 'in_stock', 'quantity': 5,
            'price_changed': True, 'current_price': Decimal('14000'),  # 6.7% drop
            'vendor': 'porter', 'checked_at': '2026-03-09T17:00:00+00:00',
        }])

        result = syncer.full_sync(dry_run=False)

        assert any(c['change'] == 'price_changed' for c in result['changes'])
        syncer.alert_manager.notify_price_change.assert_called_once()
        # 카탈로그 가격 업데이트 포함
        syncer.update_catalog_stock.assert_called_once_with(
            'PTR-TNK-001', 'in_stock', quantity=5, price='14000')
