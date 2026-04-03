"""tests/test_customer_segmentation.py — Phase 86: 고객 세그멘테이션 테스트."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.customer_segmentation import (
    Segment,
    SegmentManager,
    SegmentRule,
    PurchaseFrequencyRule,
    SpendingRule,
    RecencyRule,
    GeographicRule,
    SegmentAnalyzer,
    SegmentExporter,
    AutoSegmenter,
)


class TestSegmentModel:
    def test_dataclass_fields(self):
        seg = Segment(segment_id='s1', name='VIP', description='VIP customers')
        assert seg.segment_id == 's1'
        assert seg.name == 'VIP'
        assert seg.customer_count == 0
        assert seg.created_at


class TestSegmentManager:
    def test_create(self):
        mgr = SegmentManager()
        seg = mgr.create('VIP', description='Top customers')
        assert seg.segment_id
        assert seg.name == 'VIP'

    def test_get(self):
        mgr = SegmentManager()
        seg = mgr.create('VIP')
        found = mgr.get(seg.segment_id)
        assert found is not None
        assert found.name == 'VIP'

    def test_get_not_found(self):
        mgr = SegmentManager()
        assert mgr.get('nonexistent') is None

    def test_list(self):
        mgr = SegmentManager()
        mgr.create('VIP')
        mgr.create('신규')
        segs = mgr.list()
        assert len(segs) == 2

    def test_update(self):
        mgr = SegmentManager()
        seg = mgr.create('VIP')
        updated = mgr.update(seg.segment_id, name='Super VIP')
        assert updated.name == 'Super VIP'

    def test_delete(self):
        mgr = SegmentManager()
        seg = mgr.create('VIP')
        result = mgr.delete(seg.segment_id)
        assert result
        assert mgr.get(seg.segment_id) is None


class TestPurchaseFrequencyRule:
    def test_heavy_buyer(self):
        rule = PurchaseFrequencyRule('heavy')
        assert rule.matches({'purchase_count': 10})
        assert not rule.matches({'purchase_count': 5})

    def test_medium_buyer(self):
        rule = PurchaseFrequencyRule('medium')
        assert rule.matches({'purchase_count': 5})
        assert not rule.matches({'purchase_count': 10})

    def test_rule_name(self):
        rule = PurchaseFrequencyRule('heavy')
        assert 'heavy' in rule.name()


class TestSpendingRule:
    def test_vip(self):
        rule = SpendingRule('VIP')
        assert rule.matches({'total_spend': 1000000})
        assert not rule.matches({'total_spend': 500000})

    def test_normal(self):
        rule = SpendingRule('일반')
        assert rule.matches({'total_spend': 500000})

    def test_rule_name(self):
        rule = SpendingRule('VIP')
        assert 'VIP' in rule.name()


class TestRecencyRule:
    def test_active(self):
        rule = RecencyRule('활성')
        assert rule.matches({'days_since_last_purchase': 15})
        assert not rule.matches({'days_since_last_purchase': 60})

    def test_dormant(self):
        rule = RecencyRule('휴면')
        assert rule.matches({'days_since_last_purchase': 60})
        assert not rule.matches({'days_since_last_purchase': 10})

    def test_churned(self):
        rule = RecencyRule('이탈')
        assert rule.matches({'days_since_last_purchase': 120})

    def test_rule_name(self):
        rule = RecencyRule('활성')
        assert '활성' in rule.name()


class TestGeographicRule:
    def test_matches(self):
        rule = GeographicRule('서울')
        assert rule.matches({'region': '서울'})
        assert not rule.matches({'region': '부산'})

    def test_rule_name(self):
        rule = GeographicRule('서울')
        assert '서울' in rule.name()


class TestSegmentAnalyzer:
    def test_analyze_empty(self):
        analyzer = SegmentAnalyzer()
        result = analyzer.analyze('s1', [])
        assert result['count'] == 0
        assert result['avg_order_value'] == 0

    def test_analyze_customers(self):
        analyzer = SegmentAnalyzer()
        customers = [
            {'avg_order_value': 100000, 'total_spend': 500000, 'purchase_count': 5},
            {'avg_order_value': 200000, 'total_spend': 1000000, 'purchase_count': 10},
        ]
        result = analyzer.analyze('s1', customers)
        assert result['count'] == 2
        assert result['avg_order_value'] == 150000
        assert result['repurchase_rate'] == 1.0  # all have >1 purchase

    def test_repurchase_rate(self):
        analyzer = SegmentAnalyzer()
        customers = [
            {'purchase_count': 1},
            {'purchase_count': 3},
        ]
        result = analyzer.analyze('s1', customers)
        assert result['repurchase_rate'] == 0.5


class TestSegmentExporter:
    def test_export_csv(self):
        exporter = SegmentExporter()
        customers = [
            {'customer_id': 'c1', 'name': '홍길동', 'email': 'test@test.com'},
            {'customer_id': 'c2', 'name': '김철수', 'email': 'kim@test.com'},
        ]
        csv_str = exporter.export_csv(customers)
        assert 'customer_id' in csv_str
        assert 'c1' in csv_str
        assert 'c2' in csv_str

    def test_export_empty(self):
        exporter = SegmentExporter()
        assert exporter.export_csv([]) == ""

    def test_export_with_fields(self):
        exporter = SegmentExporter()
        customers = [{'customer_id': 'c1', 'name': '홍길동', 'email': 'a@b.com'}]
        csv_str = exporter.export_csv(customers, fields=['customer_id', 'name'])
        assert 'customer_id' in csv_str
        assert 'email' not in csv_str


class TestAutoSegmenter:
    def test_assign(self):
        auto = AutoSegmenter()
        auto.add_rules('heavy_vip', [
            PurchaseFrequencyRule('heavy'),
            SpendingRule('VIP'),
        ])
        customer = {'purchase_count': 15, 'total_spend': 2000000}
        segments = auto.assign(customer)
        assert 'heavy_vip' in segments

    def test_assign_no_match(self):
        auto = AutoSegmenter()
        auto.add_rules('vip', [SpendingRule('VIP')])
        customer = {'total_spend': 50000}  # below VIP threshold
        segments = auto.assign(customer)
        assert 'vip' not in segments

    def test_assign_all(self):
        auto = AutoSegmenter()
        auto.add_rules('active', [RecencyRule('활성')])
        customers = [
            {'customer_id': 'c1', 'days_since_last_purchase': 10},
            {'customer_id': 'c2', 'days_since_last_purchase': 100},
        ]
        result = auto.assign_all(customers)
        assert len(result) == 2
