"""tests/test_points.py — Phase 92: 포인트/마일리지 시스템 테스트."""
from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.points.point_policy import PointPolicy, BonusType, EventBonus
from src.points.point_history import PointHistory, HistoryType, PointRecord
from src.points.point_manager import PointManager, MIN_USE_POINTS, MAX_USE_RATIO
from src.points.expiry_manager import ExpiryManager


# ===========================================================================
# PointPolicy
# ===========================================================================

class TestPointPolicy:
    def test_default_rates(self):
        policy = PointPolicy()
        assert policy.get_rate("bronze") == pytest.approx(0.01)
        assert policy.get_rate("silver") == pytest.approx(0.02)
        assert policy.get_rate("gold") == pytest.approx(0.03)
        assert policy.get_rate("vip") == pytest.approx(0.05)

    def test_unknown_grade_returns_bronze_rate(self):
        policy = PointPolicy()
        assert policy.get_rate("unknown") == pytest.approx(0.01)

    def test_set_rate_valid(self):
        policy = PointPolicy()
        policy.set_rate("silver", 0.03)
        assert policy.get_rate("silver") == pytest.approx(0.03)

    def test_set_rate_out_of_range(self):
        policy = PointPolicy()
        with pytest.raises(ValueError):
            policy.set_rate("gold", 1.5)

    def test_get_all_rates(self):
        policy = PointPolicy()
        rates = policy.get_all_rates()
        assert "bronze" in rates
        assert "vip" in rates

    def test_add_event(self):
        policy = PointPolicy()
        ev = policy.add_event("double2024", "더블 포인트", 2.0)
        assert ev.event_id == "double2024"
        assert ev.multiplier == 2.0
        assert ev.active is True

    def test_add_event_invalid_multiplier(self):
        policy = PointPolicy()
        with pytest.raises(ValueError):
            policy.add_event("bad", "나쁜 이벤트", -1.0)

    def test_deactivate_event(self):
        policy = PointPolicy()
        policy.add_event("ev1", "이벤트1", 2.0)
        assert policy.deactivate_event("ev1") is True
        assert len(policy.get_active_events()) == 0

    def test_deactivate_nonexistent_event(self):
        policy = PointPolicy()
        assert policy.deactivate_event("nonexistent") is False

    def test_event_multiplier_no_events(self):
        policy = PointPolicy()
        assert policy.get_event_multiplier() == 1.0

    def test_event_multiplier_with_active_event(self):
        policy = PointPolicy()
        policy.add_event("triple", "트리플 포인트", 3.0)
        assert policy.get_event_multiplier() == 3.0

    def test_calculate_earn_rate_no_event(self):
        policy = PointPolicy()
        rate = policy.calculate_earn_rate("gold", apply_event=False)
        assert rate == pytest.approx(0.03)

    def test_calculate_earn_rate_with_event(self):
        policy = PointPolicy()
        policy.add_event("double", "더블", 2.0)
        rate = policy.calculate_earn_rate("gold", apply_event=True)
        assert rate == pytest.approx(0.06)

    def test_calculate_earn_points(self):
        policy = PointPolicy()
        points = policy.calculate_earn_points(10000, "silver")
        assert points == 200  # 10000 * 0.02

    def test_special_bonus_first_purchase(self):
        policy = PointPolicy()
        assert policy.get_special_bonus(BonusType.FIRST_PURCHASE) == 1000

    def test_special_bonus_birthday(self):
        policy = PointPolicy()
        assert policy.get_special_bonus(BonusType.BIRTHDAY) == 500

    def test_special_bonus_review(self):
        policy = PointPolicy()
        assert policy.get_special_bonus(BonusType.REVIEW) == 200

    def test_set_special_bonus(self):
        policy = PointPolicy()
        policy.set_special_bonus(BonusType.REVIEW, 300)
        assert policy.get_special_bonus(BonusType.REVIEW) == 300

    def test_set_special_bonus_negative(self):
        policy = PointPolicy()
        with pytest.raises(ValueError):
            policy.set_special_bonus(BonusType.BIRTHDAY, -100)

    def test_to_dict(self):
        policy = PointPolicy()
        d = policy.to_dict()
        assert "rates" in d
        assert "events" in d
        assert "special_bonuses" in d


