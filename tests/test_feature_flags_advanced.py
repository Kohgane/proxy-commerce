"""tests/test_feature_flags_advanced.py — Phase 78: 피처 플래그 고도화 테스트."""
from __future__ import annotations

import pytest

from src.feature_flags import (
    FeatureFlag, TargetingRule, Variant,
    GradualRollout, VariantManager,
    FlagHistory, FlagOverride,
    FlagEvaluatorAdvanced,
)


class TestTargetingRule:
    def test_eq_match(self):
        rule = TargetingRule(attribute="plan", operator="eq", value="premium")
        assert rule.matches({"plan": "premium"}) is True
        assert rule.matches({"plan": "free"}) is False

    def test_in_match(self):
        rule = TargetingRule(attribute="country", operator="in", value=["KR", "JP"])
        assert rule.matches({"country": "KR"}) is True
        assert rule.matches({"country": "US"}) is False

    def test_gt_match(self):
        rule = TargetingRule(attribute="age", operator="gt", value=18)
        assert rule.matches({"age": 20}) is True
        assert rule.matches({"age": 15}) is False

    def test_missing_attribute(self):
        rule = TargetingRule(attribute="missing", operator="eq", value="x")
        assert rule.matches({}) is False

    def test_to_dict(self):
        rule = TargetingRule(attribute="plan", operator="eq", value="vip")
        d = rule.to_dict()
        assert d["attribute"] == "plan"
        assert "rule_id" in d


class TestFeatureFlag:
    def test_creation(self):
        flag = FeatureFlag(name="new_feature", enabled=True)
        assert flag.name == "new_feature"
        assert flag.enabled is True
        assert flag.rollout_percentage == 100.0

    def test_to_dict(self):
        flag = FeatureFlag(
            name="test_flag",
            enabled=True,
            rollout_percentage=50.0,
            rules=[TargetingRule("plan", "eq", "premium")],
        )
        d = flag.to_dict()
        assert d["name"] == "test_flag"
        assert d["rollout_percentage"] == 50.0
        assert len(d["rules"]) == 1
        assert "flag_id" in d


class TestGradualRollout:
    def setup_method(self):
        self.rollout = GradualRollout()

    def test_100_percent_always_included(self):
        for i in range(10):
            assert self.rollout.is_included("flag", f"user{i}", 100.0) is True

    def test_0_percent_never_included(self):
        for i in range(10):
            assert self.rollout.is_included("flag", f"user{i}", 0.0) is False

    def test_consistency(self):
        # 같은 사용자는 항상 같은 결과
        result1 = self.rollout.is_included("flag", "user123", 50.0)
        result2 = self.rollout.is_included("flag", "user123", 50.0)
        assert result1 == result2

    def test_50_percent_approximately(self):
        included = sum(
            1 for i in range(1000)
            if self.rollout.is_included("flag", f"user{i}", 50.0)
        )
        # 약 50% 포함 (±15% 허용)
        assert 350 <= included <= 650


class TestVariantManager:
    def setup_method(self):
        self.mgr = VariantManager()
        self.variants = [
            Variant("control", "original", weight=1.0),
            Variant("treatment", "new", weight=1.0),
        ]

    def test_assign_variant(self):
        variant = self.mgr.assign_variant("flag1", "user1", self.variants)
        assert variant is not None
        assert variant.name in ["control", "treatment"]

    def test_consistent_assignment(self):
        v1 = self.mgr.assign_variant("flag1", "user1", self.variants)
        v2 = self.mgr.assign_variant("flag1", "user1", self.variants)
        assert v1.name == v2.name

    def test_get_assignment(self):
        self.mgr.assign_variant("flag1", "user1", self.variants)
        assignment = self.mgr.get_assignment("flag1", "user1")
        assert assignment is not None

    def test_clear_assignment(self):
        self.mgr.assign_variant("flag1", "user1", self.variants)
        self.mgr.clear_assignment("flag1", "user1")
        assert self.mgr.get_assignment("flag1", "user1") is None

    def test_empty_variants(self):
        variant = self.mgr.assign_variant("flag1", "user1", [])
        assert variant is None

    def test_weighted_distribution(self):
        weighted_variants = [
            Variant("heavy", "h", weight=9.0),
            Variant("light", "l", weight=1.0),
        ]
        counts = {"heavy": 0, "light": 0}
        for i in range(100):
            v = self.mgr.assign_variant("wf", f"u{i}", weighted_variants)
            counts[v.name] += 1
        # heavy가 약 90% - 너그럽게 허용
        assert counts["heavy"] >= 70


