"""tests/test_inventory_sync.py — InventorySync 통합 테스트.

InventorySync.full_sync, sync_single, update_catalog_stock 등 핵심 로직을
외부 서비스 없이 mock으로 검증한다.
"""

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.inventory.inventory_sync import InventorySync, _map_stock_status  # noqa: E402

# ──────────────────────────────────────────────────────────
# 공통 테스트 데이터
# ──────────────────────────────────────────────────────────

CATALOG_ROWS = [
    {
        'sku': 'PTR-TNK-001',
        'title_ko': '포터 탱커',
        'src_url': 'https://www.yoshidakaban.com/product/100000.html',
        'buy_currency': 'JPY',
        'buy_price': 30800,
        'stock': 5,
        'stock_status': 'in_stock',
        'vendor': 'porter',
        'status': 'active',
        'price_history': '',
        'last_stock_check': '',
    },
    {
        'sku': 'MMP-EDP-001',
        'title_ko': '메모파리 향수',
        'src_url': 'https://www.memoparis.com/products/african-leather',
        'buy_currency': 'EUR',
        'buy_price': 250.0,
        'stock': 3,
        'stock_status': 'in_stock',
        'vendor': 'memo_paris',
        'status': 'active',
        'price_history': '',
        'last_stock_check': '',
    },
    {
        'sku': 'PTR-WAL-001',
        'title_ko': '포터 지갑',
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

CHECKED_IN_STOCK = [
    {'sku': 'PTR-TNK-001', 'status': 'in_stock', 'quantity': 5,
     'current_price': Decimal('30800'), 'vendor': 'porter', 'error': None},
    {'sku': 'MMP-EDP-001', 'status': 'in_stock', 'quantity': 3,
     'current_price': Decimal('250'), 'vendor': 'memo_paris', 'error': None},
    {'sku': 'PTR-WAL-001', 'status': 'out_of_stock', 'quantity': 0,
     'current_price': None, 'vendor': 'porter', 'error': None},
]

CHECKED_WITH_CHANGES = [
    {'sku': 'PTR-TNK-001', 'status': 'out_of_stock', 'quantity': 0,
     'current_price': None, 'vendor': 'porter', 'error': None},
    {'sku': 'MMP-EDP-001', 'status': 'in_stock', 'quantity': 3,
     'current_price': Decimal('250'), 'vendor': 'memo_paris', 'error': None},
    {'sku': 'PTR-WAL-001', 'status': 'in_stock', 'quantity': 5,
     'current_price': Decimal('8000'), 'vendor': 'porter', 'error': None},
]

CHECKED_PRICE_CHANGE = [
    {'sku': 'PTR-TNK-001', 'status': 'in_stock', 'quantity': 5,
     'current_price': Decimal('33000'), 'vendor': 'porter', 'error': None},
]


def _make_sync(catalog_rows=None, checked_rows=None, dry_run_default=True):
    """mock이 적용된 InventorySync 인스턴스를 반환."""
    sync = InventorySync(sheet_id='fake_sheet', worksheet='catalog')

    mock_ws = MagicMock()
    mock_ws.get_all_records.return_value = list(catalog_rows or CATALOG_ROWS)
    mock_ws.row_values.return_value = list(CATALOG_ROWS[0].keys()) if CATALOG_ROWS else []
    mock_ws.update_cell.return_value = None

    with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
        sync._mock_ws = mock_ws

    sync.checker = MagicMock()
    sync.checker.check_batch.return_value = list(checked_rows or CHECKED_IN_STOCK)
    sync.checker.check_single.side_effect = lambda sku, url, vendor: next(
        (r for r in (checked_rows or CHECKED_IN_STOCK) if r['sku'] == sku),
        {'sku': sku, 'status': 'unknown', 'quantity': 0, 'current_price': None,
         'vendor': vendor, 'error': None}
    )
    sync.alert_manager = MagicMock()

    return sync, mock_ws


# ══════════════════════════════════════════════════════════
# _map_stock_status 유틸
# ══════════════════════════════════════════════════════════

class TestMapStockStatus:
    def test_in_stock(self):
        assert _map_stock_status('in_stock') == 'in_stock'

    def test_out_of_stock(self):
        assert _map_stock_status('out_of_stock') == 'out_of_stock'

    def test_low_stock(self):
        assert _map_stock_status('low_stock') == 'low_stock'

    def test_unknown_returns_unknown(self):
        assert _map_stock_status('unknown') == 'unknown'

    def test_invalid_returns_unknown(self):
        assert _map_stock_status('garbage_value') == 'unknown'


# ══════════════════════════════════════════════════════════
# InventorySync.full_sync — dry_run 모드
# ══════════════════════════════════════════════════════════

class TestFullSyncDryRun:
    def test_returns_dict(self):
        sync, mock_ws = _make_sync()
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = sync.full_sync(dry_run=True)
        assert isinstance(result, dict)

    def test_result_has_required_keys(self):
        sync, mock_ws = _make_sync()
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = sync.full_sync(dry_run=True)
        for key in ('total_checked', 'changes', 'shopify_updated', 'woo_updated', 'sheets_updated', 'errors'):
            assert key in result, f"Missing key: {key}"

    def test_dry_run_flag_is_true_in_result(self):
        sync, mock_ws = _make_sync()
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = sync.full_sync(dry_run=True)
        assert result['dry_run'] is True

    def test_dry_run_does_not_update_sheets(self):
        sync, mock_ws = _make_sync()
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = sync.full_sync(dry_run=True)
        assert result['sheets_updated'] == 0

    def test_dry_run_does_not_update_shopify(self):
        sync, mock_ws = _make_sync()
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = sync.full_sync(dry_run=True)
        assert result['shopify_updated'] == 0

    def test_total_checked_matches_catalog(self):
        sync, mock_ws = _make_sync()
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = sync.full_sync(dry_run=True)
        assert result['total_checked'] == len(CATALOG_ROWS)


# ══════════════════════════════════════════════════════════
# 변경사항 감지
# ══════════════════════════════════════════════════════════

class TestChangeDetection:
    def test_out_of_stock_detected(self):
        """재고 있던 상품이 품절되면 out_of_stock 변경 감지."""
        sync, mock_ws = _make_sync(
            catalog_rows=CATALOG_ROWS,
            checked_rows=CHECKED_WITH_CHANGES,
        )
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = sync.full_sync(dry_run=True)
        changes = result['changes']
        oos = [c for c in changes if c.get('change') == 'out_of_stock']
        assert len(oos) >= 1
        assert oos[0]['sku'] == 'PTR-TNK-001'

    def test_restock_detected(self):
        """품절이었던 상품이 재입고되면 restock 변경 감지."""
        sync, mock_ws = _make_sync(
            catalog_rows=CATALOG_ROWS,
            checked_rows=CHECKED_WITH_CHANGES,
        )
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = sync.full_sync(dry_run=True)
        changes = result['changes']
        restock = [c for c in changes if c.get('change') == 'restock']
        assert len(restock) >= 1
        assert restock[0]['sku'] == 'PTR-WAL-001'

    def test_price_change_detected(self):
        """가격이 임계값 이상 변동되면 price_changed 변경 감지."""
        catalog = [dict(CATALOG_ROWS[0])]  # PTR-TNK-001
        checked = list(CHECKED_PRICE_CHANGE)
        sync, mock_ws = _make_sync(catalog_rows=catalog, checked_rows=checked)
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = sync.full_sync(dry_run=True)
        changes = result['changes']
        price_changes = [c for c in changes if c.get('change') == 'price_changed']
        assert len(price_changes) >= 1

    def test_no_changes_when_no_status_change(self):
        """변경사항이 없으면 changes 목록이 비어야 한다."""
        sync, mock_ws = _make_sync(
            catalog_rows=CATALOG_ROWS,
            checked_rows=CHECKED_IN_STOCK,
        )
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = sync.full_sync(dry_run=True)
        assert result['changes'] == []


# ══════════════════════════════════════════════════════════
# 카탈로그 로드 실패 처리
# ══════════════════════════════════════════════════════════

class TestCatalogLoadFailure:
    def test_sheets_error_returns_error_in_result(self):
        """Google Sheets 연결 실패 시 errors 목록에 기록되어야 한다."""
        sync = InventorySync(sheet_id='fake_sheet', worksheet='catalog')
        sync.checker = MagicMock()
        sync.alert_manager = MagicMock()
        with patch('src.inventory.inventory_sync.open_sheet', side_effect=Exception('connection refused')):
            result = sync.full_sync(dry_run=True)
        assert len(result['errors']) > 0

    def test_empty_catalog_returns_zero_checked(self):
        """빈 카탈로그면 total_checked=0을 반환해야 한다."""
        sync, mock_ws = _make_sync(catalog_rows=[], checked_rows=[])
        mock_ws.get_all_records.return_value = []
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = sync.full_sync(dry_run=True)
        assert result['total_checked'] == 0


# ══════════════════════════════════════════════════════════
# vendor_filter 기능
# ══════════════════════════════════════════════════════════

class TestVendorFilter:
    def test_vendor_filter_porter_only(self):
        """vendor_filter='porter'이면 PORTER 상품만 확인한다."""
        sync, mock_ws = _make_sync(
            catalog_rows=CATALOG_ROWS,
            checked_rows=[CHECKED_IN_STOCK[0], CHECKED_IN_STOCK[2]],
        )
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            result = sync.full_sync(dry_run=True, vendor_filter='porter')
        # memo_paris 상품은 제외되어야 함
        checked_count = result['total_checked']
        porter_rows = [r for r in CATALOG_ROWS if r['vendor'] == 'porter']
        assert checked_count == len(porter_rows)


# ══════════════════════════════════════════════════════════
# get_sync_report
# ══════════════════════════════════════════════════════════

class TestGetSyncReport:
    def test_returns_last_result(self):
        """get_sync_report는 마지막 동기화 결과를 반환한다."""
        sync, mock_ws = _make_sync()
        with patch('src.inventory.inventory_sync.open_sheet', return_value=mock_ws):
            sync.full_sync(dry_run=True)
        report = sync.get_sync_report()
        assert isinstance(report, dict)
        assert 'total_checked' in report

    def test_empty_before_first_sync(self):
        """첫 동기화 전에는 빈 dict를 반환한다."""
        sync = InventorySync(sheet_id='fake', worksheet='catalog')
        report = sync.get_sync_report()
        assert isinstance(report, dict)
