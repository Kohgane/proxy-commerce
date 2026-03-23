"""tests/test_auto_reorder.py — 자동 재발주 테스트."""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

SAMPLE_ROWS = [
    {'sku': 'PTR-TNK-001', 'title': 'Tanker', 'vendor': 'PORTER', 'stock': 1, 'sales_velocity': 2.0},
    {'sku': 'MMP-EDP-001', 'title': 'Memo', 'vendor': 'MEMO_PARIS', 'stock': 5, 'sales_velocity': 1.0},
    {'sku': 'PTR-TNK-002', 'title': 'Tanker 2', 'vendor': 'PORTER', 'stock': 0, 'sales_velocity': 3.0},
]


# ══════════════════════════════════════════════════════════
# AutoReorder 테스트
# ══════════════════════════════════════════════════════════

class TestAutoReorder:
    def _make_reorder(self, enabled=True, threshold=2):
        from src.reorder.auto_reorder import AutoReorder
        return AutoReorder(sheet_id='test', worksheet='reorder_queue',
                           enabled=enabled, threshold=threshold)

    def test_disabled_returns_early(self):
        reorder = self._make_reorder(enabled=False)
        result = reorder.run()
        assert result['enabled'] is False
        assert result['queued'] == 0

    def test_detects_low_stock(self):
        reorder = self._make_reorder(enabled=True, threshold=2)
        with patch.object(reorder, '_detect_low_stock', return_value=[SAMPLE_ROWS[0], SAMPLE_ROWS[2]]), \
             patch.object(reorder, '_build_queue', return_value=[]), \
             patch.object(reorder, '_record_to_sheet'), \
             patch.object(reorder, '_send_approval_request'):
            result = reorder.run()
        assert result['items_below_threshold'] == 2

    def test_dry_run_skips_sheet_and_telegram(self):
        reorder = self._make_reorder(enabled=True, threshold=10)
        with patch.object(reorder, '_detect_low_stock', return_value=SAMPLE_ROWS[:1]), \
             patch.object(reorder, '_build_queue', return_value=[SAMPLE_ROWS[0]]), \
             patch.object(reorder, '_record_to_sheet') as mock_sheet, \
             patch.object(reorder, '_send_approval_request') as mock_tg:
            result = reorder.run(dry_run=True)
        mock_sheet.assert_not_called()
        mock_tg.assert_not_called()
        assert result['dry_run'] is True

    def test_no_low_stock_returns_zero_queued(self):
        reorder = self._make_reorder(enabled=True, threshold=0)
        with patch.object(reorder, '_detect_low_stock', return_value=[]):
            result = reorder.run()
        assert result['items_below_threshold'] == 0
        assert result['queued'] == 0

    def test_build_queue_skips_duplicates(self):
        """중복 SKU는 발주 큐에 추가하지 않는다."""
        reorder = self._make_reorder(enabled=True)
        mock_q = MagicMock()
        mock_q.has_pending.return_value = True  # 이미 발주 대기 중

        with patch('src.reorder.reorder_queue.ReorderQueue', return_value=mock_q):
            result = reorder._build_queue(SAMPLE_ROWS[:2])
        assert result == []

    def test_calc_reorder_qty(self):
        from src.reorder.auto_reorder import AutoReorder
        qty = AutoReorder._calc_reorder_qty({'sales_velocity': 2.0})
        assert qty >= 1


# ══════════════════════════════════════════════════════════
# ReorderQueue 테스트
# ══════════════════════════════════════════════════════════

class TestReorderQueue:
    def _make_queue(self):
        from src.reorder.reorder_queue import ReorderQueue
        q = ReorderQueue(sheet_id='test', worksheet='reorder_queue')
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = []
        mock_ws.get_all_values.return_value = []
        mock_ws.row_values.return_value = [
            'sku', 'title', 'vendor', 'current_stock', 'reorder_qty',
            'status', 'created_at', 'updated_at', 'priority',
        ]
        q._get_ws = MagicMock(return_value=mock_ws)
        return q, mock_ws

    def test_has_pending_false_empty(self):
        q, _ = self._make_queue()
        assert q.has_pending('PTR-TNK-001') is False

    def test_has_pending_true(self):
        q, mock_ws = self._make_queue()
        mock_ws.get_all_records.return_value = [
            {'sku': 'PTR-TNK-001', 'status': 'pending_approval'},
        ]
        assert q.has_pending('PTR-TNK-001') is True

    def test_add_item(self):
        q, mock_ws = self._make_queue()
        result = q.add({
            'sku': 'PTR-TNK-001', 'title': 'Tanker',
            'vendor': 'PORTER', 'current_stock': 1, 'reorder_qty': 5,
        })
        assert result is True
        mock_ws.append_row.assert_called_once()

    def test_add_duplicate_skips(self):
        q, mock_ws = self._make_queue()
        mock_ws.get_all_records.return_value = [
            {'sku': 'PTR-TNK-001', 'status': 'pending_approval'},
        ]
        result = q.add({'sku': 'PTR-TNK-001'})
        assert result is False
        mock_ws.append_row.assert_not_called()

    def test_get_by_status(self):
        q, mock_ws = self._make_queue()
        mock_ws.get_all_records.return_value = [
            {'sku': 'A', 'status': 'pending_approval'},
            {'sku': 'B', 'status': 'approved'},
        ]
        pending = q.get_by_status('pending_approval')
        assert len(pending) == 1
        assert pending[0]['sku'] == 'A'

    def test_get_stats(self):
        q, mock_ws = self._make_queue()
        mock_ws.get_all_records.return_value = [
            {'sku': 'A', 'status': 'pending_approval'},
            {'sku': 'B', 'status': 'approved'},
            {'sku': 'C', 'status': 'rejected'},
        ]
        stats = q.get_stats()
        assert stats['total'] == 3
        assert stats['pending_approval'] == 1
        assert stats['approved'] == 1

    def test_calc_priority_zero_stock(self):
        from src.reorder.reorder_queue import ReorderQueue
        priority = ReorderQueue.calc_priority({'current_stock': 0, 'sales_velocity': 5.0})
        assert priority >= 8  # 높은 우선순위

    def test_calc_priority_high_stock(self):
        from src.reorder.reorder_queue import ReorderQueue
        priority = ReorderQueue.calc_priority({'current_stock': 10, 'sales_velocity': 0.0})
        assert priority <= 3  # 낮은 우선순위