class TestFlagHistory:
    def setup_method(self):
        self.history = FlagHistory()

    def test_record(self):
        entry = self.history.record("flag1", "created")
        assert entry.flag_name == "flag1"
        assert entry.action == "created"
        assert "entry_id" in entry.to_dict()

    def test_get_flag_history(self):
        self.history.record("flag1", "created")
        self.history.record("flag1", "updated", changes={"enabled": True})
        self.history.record("flag2", "created")
        history = self.history.get_flag_history("flag1")
        assert len(history) == 2

    def test_get_all(self):
        self.history.record("f1", "created")
        self.history.record("f2", "created")
        all_entries = self.history.get_all()
        assert len(all_entries) == 2


class TestFlagOverride:
    def setup_method(self):
        self.override = FlagOverride()

    def test_set_user_override(self):
        record = self.override.set_user_override("flag1", "user1", True)
        assert record["value"] is True
        assert record["user_id"] == "user1"

    def test_get_user_override(self):
        self.override.set_user_override("flag1", "user1", False)
        value = self.override.get_user_override("flag1", "user1")
        assert value is False

    def test_get_user_override_none(self):
        assert self.override.get_user_override("flag1", "nobody") is None

    def test_set_env_override(self):
        self.override.set_env_override("flag1", "staging", True)
        value = self.override.get_env_override("flag1", "staging")
        assert value is True

    def test_remove_override(self):
        self.override.set_user_override("flag1", "user1", True)
        self.override.remove_override("flag1", "user1")
        assert self.override.get_user_override("flag1", "user1") is None

    def test_list_overrides(self):
        self.override.set_user_override("f1", "u1", True)
        self.override.set_env_override("f1", "prod", False)
        overrides = self.override.list_overrides()
        assert len(overrides) == 2


class TestFlagEvaluatorAdvanced:
    def setup_method(self):
        self.evaluator = FlagEvaluatorAdvanced()

    def test_disabled_flag(self):
        flag = FeatureFlag(name="f1", enabled=False)
        result = self.evaluator.evaluate(flag, user_id="u1")
        assert result["enabled"] is False
        assert result["reason"] == "disabled"

    def test_enabled_flag(self):
        flag = FeatureFlag(name="f1", enabled=True)
        result = self.evaluator.evaluate(flag, user_id="u1")
        assert result["enabled"] is True
        assert result["reason"] == "enabled"

    def test_targeting_rule_pass(self):
        flag = FeatureFlag(
            name="f1",
            enabled=True,
            rules=[TargetingRule("plan", "eq", "premium")],
        )
        result = self.evaluator.evaluate(flag, user_id="u1",
                                         context={"plan": "premium"})
        assert result["enabled"] is True

    def test_targeting_rule_fail(self):
        flag = FeatureFlag(
            name="f1",
            enabled=True,
            rules=[TargetingRule("plan", "eq", "premium")],
        )
        result = self.evaluator.evaluate(flag, user_id="u1",
                                         context={"plan": "free"})
        assert result["enabled"] is False
        assert result["reason"] == "targeting_rule_failed"

    def test_user_override_takes_priority(self):
        flag = FeatureFlag(name="f1", enabled=True)
        self.evaluator.get_override().set_user_override("f1", "u1", False)
        result = self.evaluator.evaluate(flag, user_id="u1")
        assert result["enabled"] is False
        assert result["reason"] == "user_override"

    def test_env_override(self):
        flag = FeatureFlag(name="f1", enabled=True)
        self.evaluator.get_override().set_env_override("f1", "staging", False)
        result = self.evaluator.evaluate(flag, user_id="", environment="staging")
        assert result["enabled"] is False
        assert result["reason"] == "env_override"

    def test_rollout_exclusion(self):
        # 0% rollout — all excluded
        flag = FeatureFlag(name="f1", enabled=True, rollout_percentage=0.0)
        result = self.evaluator.evaluate(flag, user_id="any_user")
        assert result["enabled"] is False
        assert result["reason"] == "rollout_excluded"

    def test_variant_assigned(self):
        flag = FeatureFlag(
            name="f1",
            enabled=True,
            variants=[
                Variant("A", "v_a", weight=1.0),
                Variant("B", "v_b", weight=1.0),
            ],
        )
        result = self.evaluator.evaluate(flag, user_id="u1")
        assert result["enabled"] is True
        assert result["variant"] in ["A", "B"]
