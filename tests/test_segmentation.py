"""tests/test_segmentation.py — Phase 73: 고객 세그먼트 관리 테스트."""
from __future__ import annotations

import pytest

from src.segmentation import (
    SegmentRule, SegmentBuilder, SegmentManager, SegmentAnalyzer, SegmentExporter
)


class TestSegmentRule:
    def test_gt_operator(self):
        rule = SegmentRule(field="total_purchase_amount", operator="gt", value=500_000)
        assert rule.evaluate({"total_purchase_amount": 1_000_000}) is True
        assert rule.evaluate({"total_purchase_amount": 100_000}) is False

    def test_gte_operator(self):
        rule = SegmentRule(field="purchase_count", operator="gte", value=5)
        assert rule.evaluate({"purchase_count": 5}) is True
        assert rule.evaluate({"purchase_count": 4}) is False

    def test_lt_operator(self):
        rule = SegmentRule(field="purchase_count", operator="lt", value=3)
        assert rule.evaluate({"purchase_count": 1}) is True
        assert rule.evaluate({"purchase_count": 3}) is False

    def test_eq_operator(self):
        rule = SegmentRule(field="region", operator="eq", value="서울")
        assert rule.evaluate({"region": "서울"}) is True
        assert rule.evaluate({"region": "부산"}) is False

    def test_neq_operator(self):
        rule = SegmentRule(field="channel", operator="neq", value="offline")
        assert rule.evaluate({"channel": "online"}) is True
        assert rule.evaluate({"channel": "offline"}) is False

    def test_in_operator(self):
        rule = SegmentRule(field="region", operator="in", value=["서울", "경기"])
        assert rule.evaluate({"region": "서울"}) is True
        assert rule.evaluate({"region": "부산"}) is False

    def test_not_in_operator(self):
        rule = SegmentRule(field="channel", operator="not_in", value=["offline"])
        assert rule.evaluate({"channel": "online"}) is True
        assert rule.evaluate({"channel": "offline"}) is False

    def test_missing_field_returns_false(self):
        rule = SegmentRule(field="missing_field", operator="gt", value=0)
        assert rule.evaluate({}) is False

    def test_to_dict(self):
        rule = SegmentRule(field="purchase_count", operator="gte", value=10)
        d = rule.to_dict()
        assert d["field"] == "purchase_count"
        assert d["operator"] == "gte"
        assert d["value"] == 10
        assert "rule_id" in d


class TestSegmentBuilder:
    def test_and_logic(self):
        builder = SegmentBuilder(logic="AND")
        builder.add_rule("total_purchase_amount", "gte", 1_000_000)
        builder.add_rule("purchase_count", "gte", 5)
        customer_vip = {
            "total_purchase_amount": 1_500_000,
            "purchase_count": 10,
        }
        customer_not_vip = {
            "total_purchase_amount": 500_000,
            "purchase_count": 10,
        }
        assert builder.matches(customer_vip) is True
        assert builder.matches(customer_not_vip) is False

    def test_or_logic(self):
        builder = SegmentBuilder(logic="OR")
        builder.add_rule("total_purchase_amount", "gte", 1_000_000)
        builder.add_rule("purchase_count", "gte", 20)
        customer = {"total_purchase_amount": 200_000, "purchase_count": 25}
        assert builder.matches(customer) is True

    def test_empty_rules_always_matches(self):
        builder = SegmentBuilder()
        assert builder.matches({}) is True

    def test_chaining(self):
        builder = SegmentBuilder()
        result = builder.add_rule("a", "eq", 1).add_rule("b", "eq", 2)
        assert result is builder
        assert len(builder.build()) == 2

    def test_invalid_logic_raises(self):
        with pytest.raises(ValueError):
            SegmentBuilder(logic="INVALID")