# ===========================================================================
# PointHistory
# ===========================================================================

class TestPointHistory:
    def test_record_earn(self):
        history = PointHistory()
        rec = history.record("U1", HistoryType.EARN, 100, 100, "주문 적립")
        assert rec.record_id
        assert rec.user_id == "U1"
        assert rec.type == HistoryType.EARN
        assert rec.amount == 100
        assert rec.balance_after == 100

    def test_record_use(self):
        history = PointHistory()
        history.record("U1", HistoryType.EARN, 2000, 2000, "적립")
        rec = history.record("U1", HistoryType.USE, 1000, 1000, "사용")
        assert rec.type == HistoryType.USE

    def test_query_all(self):
        history = PointHistory()
        history.record("U1", HistoryType.EARN, 100, 100, "a")
        history.record("U1", HistoryType.USE, 50, 50, "b")
        result = history.query("U1")
        assert result["total"] == 2

    def test_query_by_type(self):
        history = PointHistory()
        history.record("U1", HistoryType.EARN, 100, 100, "a")
        history.record("U1", HistoryType.USE, 50, 50, "b")
        result = history.query("U1", history_type="earn")
        assert result["total"] == 1
        assert result["records"][0]["type"] == "earn"

    def test_query_pagination(self):
        history = PointHistory()
        for i in range(5):
            history.record("U1", HistoryType.EARN, 100, 100 * (i + 1), f"적립{i}")
        result = history.query("U1", page=1, per_page=2)
        assert len(result["records"]) == 2
        assert result["total"] == 5
        assert result["pages"] == 3

    def test_query_with_order_id(self):
        history = PointHistory()
        rec = history.record("U1", HistoryType.EARN, 100, 100, "주문", order_id="ORD-001")
        assert rec.order_id == "ORD-001"

    def test_to_dict(self):
        history = PointHistory()
        rec = history.record("U1", HistoryType.EARN, 100, 100, "테스트")
        d = rec.to_dict()
        assert "record_id" in d
        assert "user_id" in d
        assert "type" in d

    def test_get_all_for_user(self):
        history = PointHistory()
        history.record("U1", HistoryType.EARN, 100, 100, "a")
        history.record("U2", HistoryType.EARN, 200, 200, "b")
        records = history.get_all_for_user("U1")
        assert len(records) == 1

    def test_query_different_users(self):
        history = PointHistory()
        history.record("U1", HistoryType.EARN, 100, 100, "a")
        history.record("U2", HistoryType.EARN, 200, 200, "b")
        assert history.query("U1")["total"] == 1
        assert history.query("U2")["total"] == 1


# ===========================================================================
# PointManager
# ===========================================================================

class TestPointManagerEarn:
    def test_earn_increases_balance(self):
        mgr = PointManager()
        mgr.earn("U1", 500, "주문")
        assert mgr.get_balance("U1") == 500

    def test_earn_multiple(self):
        mgr = PointManager()
        mgr.earn("U1", 500, "주문1")
        mgr.earn("U1", 300, "주문2")
        assert mgr.get_balance("U1") == 800

    def test_earn_zero_raises(self):
        mgr = PointManager()
        with pytest.raises(ValueError):
            mgr.earn("U1", 0, "잘못된 적립")

    def test_earn_negative_raises(self):
        mgr = PointManager()
        with pytest.raises(ValueError):
            mgr.earn("U1", -100, "잘못된 적립")

    def test_earn_records_history(self):
        mgr = PointManager()
        mgr.earn("U1", 500, "주문")
        hist = mgr.history.query("U1")
        assert hist["total"] == 1
        assert hist["records"][0]["type"] == "earn"

    def test_earn_from_order_bronze(self):
        mgr = PointManager()
        mgr.earn_from_order("U1", 10000, "bronze", "ORD-001")
        # bronze 1% = 100 포인트
        assert mgr.get_balance("U1") == 100

    def test_earn_from_order_vip(self):
        mgr = PointManager()
        mgr.earn_from_order("U1", 10000, "vip", "ORD-001")
        # vip 5% = 500 포인트
        assert mgr.get_balance("U1") == 500

    def test_earn_special_first_purchase(self):
        mgr = PointManager()
        lot = mgr.earn_special("U1", BonusType.FIRST_PURCHASE)
        assert lot is not None
        assert mgr.get_balance("U1") == 1000

    def test_get_lots_for_user(self):
        mgr = PointManager()
        mgr.earn("U1", 500, "주문1")
        mgr.earn("U1", 300, "주문2")
        lots = mgr.get_lots_for_user("U1")
        assert len(lots) == 2

    def test_lot_has_expiry(self):
        mgr = PointManager()
        lot = mgr.earn("U1", 500, "주문")
        assert lot.expires_at > lot.earned_at


