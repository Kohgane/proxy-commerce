"""tests/test_inventory_transactions.py — Phase 85: 재고 입출고 이력 관리 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.inventory_transactions import (
    InventoryTransaction,
    TransactionManager,
    StockLedger,
    TransactionReport,
    StockAdjustment,
    TransactionValidator,
)


class TestInventoryTransaction:
    def test_dataclass_fields(self):
        tx = InventoryTransaction(
            transaction_id='tx1',
            sku='SKU-001',
            type='inbound',
            quantity=10,
            reason='purchase',
            timestamp='2024-01-01T00:00:00',
        )
        assert tx.transaction_id == 'tx1'
        assert tx.sku == 'SKU-001'
        assert tx.type == 'inbound'
        assert tx.quantity == 10
        assert tx.reason == 'purchase'


class TestTransactionManager:
    def test_create_inbound(self):
        mgr = TransactionManager()
        tx = mgr.create('SKU-001', 'inbound', 50, reason='purchase')
        assert tx.sku == 'SKU-001'
        assert tx.type == 'inbound'
        assert tx.quantity == 50
        assert tx.transaction_id

    def test_create_outbound(self):
        mgr = TransactionManager()
        tx = mgr.create('SKU-001', 'outbound', 10, reason='sale')
        assert tx.type == 'outbound'
        assert tx.quantity == 10

    def test_list_all(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 10)
        mgr.create('SKU-002', 'inbound', 20)
        all_txs = mgr.list()
        assert len(all_txs) == 2

    def test_list_by_sku(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 10)
        mgr.create('SKU-002', 'inbound', 20)
        mgr.create('SKU-001', 'outbound', 5)
        sku1_txs = mgr.list('SKU-001')
        assert len(sku1_txs) == 2

    def test_stats(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 100)
        mgr.create('SKU-001', 'outbound', 30)
        mgr.create('SKU-001', 'adjustment', -5)
        stats = mgr.stats('SKU-001')
        assert stats['inbound'] == 100
        assert stats['outbound'] == 30
        assert stats['adjustment'] == -5
        assert stats['net'] == 65

    def test_stats_empty(self):
        mgr = TransactionManager()
        stats = mgr.stats('NONEXISTENT')
        assert stats['net'] == 0
        assert stats['total'] == 0


class TestStockLedger:
    def test_current_qty(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 100)
        mgr.create('SKU-001', 'outbound', 30)
        ledger = StockLedger(mgr)
        assert ledger.current_qty('SKU-001') == 70

    def test_current_qty_empty(self):
        mgr = TransactionManager()
        ledger = StockLedger(mgr)
        assert ledger.current_qty('EMPTY') == 0

    def test_snapshot(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 50)
        ledger = StockLedger(mgr)
        snap = ledger.snapshot('SKU-001')
        assert snap['sku'] == 'SKU-001'
        assert snap['quantity'] == 50

    def test_snapshot_with_as_of(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 50)
        ledger = StockLedger(mgr)
        snap = ledger.snapshot('SKU-001', as_of='2020-01-01')
        assert snap['quantity'] == 0  # all transactions after 2020-01-01


class TestTransactionReport:
    def test_period_summary(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 100)
        mgr.create('SKU-001', 'outbound', 30)
        rep = TransactionReport(mgr)
        summary = rep.period_summary('2000-01-01', '2999-12-31')
        assert summary['inbound'] == 100
        assert summary['outbound'] == 30
        assert summary['count'] == 2

    def test_sku_history(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 50)
        mgr.create('SKU-001', 'outbound', 20)
        rep = TransactionReport(mgr)
        history = rep.sku_history('SKU-001')
        assert len(history) == 2
        assert history[0]['type'] == 'inbound'

    def test_detect_discrepancies(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'outbound', 100)  # negative stock
        rep = TransactionReport(mgr)
        discrepancies = rep.detect_discrepancies()
        assert len(discrepancies) == 1
        assert discrepancies[0]['sku'] == 'SKU-001'
        assert discrepancies[0]['net_qty'] < 0

    def test_no_discrepancies(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 100)
        rep = TransactionReport(mgr)
        assert rep.detect_discrepancies() == []


class TestStockAdjustment:
    def test_adjust_up(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 50)
        adj = StockAdjustment(mgr)
        result = adj.adjust('SKU-001', actual_qty=60)
        assert result['diff'] == 10
        assert result['previous'] == 50
        assert result['actual'] == 60

    def test_adjust_down(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 50)
        adj = StockAdjustment(mgr)
        result = adj.adjust('SKU-001', actual_qty=40)
        assert result['diff'] == -10

    def test_no_change(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 50)
        adj = StockAdjustment(mgr)
        result = adj.adjust('SKU-001', actual_qty=50)
        assert result['status'] == 'no_change'


class TestTransactionValidator:
    def test_valid_inbound(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 100)
        validator = TransactionValidator(mgr)
        valid, errors = validator.validate('SKU-001', 'inbound', 50)
        assert valid
        assert errors == []

    def test_invalid_type(self):
        mgr = TransactionManager()
        validator = TransactionValidator(mgr)
        valid, errors = validator.validate('SKU-001', 'invalid_type', 10)
        assert not valid
        assert len(errors) > 0

    def test_zero_quantity(self):
        mgr = TransactionManager()
        validator = TransactionValidator(mgr)
        valid, errors = validator.validate('SKU-001', 'inbound', 0)
        assert not valid

    def test_outbound_insufficient_stock(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 10)
        validator = TransactionValidator(mgr)
        valid, errors = validator.validate('SKU-001', 'outbound', 20)
        assert not valid
        assert any('재고 부족' in e for e in errors)

    def test_outbound_sufficient_stock(self):
        mgr = TransactionManager()
        mgr.create('SKU-001', 'inbound', 100)
        validator = TransactionValidator(mgr)
        valid, errors = validator.validate('SKU-001', 'outbound', 50)
        assert valid