class TestSegmentManager:
    def setup_method(self):
        self.mgr = SegmentManager()

    def test_builtin_segments_initialized(self):
        segments = self.mgr.list()
        names = [s["name"] for s in segments]
        assert "VIP" in names
        assert "신규" in names
        assert "이탈위험" in names

    def test_create_segment(self):
        seg = self.mgr.create(
            name="테스트",
            description="테스트 세그먼트",
            rules=[{"field": "purchase_count", "operator": "gte", "value": 3}],
        )
        assert seg["name"] == "테스트"
        assert "segment_id" in seg

    def test_create_duplicate_raises(self):
        self.mgr.create(name="unique_seg")
        with pytest.raises(ValueError):
            self.mgr.create(name="unique_seg")

    def test_get_segment(self):
        self.mgr.create(name="seg1")
        seg = self.mgr.get("seg1")
        assert seg is not None
        assert seg["name"] == "seg1"

    def test_get_nonexistent_returns_none(self):
        assert self.mgr.get("nonexistent") is None

    def test_update_segment(self):
        self.mgr.create(name="seg_update", description="old")
        updated = self.mgr.update("seg_update", description="new")
        assert updated["description"] == "new"

    def test_delete_segment(self):
        self.mgr.create(name="seg_delete")
        self.mgr.delete("seg_delete")
        assert self.mgr.get("seg_delete") is None

    def test_delete_builtin_raises(self):
        with pytest.raises(ValueError):
            self.mgr.delete("VIP")

    def test_classify_customer(self):
        customer = {"total_purchase_amount": 2_000_000, "purchase_count": 15}
        matched = self.mgr.classify_customer(customer)
        assert "VIP" in matched
        assert "대량구매" in matched

    def test_add_customer_manually(self):
        self.mgr.add_customer("VIP", "customer_001")
        customers = self.mgr.get_customers("VIP")
        assert "customer_001" in customers

    def test_build_segment(self):
        all_customers = [
            {"customer_id": "c1", "total_purchase_amount": 1_500_000},
            {"customer_id": "c2", "total_purchase_amount": 500_000},
            {"customer_id": "c3", "total_purchase_amount": 2_000_000},
        ]
        count = self.mgr.build_segment("VIP", all_customers)
        assert count == 2  # c1, c3


class TestSegmentAnalyzer:
    def setup_method(self):
        self.analyzer = SegmentAnalyzer()

    def test_analyze_empty(self):
        result = self.analyzer.analyze("empty", [])
        assert result["size"] == 0
        assert result["avg_order_amount"] == 0.0

    def test_analyze_customers(self):
        customers = [
            {"total_purchase_amount": 1_000_000, "purchase_count": 5, "days_since_last_purchase": 30},
            {"total_purchase_amount": 2_000_000, "purchase_count": 10, "days_since_last_purchase": 100},
        ]
        result = self.analyzer.analyze("test", customers)
        assert result["size"] == 2
        assert result["avg_order_amount"] == 1_500_000.0
        assert result["churn_rate"] == 0.5

    def test_compare(self):
        results = [
            {"segment_name": "VIP", "size": 10, "ltv": 500_000},
            {"segment_name": "신규", "size": 100, "ltv": 50_000},
        ]
        comparison = self.analyzer.compare(results)
        assert comparison["best_ltv"] == "VIP"
        assert comparison["largest"] == "신규"


class TestSegmentExporter:
    def setup_method(self):
        self.exporter = SegmentExporter()

    def test_export_csv(self):
        customers = [
            {"customer_id": "c1", "total_purchase_amount": 1_000_000, "purchase_count": 5},
            {"customer_id": "c2", "total_purchase_amount": 500_000, "purchase_count": 2},
        ]
        csv_str = self.exporter.export_csv(customers)
        assert "customer_id" in csv_str
        assert "c1" in csv_str
        assert "c2" in csv_str

    def test_export_segment(self):
        customers = [{"customer_id": "c1"}]
        result = self.exporter.export_segment("VIP", customers)
        assert result["segment_name"] == "VIP"
        assert result["record_count"] == 1
        assert "csv" in result

    def test_export_empty(self):
        result = self.exporter.export_segment("empty", [])
        assert result["record_count"] == 0