class TestPointManagerUse:
    def test_use_success(self):
        mgr = PointManager()
        mgr.earn("U1", 5000, "적립")
        deducted = mgr.use("U1", 2000, 10000, "결제")
        assert deducted == 2000
        assert mgr.get_balance("U1") == 3000

    def test_use_below_minimum(self):
        mgr = PointManager()
        mgr.earn("U1", 5000, "적립")
        with pytest.raises(ValueError, match="최소"):
            mgr.use("U1", 500, 10000, "결제")

    def test_use_exceeds_ratio(self):
        mgr = PointManager()
        mgr.earn("U1", 10000, "적립")
        # payment_amount=10000, 50% = 5000; 요청 6000 → 초과
        with pytest.raises(ValueError, match="이하만"):
            mgr.use("U1", 6000, 10000, "결제")

    def test_use_insufficient_balance(self):
        mgr = PointManager()
        mgr.earn("U1", 1500, "적립")
        with pytest.raises(ValueError, match="잔액"):
            mgr.use("U1", 2000, 10000, "결제")

    def test_use_records_history(self):
        mgr = PointManager()
        mgr.earn("U1", 5000, "적립")
        mgr.use("U1", 2000, 10000, "결제")
        result = mgr.history.query("U1", history_type="use")
        assert result["total"] == 1

    def test_cancel_use_restores_balance(self):
        mgr = PointManager()
        mgr.earn("U1", 5000, "적립")
        mgr.use("U1", 2000, 10000, "결제")
        mgr.cancel_use("U1", 2000, "주문 취소")
        assert mgr.get_balance("U1") == 5000

    def test_cancel_use_records_history(self):
        mgr = PointManager()
        mgr.earn("U1", 5000, "적립")
        mgr.use("U1", 2000, 10000, "결제")
        mgr.cancel_use("U1", 2000, "주문 취소")
        result = mgr.history.query("U1", history_type="cancel")
        assert result["total"] == 1

    def test_initial_balance_zero(self):
        mgr = PointManager()
        assert mgr.get_balance("UNKNOWN") == 0


# ===========================================================================
# ExpiryManager
# ===========================================================================

