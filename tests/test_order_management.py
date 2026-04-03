"""tests/test_order_management.py — Phase 84: 주문 분할/병합 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.order_management import (
    SubOrder,
    OrderSplitter,
    OrderMerger,
    MergeCandidate,
    SplitHistory,
    SplitNotifier,
)


class TestSubOrder:
    def test_defaults(self):
        so = SubOrder(parent_order_id='o1', sub_order_id='o1-sub-1')
        assert so.status == 'pending'
        assert so.items == []
        assert so.shipping_info == {}


class TestOrderSplitter:
    def test_split_string_order(self):
        splitter = OrderSplitter()
        result = splitter.split('ORD-001')
        assert result['parent_order_id'] == 'ORD-001'
        assert len(result['sub_orders']) == 1
        assert result['sub_orders'][0].sub_order_id == 'ORD-001-sub-1'

    def test_split_by_supplier(self):
        splitter = OrderSplitter()
        order = {
            'order_id': 'ORD-002',
            'items': [
                {'supplier_id': 'sup1', 'name': 'item1'},
                {'supplier_id': 'sup2', 'name': 'item2'},
                {'supplier_id': 'sup1', 'name': 'item3'},
            ],
        }
        result = splitter.split(order, strategy='supplier')
        assert result['parent_order_id'] == 'ORD-002'
        assert len(result['sub_orders']) == 2

    def test_split_by_warehouse(self):
        splitter = OrderSplitter()
        order = {
            'order_id': 'ORD-003',
            'items': [
                {'warehouse_id': 'wh1', 'name': 'item1'},
                {'warehouse_id': 'wh2', 'name': 'item2'},
            ],
        }
        result = splitter.split(order, strategy='warehouse')
        assert len(result['sub_orders']) == 2

    def test_split_by_shipping_method(self):
        splitter = OrderSplitter()
        order = {
            'order_id': 'ORD-004',
            'items': [
                {'shipping_method': 'express', 'name': 'item1'},
                {'shipping_method': 'standard', 'name': 'item2'},
            ],
        }
        result = splitter.split(order, strategy='shipping_method')
        assert len(result['sub_orders']) == 2

    def test_split_single_supplier(self):
        splitter = OrderSplitter()
        order = {
            'order_id': 'ORD-005',
            'items': [
                {'supplier_id': 'sup1', 'name': 'item1'},
                {'supplier_id': 'sup1', 'name': 'item2'},
            ],
        }
        result = splitter.split(order, strategy='supplier')
        assert len(result['sub_orders']) == 1


class TestOrderMerger:
    def test_merge(self):
        merger = OrderMerger()
        result = merger.merge(['ORD-001', 'ORD-002'])
        assert 'merged_order_id' in result
        assert result['status'] == 'merged'
        assert 'ORD-001' in result['merged_order_ids']
        assert 'ORD-002' in result['merged_order_ids']

    def test_merge_multiple(self):
        merger = OrderMerger()
        result = merger.merge(['ORD-001', 'ORD-002', 'ORD-003'])
        assert len(result['merged_order_ids']) == 3


class TestMergeCandidate:
    def test_find_candidates(self):
        mc = MergeCandidate()
        orders = [
            {'order_id': 'o1', 'recipient': 'alice', 'warehouse_id': 'wh1'},
            {'order_id': 'o2', 'recipient': 'alice', 'warehouse_id': 'wh1'},
            {'order_id': 'o3', 'recipient': 'bob', 'warehouse_id': 'wh1'},
        ]
        candidates = mc.find_candidates(orders)
        assert len(candidates) == 1
        assert 'o1' in candidates[0]['order_ids']
        assert 'o2' in candidates[0]['order_ids']

    def test_no_candidates(self):
        mc = MergeCandidate()
        orders = [
            {'order_id': 'o1', 'recipient': 'alice', 'warehouse_id': 'wh1'},
            {'order_id': 'o2', 'recipient': 'bob', 'warehouse_id': 'wh2'},
        ]
        candidates = mc.find_candidates(orders)
        assert candidates == []


class TestSplitHistory:
    def test_record_and_get_split(self):
        history = SplitHistory()
        history.record_split('ORD-001', ['ORD-001-sub-1', 'ORD-001-sub-2'])
        records = history.get_split_history('ORD-001')
        assert len(records) == 1
        assert 'ORD-001-sub-1' in records[0]['sub_order_ids']

    def test_record_and_get_merge(self):
        history = SplitHistory()
        history.record_merge(['ORD-001', 'ORD-002'], 'merged-ORD-001-ORD-002')
        records = history.get_merge_history('merged-ORD-001-ORD-002')
        assert len(records) == 1

    def test_get_sub_orders(self):
        history = SplitHistory()
        history.record_split('ORD-001', ['ORD-001-sub-1', 'ORD-001-sub-2'])
        result = history.get_sub_orders('ORD-001')
        assert result['parent_order_id'] == 'ORD-001'
        assert 'ORD-001-sub-1' in result['sub_orders']
        assert 'ORD-001-sub-2' in result['sub_orders']

    def test_empty_history(self):
        history = SplitHistory()
        assert history.get_split_history('nonexistent') == []
        assert history.get_merge_history('nonexistent') == []
        result = history.get_sub_orders('nonexistent')
        assert result['sub_orders'] == []


class TestSplitNotifier:
    def test_notify_split(self):
        notifier = SplitNotifier()
        result = notifier.notify_split('ORD-001', ['sub-1', 'sub-2'], 'cust1')
        assert result['notified'] is True
        assert 'sub-1' in result['sub_order_ids']

    def test_notify_merge(self):
        notifier = SplitNotifier()
        result = notifier.notify_merge('merged-001', ['o1', 'o2'], 'cust1')
        assert result['notified'] is True
        assert result['merged_order_id'] == 'merged-001'
