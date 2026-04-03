"""tests/test_feature_flags.py — Phase 59: 피쳐 플래그 테스트."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from src.feature_flags.feature_flag_manager import FeatureFlagManager
from src.feature_flags.flag_evaluator import FlagEvaluator
from src.feature_flags.percentage_rollout import PercentageRollout
from src.feature_flags.user_target_rollout import UserTargetRollout
from src.feature_flags.schedule_rollout import ScheduleRollout
from src.feature_flags.flag_audit_log import FlagAuditLog
from src.feature_flags.rollout_strategy import RolloutStrategy


class TestFeatureFlagManager:
    def setup_method(self):
        self.manager = FeatureFlagManager()

    def test_create_flag(self):
        flag = self.manager.create_flag("new_feature", enabled=True, description="Test")
        assert flag["name"] == "new_feature"
        assert flag["enabled"] is True
        assert flag["created_at"]

    def test_create_duplicate_raises(self):
        self.manager.create_flag("flag1")
        with pytest.raises(ValueError):
            self.manager.create_flag("flag1")

    def test_get_flag(self):
        self.manager.create_flag("flag1", enabled=True)
        flag = self.manager.get_flag("flag1")
        assert flag is not None
        assert flag["enabled"] is True

    def test_get_missing_flag(self):
        assert self.manager.get_flag("nonexistent") is None

    def test_update_flag(self):
        self.manager.create_flag("flag1", enabled=False)
        updated = self.manager.update_flag("flag1", enabled=True)
        assert updated["enabled"] is True

    def test_update_missing_raises(self):
        with pytest.raises(KeyError):
            self.manager.update_flag("nonexistent")

    def test_delete_flag(self):
        self.manager.create_flag("flag1")
        self.manager.delete_flag("flag1")
        assert self.manager.get_flag("flag1") is None

    def test_delete_missing_raises(self):
        with pytest.raises(KeyError):
            self.manager.delete_flag("nonexistent")

    def test_list_flags(self):
        self.manager.create_flag("f1")
        self.manager.create_flag("f2")
        flags = self.manager.list_flags()
        assert len(flags) == 2


class TestFlagEvaluator:
    def setup_method(self):
        self.manager = FeatureFlagManager()
        self.evaluator = FlagEvaluator(manager=self.manager)

    def test_missing_flag_returns_false(self):
        assert self.evaluator.evaluate("nonexistent") is False

    def test_disabled_flag_returns_false(self):
        self.manager.create_flag("flag1", enabled=False)
        assert self.evaluator.evaluate("flag1") is False

    def test_enabled_flag_returns_true(self):
        self.manager.create_flag("flag1", enabled=True)
        assert self.evaluator.evaluate("flag1") is True

    def test_with_strategy(self):
        self.manager.create_flag("flag1", enabled=True)
        strategy = UserTargetRollout(user_ids=["user1"])
        self.evaluator.set_strategy("flag1", strategy)
        assert self.evaluator.evaluate("flag1", user_id="user1") is True
        assert self.evaluator.evaluate("flag1", user_id="user2") is False


class TestPercentageRollout:
    def test_0_percent_always_false(self):
        rollout = PercentageRollout(0)
        for i in range(20):
            assert rollout.should_enable(user_id=f"user{i}") is False

    def test_100_percent_always_true(self):
        rollout = PercentageRollout(100)
        for i in range(20):
            assert rollout.should_enable(user_id=f"user{i}") is True

    def test_deterministic(self):
        rollout = PercentageRollout(50)
        result1 = rollout.should_enable(user_id="alice")
        result2 = rollout.should_enable(user_id="alice")
        assert result1 == result2

    def test_invalid_percentage(self):
        with pytest.raises(ValueError):
            PercentageRollout(101)
        with pytest.raises(ValueError):
            PercentageRollout(-1)

    def test_no_user_id_returns_false(self):
        rollout = PercentageRollout(100)
        assert rollout.should_enable() is False


class TestUserTargetRollout:
    def test_targeted_user_enabled(self):
        rollout = UserTargetRollout(user_ids=["user1", "user2"])
        assert rollout.should_enable(user_id="user1") is True

    def test_non_targeted_user_disabled(self):
        rollout = UserTargetRollout(user_ids=["user1"])
        assert rollout.should_enable(user_id="user3") is False

    def test_no_user_id_returns_false(self):
        rollout = UserTargetRollout(user_ids=["user1"])
        assert rollout.should_enable() is False


class TestScheduleRollout:
    def test_past_time_enables(self):
        past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        rollout = ScheduleRollout(enable_at=past)
        assert rollout.should_enable() is True

    def test_future_time_disables(self):
        future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        rollout = ScheduleRollout(enable_at=future)
        assert rollout.should_enable() is False

    def test_naive_datetime(self):
        past = datetime.utcnow() - timedelta(hours=1)
        rollout = ScheduleRollout(enable_at=past)
        assert rollout.should_enable() is True


class TestFlagAuditLog:
    def setup_method(self):
        self.log = FlagAuditLog()

    def test_record_and_get(self):
        self.log.record("flag1", "create", None, {"enabled": True})
        entries = self.log.get_log()
        assert len(entries) == 1
        assert entries[0]["flag_name"] == "flag1"

    def test_get_log_by_flag(self):
        self.log.record("flag1", "create", None, {})
        self.log.record("flag2", "create", None, {})
        entries = self.log.get_log(flag_name="flag1")
        assert len(entries) == 1

    def test_get_recent(self):
        for i in range(30):
            self.log.record(f"flag{i}", "create", None, {})
        recent = self.log.get_recent(limit=20)
        assert len(recent) == 20

    def test_record_with_user_id(self):
        self.log.record("flag1", "update", False, True, user_id="admin")
        entries = self.log.get_log("flag1")
        assert entries[0]["user_id"] == "admin"