class TestExpiryManager:
    def test_get_expiring_empty(self):
        mgr = PointManager()
        expiry = ExpiryManager(point_manager=mgr)
        result = expiry.get_expiring_lots("U1", within_days=30)
        assert result == []

    def test_get_expiring_within_7_days(self):
        mgr = PointManager()
        expiry = ExpiryManager(point_manager=mgr, history=mgr.history)
        # 5일 후 만료되는 포인트 적립
        mgr.earn("U1", 1000, "적립", expiry_days=5)
        # 60일 후 만료
        mgr.earn("U1", 2000, "적립", expiry_days=60)
        result = expiry.get_expiring_lots("U1", within_days=7)
        assert len(result) == 1
        assert result[0]["remaining"] == 1000

    def test_get_expiring_within_30_days(self):
        mgr = PointManager()
        expiry = ExpiryManager(point_manager=mgr, history=mgr.history)
        mgr.earn("U1", 1000, "적립", expiry_days=5)
        mgr.earn("U1", 2000, "적립", expiry_days=15)
        mgr.earn("U1", 3000, "적립", expiry_days=60)
        result = expiry.get_expiring_lots("U1", within_days=30)
        assert len(result) == 2

    def test_run_expiry_batch_expires_old_lots(self):
        mgr = PointManager()
        expiry = ExpiryManager(point_manager=mgr, history=mgr.history)
        mgr.earn("U1", 1000, "적립", expiry_days=1)
        # 과거 시점으로 만료 배치 실행
        past = datetime.now(timezone.utc) + timedelta(days=2)
        result = expiry.run_expiry_batch(now=past)
        assert result["expired_lots"] == 1
        assert result["expired_points"] == 1000
        assert "U1" in result["affected_users"]
        assert mgr.get_balance("U1") == 0

    def test_run_expiry_batch_records_history(self):
        mgr = PointManager()
        expiry = ExpiryManager(point_manager=mgr, history=mgr.history)
        mgr.earn("U1", 1000, "적립", expiry_days=1)
        past = datetime.now(timezone.utc) + timedelta(days=2)
        expiry.run_expiry_batch(now=past)
        result = mgr.history.query("U1", history_type="expire")
        assert result["total"] == 1

    def test_run_expiry_batch_no_expired(self):
        mgr = PointManager()
        expiry = ExpiryManager(point_manager=mgr, history=mgr.history)
        mgr.earn("U1", 1000, "적립", expiry_days=365)
        result = expiry.run_expiry_batch()
        assert result["expired_lots"] == 0

    def test_expiry_notifications_generated(self):
        mgr = PointManager()
        expiry = ExpiryManager(point_manager=mgr, history=mgr.history)
        mgr.earn("U1", 500, "적립", expiry_days=1)
        past = datetime.now(timezone.utc) + timedelta(days=2)
        expiry.run_expiry_batch(now=past)
        notifs = expiry.get_notifications()
        assert len(notifs) == 1
        assert notifs[0]["user_id"] == "U1"

    def test_days_until_expiry_in_result(self):
        mgr = PointManager()
        expiry = ExpiryManager(point_manager=mgr, history=mgr.history)
        mgr.earn("U1", 1000, "적립", expiry_days=5)
        result = expiry.get_expiring_lots("U1", within_days=7)
        assert "days_until_expiry" in result[0]


# ===========================================================================
# Points API (Flask 통합 테스트)
# ===========================================================================

@pytest.fixture
def points_app():
    """포인트 API Blueprint이 등록된 Flask 테스트 클라이언트."""
    import src.order_webhook as wh
    wh.app.config["TESTING"] = True
    with wh.app.test_client() as c:
        yield c


class TestPointsAPI:
    def test_get_balance(self, points_app):
        resp = points_app.get("/api/v1/points/USER1/balance")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "balance" in data

    def test_earn_endpoint(self, points_app):
        resp = points_app.post(
            "/api/v1/points/USER1/earn",
            json={"amount": 500, "reason": "테스트 적립"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "lot" in data
        assert "balance" in data

    def test_earn_missing_fields(self, points_app):
        resp = points_app.post("/api/v1/points/USER1/earn", json={"amount": 500})
        assert resp.status_code == 400

    def test_use_endpoint(self, points_app):
        # 먼저 적립
        points_app.post("/api/v1/points/USERX/earn", json={"amount": 5000, "reason": "적립"})
        resp = points_app.post(
            "/api/v1/points/USERX/use",
            json={"use_amount": 1000, "payment_amount": 10000, "reason": "결제"},
        )
        assert resp.status_code == 200

    def test_use_insufficient(self, points_app):
        resp = points_app.post(
            "/api/v1/points/USERNEW/use",
            json={"use_amount": 5000, "payment_amount": 10000, "reason": "결제"},
        )
        assert resp.status_code == 400

    def test_history_endpoint(self, points_app):
        points_app.post("/api/v1/points/USERH/earn", json={"amount": 1000, "reason": "적립"})
        resp = points_app.get("/api/v1/points/USERH/history")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "records" in data

    def test_expiring_endpoint(self, points_app):
        resp = points_app.get("/api/v1/points/USER1/expiring")
        assert resp.status_code == 200

    def test_expire_run_endpoint(self, points_app):
        resp = points_app.post("/api/v1/points/expire/run")
        assert resp.status_code == 200

    def test_policy_get(self, points_app):
        resp = points_app.get("/api/v1/points/policy")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "rates" in data

    def test_policy_update(self, points_app):
        resp = points_app.put(
            "/api/v1/points/policy",
            json={"rates": {"bronze": 0.015}},
        )
        assert resp.status_code == 200
