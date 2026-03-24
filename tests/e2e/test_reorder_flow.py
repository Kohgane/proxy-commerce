"""tests/e2e/test_reorder_flow.py — 자동 재발주 플로우 E2E 테스트.

AutoReorder의 재고 부족 감지, dry_run, 발주 큐 생성을 검증한다.
"""

from unittest.mock import MagicMock, patch


CATALOG_WITH_LOW_STOCK = [
    {
        'sku': 'PTR-TNK-001',
        'title_ko': '포터 탱커 브리프케이스',
        'buy_currency': 'JPY',
        'buy_price': 30800,
        'stock': 1,  # 임계값(2) 이하
        'vendor': 'porter',
        'status': 'active',
    },
    {
        'sku': 'MMP-EDP-001',
        'title_ko': '메모파리 EDP',
        'buy_currency': 'EUR',
        'buy_price': 250,
        'stock': 5,  # 재고 충분
        'vendor': 'memo_paris',
        'status': 'active',
    },
]


class TestAutoReorderFlow:
    """AutoReorder 플로우 E2E 테스트."""

    def test_reorder_detects_low_stock(self, monkeypatch):
        """임계값 이하 재고를 가진 상품을 감지한다."""
        monkeypatch.setenv('REORDER_ENABLED', '1')
        monkeypatch.setenv('REORDER_THRESHOLD', '2')
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test_sheet')

        import src.utils.sheets as sheets_mod
        with patch.object(sheets_mod, 'open_sheet') as mock_sheet, \
             patch('src.inventory.inventory_sync.InventorySync._get_active_rows',
                   return_value=CATALOG_WITH_LOW_STOCK), \
             patch('src.utils.telegram.send_tele', return_value=None):

            ws_queue = MagicMock()
            ws_queue.get_all_records.return_value = []
            ws_queue.append_row.return_value = None
            mock_sheet.return_value = ws_queue

            from src.reorder.auto_reorder import AutoReorder
            reorder = AutoReorder(
                sheet_id='test_sheet',
                enabled=True,
                threshold=2,
            )
            result = reorder.run(dry_run=True)

        assert result['enabled'] is True
        assert result['items_below_threshold'] >= 1

    def test_reorder_dry_run(self, monkeypatch):
        """dry_run=True 시 발주 큐에 항목을 추가하지 않는다."""
        monkeypatch.setenv('REORDER_ENABLED', '1')
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test_sheet')

        import src.utils.sheets as sheets_mod
        with patch.object(sheets_mod, 'open_sheet') as mock_sheet, \
             patch('src.inventory.inventory_sync.InventorySync._get_active_rows',
                   return_value=CATALOG_WITH_LOW_STOCK), \
             patch('src.utils.telegram.send_tele', return_value=None):

            ws_queue = MagicMock()
            ws_queue.get_all_records.return_value = []
            mock_sheet.return_value = ws_queue

            from src.reorder.auto_reorder import AutoReorder
            reorder = AutoReorder(sheet_id='test_sheet', enabled=True, threshold=2)
            result = reorder.run(dry_run=True)

        assert result['dry_run'] is True
        # dry_run에서도 큐 아이템은 생성되지만 Sheets에 기록되지 않음
        ws_queue.append_row.assert_not_called()

    def test_reorder_creates_queue(self, monkeypatch):
        """dry_run=False + 재고 부족 상품 존재 시 발주 큐에 항목이 추가된다."""
        monkeypatch.setenv('REORDER_ENABLED', '1')
        monkeypatch.setenv('GOOGLE_SHEET_ID', 'test_sheet')
        monkeypatch.setenv('REORDER_APPROVAL_REQUIRED', '0')

        import src.utils.sheets as sheets_mod
        with patch.object(sheets_mod, 'open_sheet') as mock_sheet, \
             patch('src.inventory.inventory_sync.InventorySync._get_active_rows',
                   return_value=CATALOG_WITH_LOW_STOCK), \
             patch('src.utils.telegram.send_tele', return_value=None):

            ws_queue = MagicMock()
            ws_queue.get_all_records.return_value = []
            ws_queue.append_row.return_value = None
            mock_sheet.return_value = ws_queue

            from src.reorder.auto_reorder import AutoReorder
            reorder = AutoReorder(sheet_id='test_sheet', enabled=True, threshold=2)
            result = reorder.run(dry_run=False)

        assert result['enabled'] is True
        assert result['dry_run'] is False
        assert result['items_below_threshold'] >= 1

    def test_reorder_disabled(self, monkeypatch):
        """REORDER_ENABLED=0 시 실행하지 않는다."""
        from src.reorder.auto_reorder import AutoReorder
        reorder = AutoReorder(enabled=False)
        result = reorder.run()

        assert result['enabled'] is False
        assert result['items_checked'] == 0
