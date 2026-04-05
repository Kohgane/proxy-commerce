"""tests/test_logistics.py — 물류 최적화 Phase 99 테스트."""
from __future__ import annotations

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── TestLogisticsModels ────────────────────────────────────────────────────

class TestLogisticsModels:
    def test_delivery_status_values(self):
        from src.logistics.logistics_models import DeliveryStatus
        assert DeliveryStatus.assigned.value == "assigned"
        assert DeliveryStatus.delivered.value == "delivered"
        assert DeliveryStatus.failed.value == "failed"

    def test_delivery_status_all_members(self):
        from src.logistics.logistics_models import DeliveryStatus
        members = {s.value for s in DeliveryStatus}
        assert "assigned" in members
        assert "picked_up" in members
        assert "in_transit" in members
        assert "near_destination" in members
        assert "delivered" in members
        assert "failed" in members

    def test_coordinate(self):
        from src.logistics.logistics_models import Coordinate
        c = Coordinate(lat=37.5, lon=127.0)
        assert c.lat == 37.5
        assert c.lon == 127.0

    def test_delivery_stop_defaults(self):
        from src.logistics.logistics_models import Coordinate, DeliveryStop
        c = Coordinate(lat=37.5, lon=127.0)
        s = DeliveryStop(stop_id="s1", address="서울", coordinate=c, order_id="o1")
        assert s.weight_kg == 1.0
        assert s.delivered is False
        assert s.priority == 1

    def test_delivery_stop_custom(self):
        from src.logistics.logistics_models import Coordinate, DeliveryStop
        c = Coordinate(lat=37.5, lon=127.0)
        s = DeliveryStop(stop_id="s2", address="부산", coordinate=c, order_id="o2",
                         weight_kg=5.0, priority=2)
        assert s.weight_kg == 5.0
        assert s.priority == 2

    def test_route_result_to_dict(self):
        from src.logistics.logistics_models import Coordinate, DeliveryStop, RouteResult
        c = Coordinate(lat=37.5, lon=127.0)
        stop = DeliveryStop(stop_id="s1", address="addr", coordinate=c, order_id="o1")
        route = RouteResult(route_id="r1", stops=[stop], total_distance_km=10.0,
                            estimated_duration_min=30.0, strategy_used="nearest_neighbor")
        d = route.to_dict()
        assert d["route_id"] == "r1"
        assert d["total_distance_km"] == 10.0
        assert len(d["stops"]) == 1

    def test_delivery_agent_to_dict(self):
        from src.logistics.logistics_models import Coordinate, DeliveryAgent
        c = Coordinate(lat=37.5, lon=127.0)
        agent = DeliveryAgent(agent_id="a1", name="홍길동", phone="010-1234-5678",
                              current_location=c)
        d = agent.to_dict()
        assert d["agent_id"] == "a1"
        assert d["name"] == "홍길동"
        assert d["status"] == "available"

    def test_delivery_agent_defaults(self):
        from src.logistics.logistics_models import Coordinate, DeliveryAgent
        c = Coordinate(lat=37.5, lon=127.0)
        agent = DeliveryAgent(agent_id="a2", name="김철수", phone="010-0000-0000",
                              current_location=c)
        assert agent.capacity_kg == 50.0
        assert agent.vehicle_type == "motorcycle"
        assert agent.assigned_deliveries == []

    def test_delivery_record_to_dict(self):
        from src.logistics.logistics_models import Coordinate, DeliveryRecord, DeliveryStatus
        pc = Coordinate(lat=37.5, lon=127.0)
        dc = Coordinate(lat=37.6, lon=127.1)
        rec = DeliveryRecord(delivery_id="d1", agent_id="a1", order_id="o1",
                             pickup_address="픽업", delivery_address="배송지",
                             pickup_coordinate=pc, delivery_coordinate=dc)
        d = rec.to_dict()
        assert d["delivery_id"] == "d1"
        assert d["status"] == "assigned"

    def test_delivery_record_default_status(self):
        from src.logistics.logistics_models import Coordinate, DeliveryRecord, DeliveryStatus
        pc = Coordinate(lat=37.5, lon=127.0)
        dc = Coordinate(lat=37.6, lon=127.1)
        rec = DeliveryRecord(delivery_id="d2", agent_id="", order_id="o2",
                             pickup_address="", delivery_address="",
                             pickup_coordinate=pc, delivery_coordinate=dc)
        assert rec.status == DeliveryStatus.assigned

    def test_proof_of_delivery_to_dict(self):
        from src.logistics.logistics_models import ProofOfDelivery
        pod = ProofOfDelivery(delivery_id="d1", recipient_name="수령인")
        d = pod.to_dict()
        assert d["delivery_id"] == "d1"
        assert d["recipient_name"] == "수령인"
        assert "delivered_at" in d

    def test_proof_of_delivery_defaults(self):
        from src.logistics.logistics_models import ProofOfDelivery
        pod = ProofOfDelivery(delivery_id="d2", recipient_name="test")
        assert pod.signature_data == "mock_signature"
        assert pod.photo_url == "mock_photo.jpg"
        assert pod.notes == ""

    def test_delivery_time_window_to_dict(self):
        from src.logistics.logistics_models import DeliveryTimeWindow
        w = DeliveryTimeWindow(window_id="w1", name="오전", start_hour=9, end_hour=12)
        d = w.to_dict()
        assert d["name"] == "오전"
        assert d["surcharge_rate"] == 0.0

    def test_carrier_info_to_dict(self):
        from src.logistics.logistics_models import CarrierInfo
        c = CarrierInfo(carrier_id="CJ", name="CJ대한통운", base_rate=3000.0, per_kg_rate=200.0)
        d = c.to_dict()
        assert d["carrier_id"] == "CJ"
        assert d["base_rate"] == 3000.0

    def test_consolidation_group_to_dict(self):
        from src.logistics.logistics_models import ConsolidationGroup
        g = ConsolidationGroup(group_id="g1", order_ids=["o1", "o2"], region="서울",
                               estimated_saving=500.0, original_cost=5000.0, consolidated_cost=4500.0)
        d = g.to_dict()
        assert d["group_id"] == "g1"
        assert d["estimated_saving"] == 500.0

    def test_logistics_kpi_data_to_dict(self):
        from src.logistics.logistics_models import LogisticsKPIData
        kpi = LogisticsKPIData(on_time_rate=0.9, total_deliveries=100,
                               successful_deliveries=90, failed_deliveries=10)
        d = kpi.to_dict()
        assert d["on_time_rate"] == 0.9
        assert d["total_deliveries"] == 100


# ── TestDistanceCalculator ─────────────────────────────────────────────────

class TestDistanceCalculator:
    def test_haversine_same_point(self):
        from src.logistics.logistics_models import Coordinate
        from src.logistics.route_optimizer import DistanceCalculator
        c = Coordinate(lat=37.5665, lon=126.9780)
        assert DistanceCalculator.haversine(c, c) == pytest.approx(0.0, abs=1e-9)

    def test_haversine_known_distance(self):
        from src.logistics.logistics_models import Coordinate
        from src.logistics.route_optimizer import DistanceCalculator
        # 서울 - 부산 약 325km
        seoul = Coordinate(lat=37.5665, lon=126.9780)
        busan = Coordinate(lat=35.1796, lon=129.0756)
        dist = DistanceCalculator.haversine(seoul, busan)
        assert 300 < dist < 400

    def test_haversine_symmetry(self):
        from src.logistics.logistics_models import Coordinate
        from src.logistics.route_optimizer import DistanceCalculator
        a = Coordinate(lat=37.5, lon=127.0)
        b = Coordinate(lat=35.1, lon=129.0)
        assert DistanceCalculator.haversine(a, b) == pytest.approx(
            DistanceCalculator.haversine(b, a), rel=1e-6
        )

    def test_haversine_short_distance(self):
        from src.logistics.logistics_models import Coordinate
        from src.logistics.route_optimizer import DistanceCalculator
        a = Coordinate(lat=37.5, lon=127.0)
        b = Coordinate(lat=37.501, lon=127.001)
        dist = DistanceCalculator.haversine(a, b)
        assert 0 < dist < 1

    def test_distance_matrix_empty(self):
        from src.logistics.route_optimizer import DistanceCalculator
        matrix = DistanceCalculator.distance_matrix([])
        assert matrix == []

    def test_distance_matrix_size(self):
        from src.logistics.logistics_models import Coordinate, DeliveryStop
        from src.logistics.route_optimizer import DistanceCalculator
        stops = [
            DeliveryStop(stop_id=f"s{i}", address=f"addr{i}",
                         coordinate=Coordinate(lat=37.5 + i * 0.01, lon=127.0),
                         order_id=f"o{i}")
            for i in range(4)
        ]
        matrix = DistanceCalculator.distance_matrix(stops)
        assert len(matrix) == 4
        assert all(len(row) == 4 for row in matrix)

    def test_distance_matrix_diagonal_zero(self):
        from src.logistics.logistics_models import Coordinate, DeliveryStop
        from src.logistics.route_optimizer import DistanceCalculator
        stops = [
            DeliveryStop(stop_id=f"s{i}", address="",
                         coordinate=Coordinate(lat=37.5 + i * 0.01, lon=127.0),
                         order_id=f"o{i}")
            for i in range(3)
        ]
        matrix = DistanceCalculator.distance_matrix(stops)
        for i in range(3):
            assert matrix[i][i] == pytest.approx(0.0)


# ── TestRouteStrategies ────────────────────────────────────────────────────

class TestRouteStrategies:
    def _make_stops(self, n=5):
        from src.logistics.logistics_models import Coordinate, DeliveryStop
        return [
            DeliveryStop(stop_id=f"s{i}", address=f"addr{i}",
                         coordinate=Coordinate(lat=37.5 + i * 0.01, lon=127.0 + i * 0.01),
                         order_id=f"o{i}", weight_kg=2.0, volume_m3=0.02)
            for i in range(n)
        ]

    def _depot(self):
        from src.logistics.logistics_models import Coordinate
        return Coordinate(lat=37.5, lon=127.0)

    def test_nearest_neighbor_returns_list(self):
        from src.logistics.route_optimizer import NearestNeighborStrategy, RouteConstraint
        strategy = NearestNeighborStrategy()
        stops = self._make_stops(5)
        result = strategy.optimize(stops, self._depot(), RouteConstraint())
        assert isinstance(result, list)

    def test_nearest_neighbor_empty(self):
        from src.logistics.route_optimizer import NearestNeighborStrategy, RouteConstraint
        strategy = NearestNeighborStrategy()
        result = strategy.optimize([], self._depot(), RouteConstraint())
        assert result == []

    def test_nearest_neighbor_capacity_limit(self):
        from src.logistics.route_optimizer import NearestNeighborStrategy, RouteConstraint
        strategy = NearestNeighborStrategy()
        stops = self._make_stops(10)
        constraints = RouteConstraint(vehicle_capacity_kg=5.0)
        result = strategy.optimize(stops, self._depot(), constraints)
        total_weight = sum(s.weight_kg for s in result)
        assert total_weight <= 5.0

    def test_two_opt_returns_list(self):
        from src.logistics.route_optimizer import TwoOptStrategy, RouteConstraint
        strategy = TwoOptStrategy()
        stops = self._make_stops(5)
        result = strategy.optimize(stops, self._depot(), RouteConstraint())
        assert isinstance(result, list)

    def test_two_opt_empty(self):
        from src.logistics.route_optimizer import TwoOptStrategy, RouteConstraint
        strategy = TwoOptStrategy()
        result = strategy.optimize([], self._depot(), RouteConstraint())
        assert result == []

    def test_two_opt_single(self):
        from src.logistics.route_optimizer import TwoOptStrategy, RouteConstraint
        strategy = TwoOptStrategy()
        stops = self._make_stops(1)
        result = strategy.optimize(stops, self._depot(), RouteConstraint())
        assert len(result) == 1

    def test_two_opt_two_stops(self):
        from src.logistics.route_optimizer import TwoOptStrategy, RouteConstraint
        strategy = TwoOptStrategy()
        stops = self._make_stops(2)
        result = strategy.optimize(stops, self._depot(), RouteConstraint())
        assert len(result) == 2

    def test_cluster_first_returns_list(self):
        from src.logistics.route_optimizer import ClusterFirstRouteSecond, RouteConstraint
        strategy = ClusterFirstRouteSecond()
        stops = self._make_stops(6)
        result = strategy.optimize(stops, self._depot(), RouteConstraint())
        assert isinstance(result, list)

    def test_cluster_first_empty(self):
        from src.logistics.route_optimizer import ClusterFirstRouteSecond, RouteConstraint
        strategy = ClusterFirstRouteSecond()
        result = strategy.optimize([], self._depot(), RouteConstraint())
        assert result == []


# ── TestRouteOptimizer ─────────────────────────────────────────────────────

class TestRouteOptimizer:
    def _make_stops(self, n=3):
        from src.logistics.logistics_models import Coordinate, DeliveryStop
        return [
            DeliveryStop(stop_id=f"s{i}", address=f"addr{i}",
                         coordinate=Coordinate(lat=37.5 + i * 0.01, lon=127.0),
                         order_id=f"o{i}", weight_kg=2.0)
            for i in range(n)
        ]

    def _depot(self):
        from src.logistics.logistics_models import Coordinate
        return Coordinate(lat=37.5, lon=127.0)

    def test_optimize_returns_route_result(self):
        from src.logistics.route_optimizer import RouteOptimizer
        opt = RouteOptimizer()
        result = opt.optimize(self._make_stops(3), self._depot())
        assert result.route_id
        assert result.total_distance_km >= 0
        assert result.estimated_duration_min >= 0

    def test_optimize_stores_route(self):
        from src.logistics.route_optimizer import RouteOptimizer
        opt = RouteOptimizer()
        result = opt.optimize(self._make_stops(3), self._depot())
        fetched = opt.get_route(result.route_id)
        assert fetched is not None
        assert fetched.route_id == result.route_id

    def test_get_route_not_found(self):
        from src.logistics.route_optimizer import RouteOptimizer
        opt = RouteOptimizer()
        assert opt.get_route("nonexistent") is None

    def test_list_routes_empty(self):
        from src.logistics.route_optimizer import RouteOptimizer
        opt = RouteOptimizer()
        assert opt.list_routes() == []

    def test_list_routes_multiple(self):
        from src.logistics.route_optimizer import RouteOptimizer
        opt = RouteOptimizer()
        opt.optimize(self._make_stops(2), self._depot())
        opt.optimize(self._make_stops(2), self._depot())
        assert len(opt.list_routes()) == 2

    def test_optimize_nearest_neighbor_strategy(self):
        from src.logistics.route_optimizer import RouteOptimizer
        opt = RouteOptimizer()
        result = opt.optimize(self._make_stops(3), self._depot(), strategy="nearest_neighbor")
        assert result.strategy_used == "nearest_neighbor"

    def test_optimize_two_opt_strategy(self):
        from src.logistics.route_optimizer import RouteOptimizer
        opt = RouteOptimizer()
        result = opt.optimize(self._make_stops(4), self._depot(), strategy="two_opt")
        assert result.strategy_used == "two_opt"

    def test_optimize_cluster_first_strategy(self):
        from src.logistics.route_optimizer import RouteOptimizer
        opt = RouteOptimizer()
        result = opt.optimize(self._make_stops(4), self._depot(), strategy="cluster_first")
        assert result.strategy_used == "cluster_first"

    def test_optimize_empty_stops(self):
        from src.logistics.route_optimizer import RouteOptimizer
        opt = RouteOptimizer()
        result = opt.optimize([], self._depot())
        assert result.total_distance_km == 0.0
        assert len(result.stops) == 0


# ── TestLastMileTracker ────────────────────────────────────────────────────

class TestLastMileTracker:
    def _coords(self):
        from src.logistics.logistics_models import Coordinate
        return Coordinate(lat=37.5665, lon=126.9780), Coordinate(lat=37.4979, lon=127.0276)

    def test_create_delivery(self):
        from src.logistics.last_mile import LastMileTracker
        tracker = LastMileTracker()
        pc, dc = self._coords()
        rec = tracker.create_delivery("o1", "픽업", "배송지", pc, dc)
        assert rec.delivery_id
        assert rec.order_id == "o1"
        assert rec.distance_km > 0

    def test_get_delivery(self):
        from src.logistics.last_mile import LastMileTracker
        tracker = LastMileTracker()
        pc, dc = self._coords()
        rec = tracker.create_delivery("o2", "픽업", "배송지", pc, dc)
        fetched = tracker.get_delivery(rec.delivery_id)
        assert fetched is not None
        assert fetched.delivery_id == rec.delivery_id

    def test_get_delivery_not_found(self):
        from src.logistics.last_mile import LastMileTracker
        tracker = LastMileTracker()
        assert tracker.get_delivery("nonexistent") is None

    def test_list_deliveries_empty(self):
        from src.logistics.last_mile import LastMileTracker
        tracker = LastMileTracker()
        assert tracker.list_deliveries() == []

    def test_list_deliveries_with_filter(self):
        from src.logistics.last_mile import LastMileTracker
        from src.logistics.logistics_models import DeliveryStatus
        tracker = LastMileTracker()
        pc, dc = self._coords()
        tracker.create_delivery("o3", "픽업", "배송지", pc, dc)
        result = tracker.list_deliveries(DeliveryStatus.assigned)
        assert len(result) == 1

    def test_update_status_valid_transition(self):
        from src.logistics.last_mile import LastMileTracker
        from src.logistics.logistics_models import DeliveryStatus
        tracker = LastMileTracker()
        pc, dc = self._coords()
        rec = tracker.create_delivery("o4", "픽업", "배송지", pc, dc)
        updated = tracker.update_status(rec.delivery_id, DeliveryStatus.picked_up)
        assert updated.status == DeliveryStatus.picked_up

    def test_update_status_invalid_transition(self):
        from src.logistics.last_mile import LastMileTracker
        from src.logistics.logistics_models import DeliveryStatus
        tracker = LastMileTracker()
        pc, dc = self._coords()
        rec = tracker.create_delivery("o5", "픽업", "배송지", pc, dc)
        with pytest.raises(ValueError):
            tracker.update_status(rec.delivery_id, DeliveryStatus.delivered)

    def test_update_status_not_found(self):
        from src.logistics.last_mile import LastMileTracker
        from src.logistics.logistics_models import DeliveryStatus
        tracker = LastMileTracker()
        with pytest.raises(KeyError):
            tracker.update_status("nonexistent", DeliveryStatus.picked_up)

    def test_update_location(self):
        from src.logistics.last_mile import LastMileTracker
        from src.logistics.logistics_models import Coordinate
        tracker = LastMileTracker()
        pc, dc = self._coords()
        rec = tracker.create_delivery("o6", "픽업", "배송지", pc, dc)
        new_loc = Coordinate(lat=37.52, lon=127.01)
        updated = tracker.update_location(rec.delivery_id, new_loc)
        assert updated.eta_minutes >= 0

    def test_calculate_eta(self):
        from src.logistics.last_mile import LastMileTracker
        tracker = LastMileTracker()
        pc, dc = self._coords()
        rec = tracker.create_delivery("o7", "픽업", "배송지", pc, dc)
        eta = tracker.calculate_eta(rec.delivery_id)
        assert eta >= 0

    def test_calculate_eta_not_found(self):
        from src.logistics.last_mile import LastMileTracker
        tracker = LastMileTracker()
        with pytest.raises(KeyError):
            tracker.calculate_eta("nonexistent")

    def test_full_status_transition(self):
        from src.logistics.last_mile import LastMileTracker
        from src.logistics.logistics_models import DeliveryStatus
        tracker = LastMileTracker()
        pc, dc = self._coords()
        rec = tracker.create_delivery("o8", "픽업", "배송지", pc, dc)
        tracker.update_status(rec.delivery_id, DeliveryStatus.picked_up)
        tracker.update_status(rec.delivery_id, DeliveryStatus.in_transit)
        tracker.update_status(rec.delivery_id, DeliveryStatus.near_destination)
        tracker.update_status(rec.delivery_id, DeliveryStatus.delivered)
        final = tracker.get_delivery(rec.delivery_id)
        assert final.status == DeliveryStatus.delivered


# ── TestDeliveryAssignment ─────────────────────────────────────────────────

class TestDeliveryAssignment:
    def _coord(self):
        from src.logistics.logistics_models import Coordinate
        return Coordinate(lat=37.5665, lon=126.9780)

    def test_register_agent(self):
        from src.logistics.last_mile import DeliveryAssignment
        assignment = DeliveryAssignment()
        agent = assignment.register_agent("홍길동", "010-1234-5678", self._coord())
        assert agent.agent_id
        assert agent.name == "홍길동"

    def test_get_agent(self):
        from src.logistics.last_mile import DeliveryAssignment
        assignment = DeliveryAssignment()
        agent = assignment.register_agent("김철수", "010-0000-0000", self._coord())
        fetched = assignment.get_agent(agent.agent_id)
        assert fetched is not None

    def test_get_agent_not_found(self):
        from src.logistics.last_mile import DeliveryAssignment
        assignment = DeliveryAssignment()
        assert assignment.get_agent("nonexistent") is None

    def test_list_agents_empty(self):
        from src.logistics.last_mile import DeliveryAssignment
        assignment = DeliveryAssignment()
        assert assignment.list_agents() == []

    def test_list_agents_by_status(self):
        from src.logistics.last_mile import DeliveryAssignment
        assignment = DeliveryAssignment()
        assignment.register_agent("기사1", "010-1111-1111", self._coord())
        available = assignment.list_agents("available")
        assert len(available) == 1

    def test_assign_best_agent(self):
        from src.logistics.last_mile import DeliveryAssignment, LastMileTracker
        from src.logistics.logistics_models import Coordinate
        assignment = DeliveryAssignment()
        assignment.register_agent("기사A", "010-2222-2222", self._coord())
        tracker = LastMileTracker()
        pc = Coordinate(lat=37.5665, lon=126.9780)
        dc = Coordinate(lat=37.4979, lon=127.0276)
        rec = tracker.create_delivery("o_assign", "픽업", "배송지", pc, dc)
        agent = assignment.assign_best_agent(rec)
        assert agent is not None
        assert rec.delivery_id in agent.assigned_deliveries

    def test_assign_no_available_agents(self):
        from src.logistics.last_mile import DeliveryAssignment, LastMileTracker
        from src.logistics.logistics_models import Coordinate
        assignment = DeliveryAssignment()
        tracker = LastMileTracker()
        pc = Coordinate(lat=37.5665, lon=126.9780)
        dc = Coordinate(lat=37.4979, lon=127.0276)
        rec = tracker.create_delivery("o_no_agent", "픽업", "배송지", pc, dc)
        result = assignment.assign_best_agent(rec)
        assert result is None


# ── TestProofOfDeliveryService ─────────────────────────────────────────────

class TestProofOfDeliveryService:
    def test_record_proof(self):
        from src.logistics.last_mile import ProofOfDeliveryService
        svc = ProofOfDeliveryService()
        proof = svc.record_proof("d1", "수령인A")
        assert proof.delivery_id == "d1"
        assert proof.recipient_name == "수령인A"

    def test_get_proof(self):
        from src.logistics.last_mile import ProofOfDeliveryService
        svc = ProofOfDeliveryService()
        svc.record_proof("d2", "수령인B", notes="현관 앞")
        proof = svc.get_proof("d2")
        assert proof is not None
        assert proof.notes == "현관 앞"

    def test_get_proof_not_found(self):
        from src.logistics.last_mile import ProofOfDeliveryService
        svc = ProofOfDeliveryService()
        assert svc.get_proof("nonexistent") is None

    def test_record_proof_with_gps(self):
        from src.logistics.last_mile import ProofOfDeliveryService
        from src.logistics.logistics_models import Coordinate
        svc = ProofOfDeliveryService()
        gps = Coordinate(lat=37.5, lon=127.0)
        proof = svc.record_proof("d3", "수령인C", gps_coord=gps)
        assert proof.gps_coordinate is not None
        assert proof.gps_coordinate.lat == 37.5

    def test_proof_to_dict(self):
        from src.logistics.last_mile import ProofOfDeliveryService
        svc = ProofOfDeliveryService()
        proof = svc.record_proof("d4", "수령인D")
        d = proof.to_dict()
        assert d["delivery_id"] == "d4"
        assert "delivered_at" in d


# ── TestDeliveryTimeWindowManager ─────────────────────────────────────────

class TestDeliveryTimeWindowManager:
    def test_get_windows(self):
        from src.logistics.last_mile import DeliveryTimeWindowManager
        mgr = DeliveryTimeWindowManager()
        windows = mgr.get_windows()
        assert len(windows) == 4

    def test_morning_surcharge(self):
        from src.logistics.last_mile import DeliveryTimeWindowManager
        mgr = DeliveryTimeWindowManager()
        assert mgr.get_surcharge(10) == 0.0

    def test_afternoon_surcharge(self):
        from src.logistics.last_mile import DeliveryTimeWindowManager
        mgr = DeliveryTimeWindowManager()
        assert mgr.get_surcharge(15) == 0.0

    def test_evening_surcharge(self):
        from src.logistics.last_mile import DeliveryTimeWindowManager
        mgr = DeliveryTimeWindowManager()
        assert mgr.get_surcharge(20) == pytest.approx(0.2)

    def test_night_surcharge(self):
        from src.logistics.last_mile import DeliveryTimeWindowManager
        mgr = DeliveryTimeWindowManager()
        assert mgr.get_surcharge(23) == pytest.approx(0.5)

    def test_early_morning_surcharge(self):
        from src.logistics.last_mile import DeliveryTimeWindowManager
        mgr = DeliveryTimeWindowManager()
        assert mgr.get_surcharge(3) == pytest.approx(0.5)

    def test_window_to_dict(self):
        from src.logistics.last_mile import DeliveryTimeWindowManager
        mgr = DeliveryTimeWindowManager()
        windows = mgr.get_windows()
        d = windows[0].to_dict()
        assert "window_id" in d
        assert "name" in d


# ── TestLogisticsCostCalculator ────────────────────────────────────────────

class TestLogisticsCostCalculator:
    def test_calculate_shipping_cost_basic(self):
        from src.logistics.cost_optimizer import LogisticsCostCalculator
        calc = LogisticsCostCalculator()
        cost = calc.calculate_shipping_cost(1.0, 10.0)
        assert cost > 0

    def test_calculate_shipping_cost_with_carrier(self):
        from src.logistics.cost_optimizer import LogisticsCostCalculator
        calc = LogisticsCostCalculator()
        cj_cost = calc.calculate_shipping_cost(1.0, 10.0, "CJ")
        post_cost = calc.calculate_shipping_cost(1.0, 10.0, "POST")
        assert cj_cost != post_cost

    def test_calculate_shipping_cost_distance_surcharge(self):
        from src.logistics.cost_optimizer import LogisticsCostCalculator
        calc = LogisticsCostCalculator()
        short = calc.calculate_shipping_cost(1.0, 20.0)
        long_dist = calc.calculate_shipping_cost(1.0, 200.0)
        assert long_dist > short

    def test_calculate_packaging_cost(self):
        from src.logistics.cost_optimizer import LogisticsCostCalculator
        calc = LogisticsCostCalculator()
        cost = calc.calculate_packaging_cost(1.0)
        assert cost > 0

    def test_calculate_packaging_cost_heavy(self):
        from src.logistics.cost_optimizer import LogisticsCostCalculator
        calc = LogisticsCostCalculator()
        light = calc.calculate_packaging_cost(1.0)
        heavy = calc.calculate_packaging_cost(25.0)
        assert heavy > light

    def test_calculate_labor_cost(self):
        from src.logistics.cost_optimizer import LogisticsCostCalculator
        calc = LogisticsCostCalculator()
        cost = calc.calculate_labor_cost(10)
        assert cost > 0

    def test_calculate_labor_cost_more_deliveries(self):
        from src.logistics.cost_optimizer import LogisticsCostCalculator
        calc = LogisticsCostCalculator()
        one = calc.calculate_labor_cost(1)
        ten = calc.calculate_labor_cost(10)
        assert one > ten

    def test_calculate_fuel_cost(self):
        from src.logistics.cost_optimizer import LogisticsCostCalculator
        calc = LogisticsCostCalculator()
        cost = calc.calculate_fuel_cost(10.0)
        assert cost > 0

    def test_calculate_fuel_cost_truck_more(self):
        from src.logistics.cost_optimizer import LogisticsCostCalculator
        calc = LogisticsCostCalculator()
        moto = calc.calculate_fuel_cost(10.0, "motorcycle")
        truck = calc.calculate_fuel_cost(10.0, "truck")
        assert truck > moto

    def test_calculate_total_cost(self):
        from src.logistics.cost_optimizer import LogisticsCostCalculator
        calc = LogisticsCostCalculator()
        result = calc.calculate_total_cost(2.0, 30.0)
        assert "total_cost" in result
        assert "shipping_cost" in result
        assert "packaging_cost" in result
        assert "labor_cost" in result
        assert "fuel_cost" in result
        assert result["total_cost"] > 0


# ── TestCarrierSelector ────────────────────────────────────────────────────

class TestCarrierSelector:
    def test_get_carriers(self):
        from src.logistics.cost_optimizer import CarrierSelector
        sel = CarrierSelector()
        carriers = sel.get_carriers()
        assert len(carriers) >= 5

    def test_get_carrier_by_id(self):
        from src.logistics.cost_optimizer import CarrierSelector
        sel = CarrierSelector()
        carrier = sel.get_carrier("CJ")
        assert carrier is not None
        assert carrier.carrier_id == "CJ"

    def test_get_carrier_not_found(self):
        from src.logistics.cost_optimizer import CarrierSelector
        sel = CarrierSelector()
        assert sel.get_carrier("NONEXISTENT") is None

    def test_recommend_carrier_cost(self):
        from src.logistics.cost_optimizer import CarrierSelector
        sel = CarrierSelector()
        carrier = sel.recommend_carrier(1.0, "서울", "cost")
        assert carrier is not None

    def test_recommend_carrier_speed(self):
        from src.logistics.cost_optimizer import CarrierSelector
        sel = CarrierSelector()
        carrier = sel.recommend_carrier(1.0, "서울", "speed")
        assert carrier.avg_delivery_days <= 2

    def test_recommend_carrier_reliability(self):
        from src.logistics.cost_optimizer import CarrierSelector
        sel = CarrierSelector()
        carrier = sel.recommend_carrier(1.0, "서울", "reliability")
        assert carrier.reliability_score >= 0.9

    def test_carrier_to_dict(self):
        from src.logistics.cost_optimizer import CarrierSelector
        sel = CarrierSelector()
        carrier = sel.get_carrier("CJ")
        d = carrier.to_dict()
        assert "carrier_id" in d
        assert "name" in d


# ── TestConsolidationManager ───────────────────────────────────────────────

class TestConsolidationManager:
    def test_analyze_consolidation_empty(self):
        from src.logistics.cost_optimizer import ConsolidationManager
        mgr = ConsolidationManager()
        result = mgr.analyze_consolidation([])
        assert result == []

    def test_analyze_consolidation_single_order(self):
        from src.logistics.cost_optimizer import ConsolidationManager
        mgr = ConsolidationManager()
        orders = [{"order_id": "o1", "region": "서울", "weight_kg": 2.0}]
        result = mgr.analyze_consolidation(orders)
        assert result == []

    def test_analyze_consolidation_multiple_same_region(self):
        from src.logistics.cost_optimizer import ConsolidationManager
        mgr = ConsolidationManager()
        orders = [
            {"order_id": "o1", "region": "서울", "weight_kg": 2.0},
            {"order_id": "o2", "region": "서울", "weight_kg": 3.0},
        ]
        result = mgr.analyze_consolidation(orders)
        assert len(result) == 1
        assert result[0].region == "서울"

    def test_can_consolidate_same(self):
        from src.logistics.cost_optimizer import ConsolidationManager
        mgr = ConsolidationManager()
        o1 = {"region": "서울", "delivery_date": "2024-01-01"}
        o2 = {"region": "서울", "delivery_date": "2024-01-01"}
        assert mgr.can_consolidate(o1, o2) is True

    def test_can_consolidate_different_region(self):
        from src.logistics.cost_optimizer import ConsolidationManager
        mgr = ConsolidationManager()
        o1 = {"region": "서울", "delivery_date": "2024-01-01"}
        o2 = {"region": "부산", "delivery_date": "2024-01-01"}
        assert mgr.can_consolidate(o1, o2) is False

    def test_calculate_saving(self):
        from src.logistics.logistics_models import ConsolidationGroup
        from src.logistics.cost_optimizer import ConsolidationManager
        mgr = ConsolidationManager()
        group = ConsolidationGroup(group_id="g1", estimated_saving=500.0)
        assert mgr.calculate_saving(group) == 500.0


# ── TestCostOptimizer ─────────────────────────────────────────────────────

class TestCostOptimizer:
    def test_compare_shipping_methods(self):
        from src.logistics.cost_optimizer import CostOptimizer
        opt = CostOptimizer()
        results = opt.compare_shipping_methods(2.0, 50.0)
        assert len(results) >= 5
        assert results[0]["cost"] <= results[-1]["cost"]

    def test_find_consolidation_opportunities(self):
        from src.logistics.cost_optimizer import CostOptimizer
        opt = CostOptimizer()
        orders = [
            {"order_id": "o1", "region": "서울", "weight_kg": 2.0},
            {"order_id": "o2", "region": "서울", "weight_kg": 1.0},
        ]
        groups = opt.find_consolidation_opportunities(orders)
        assert len(groups) == 1

    def test_optimize_route_costs(self):
        from src.logistics.cost_optimizer import CostOptimizer
        opt = CostOptimizer()
        stops = [{"weight_kg": 2.0, "distance_km": 10.0}] * 3
        result = opt.optimize_route_costs(stops, [])
        assert "optimized_costs" in result
        assert "recommended_carrier" in result


# ── TestDeliveryPrediction ─────────────────────────────────────────────────

class TestDeliveryPrediction:
    def test_historical_regional_avg_same(self):
        from src.logistics.delivery_prediction import HistoricalDeliveryData
        data = HistoricalDeliveryData()
        avg = data.get_regional_avg("서울", "서울")
        assert avg < 10

    def test_historical_regional_avg_different(self):
        from src.logistics.delivery_prediction import HistoricalDeliveryData
        data = HistoricalDeliveryData()
        avg = data.get_regional_avg("서울", "부산")
        assert avg >= 24

    def test_historical_carrier_performance(self):
        from src.logistics.delivery_prediction import HistoricalDeliveryData
        data = HistoricalDeliveryData()
        perf = data.get_carrier_performance("CJ")
        assert "on_time_rate" in perf
        assert "avg_days" in perf

    def test_predict_delay_basic(self):
        from src.logistics.delivery_prediction import DeliveryDelayPredictor
        predictor = DeliveryDelayPredictor()
        result = predictor.predict_delay("CJ", "서울", "부산")
        assert 0 <= result["delay_probability"] <= 1
        assert "expected_extra_hours" in result
        assert "reasons" in result

    def test_predict_delay_returns_reasons_list(self):
        from src.logistics.delivery_prediction import DeliveryDelayPredictor
        predictor = DeliveryDelayPredictor()
        result = predictor.predict_delay("POST", "서울", "서울")
        assert isinstance(result["reasons"], list)

    def test_eta_calculator_returns_dict(self):
        from src.logistics.delivery_prediction import ETACalculator
        from src.logistics.logistics_models import Coordinate
        calc = ETACalculator()
        f = Coordinate(lat=37.5665, lon=126.9780)
        t = Coordinate(lat=37.4979, lon=127.0276)
        result = calc.calculate_eta(f, t, "CJ")
        assert "estimated_arrival" in result
        assert "confidence" in result

    def test_eta_confidence_between_0_and_1(self):
        from src.logistics.delivery_prediction import ETACalculator
        from src.logistics.logistics_models import Coordinate
        calc = ETACalculator()
        f = Coordinate(lat=37.5665, lon=126.9780)
        t = Coordinate(lat=37.4979, lon=127.0276)
        result = calc.calculate_eta(f, t, "CJ")
        assert 0 <= result["confidence"] <= 1

    def test_recalculate_eta(self):
        from src.logistics.delivery_prediction import ETACalculator
        from src.logistics.last_mile import LastMileTracker
        from src.logistics.logistics_models import Coordinate
        calc = ETACalculator()
        tracker = LastMileTracker()
        pc = Coordinate(lat=37.5665, lon=126.9780)
        dc = Coordinate(lat=37.4979, lon=127.0276)
        rec = tracker.create_delivery("o_eta", "픽업", "배송지", pc, dc)
        current = Coordinate(lat=37.53, lon=127.01)
        remaining = calc.recalculate_eta(rec, current)
        assert remaining >= 0

    def test_delivery_time_estimator(self):
        from src.logistics.delivery_prediction import DeliveryTimeEstimator
        estimator = DeliveryTimeEstimator()
        result = estimator.estimate("서울", "부산", "CJ")
        assert "estimated_days" in result
        assert "min_days" in result
        assert "max_days" in result
        assert "delay_risk" in result

    def test_delivery_time_estimator_min_max(self):
        from src.logistics.delivery_prediction import DeliveryTimeEstimator
        estimator = DeliveryTimeEstimator()
        result = estimator.estimate("서울", "서울", "CJ")
        assert result["min_days"] <= result["estimated_days"] <= result["max_days"]


# ── TestLogisticsAnalytics ─────────────────────────────────────────────────

class TestLogisticsAnalytics:
    def test_empty_success_rate(self):
        from src.logistics.logistics_analytics import LogisticsAnalytics
        analytics = LogisticsAnalytics()
        assert analytics.get_delivery_success_rate() == 0.0

    def test_add_and_success_rate(self):
        from src.logistics.logistics_analytics import LogisticsAnalytics
        analytics = LogisticsAnalytics()
        analytics.add_delivery_record({"status": "delivered"})
        analytics.add_delivery_record({"status": "failed"})
        rate = analytics.get_delivery_success_rate()
        assert rate == pytest.approx(0.5)

    def test_avg_delivery_time_empty(self):
        from src.logistics.logistics_analytics import LogisticsAnalytics
        analytics = LogisticsAnalytics()
        assert analytics.get_avg_delivery_time() == 0.0

    def test_avg_delivery_time_with_records(self):
        from src.logistics.logistics_analytics import LogisticsAnalytics
        analytics = LogisticsAnalytics()
        now = time.time()
        analytics.add_delivery_record({
            "status": "delivered", "created_at": now - 3600, "updated_at": now
        })
        avg = analytics.get_avg_delivery_time()
        assert avg == pytest.approx(1.0, abs=0.01)

    def test_carrier_performance_comparison(self):
        from src.logistics.logistics_analytics import LogisticsAnalytics
        analytics = LogisticsAnalytics()
        analytics.add_delivery_record({"carrier_id": "CJ", "status": "delivered",
                                        "created_at": time.time() - 3600, "updated_at": time.time()})
        result = analytics.get_carrier_performance_comparison()
        assert len(result) == 1
        assert result[0]["carrier_id"] == "CJ"

    def test_regional_stats(self):
        from src.logistics.logistics_analytics import LogisticsAnalytics
        analytics = LogisticsAnalytics()
        analytics.add_delivery_record({"region": "서울", "status": "delivered"})
        analytics.add_delivery_record({"region": "서울", "status": "failed"})
        stats = analytics.get_regional_stats()
        assert "서울" in stats
        assert stats["서울"]["count"] == 2

    def test_kpi_calculate(self):
        from src.logistics.logistics_analytics import LogisticsKPI
        kpi_calc = LogisticsKPI()
        deliveries = [
            {"status": "delivered", "on_time": True, "cost": 3000.0, "revenue": 5000.0},
            {"status": "failed", "on_time": False, "cost": 3000.0, "revenue": 0.0},
        ]
        kpi = kpi_calc.calculate_kpi(deliveries)
        assert kpi.total_deliveries == 2
        assert kpi.successful_deliveries == 1
        assert kpi.failed_deliveries == 1

    def test_kpi_empty(self):
        from src.logistics.logistics_analytics import LogisticsKPI
        kpi_calc = LogisticsKPI()
        kpi = kpi_calc.calculate_kpi([])
        assert kpi.total_deliveries == 0

    def test_kpi_on_time_rate(self):
        from src.logistics.logistics_analytics import LogisticsKPI
        kpi_calc = LogisticsKPI()
        deliveries = [{"on_time": True}, {"on_time": False}]
        rate = kpi_calc.get_on_time_rate(deliveries)
        assert rate == pytest.approx(0.5)

    def test_kpi_cost_per_delivery(self):
        from src.logistics.logistics_analytics import LogisticsKPI
        kpi_calc = LogisticsKPI()
        deliveries = [{"cost": 3000.0}, {"cost": 4000.0}]
        avg = kpi_calc.get_cost_per_delivery(deliveries)
        assert avg == pytest.approx(3500.0)

    def test_generate_daily_report(self):
        from src.logistics.logistics_analytics import LogisticsReport
        report = LogisticsReport()
        result = report.generate_daily_report()
        assert result["report_type"] == "daily"
        assert "date" in result

    def test_generate_weekly_report(self):
        from src.logistics.logistics_analytics import LogisticsReport
        report = LogisticsReport()
        result = report.generate_weekly_report()
        assert result["report_type"] == "weekly"

    def test_generate_monthly_report(self):
        from src.logistics.logistics_analytics import LogisticsReport
        report = LogisticsReport()
        result = report.generate_monthly_report()
        assert result["report_type"] == "monthly"

    def test_generate_carrier_report(self):
        from src.logistics.logistics_analytics import LogisticsReport
        report = LogisticsReport()
        result = report.generate_carrier_report("CJ")
        assert result["carrier_id"] == "CJ"

    def test_dashboard_realtime_status(self):
        from src.logistics.logistics_analytics import LogisticsDashboard
        dashboard = LogisticsDashboard()
        result = dashboard.get_realtime_status()
        assert "active_deliveries" in result
        assert "available_agents" in result

    def test_dashboard_cost_summary(self):
        from src.logistics.logistics_analytics import LogisticsDashboard
        dashboard = LogisticsDashboard()
        result = dashboard.get_cost_summary()
        assert "total_cost" in result
        assert "currency" in result

    def test_heatmap_regional(self):
        from src.logistics.logistics_analytics import DeliveryHeatmap
        hm = DeliveryHeatmap()
        deliveries = [{"region": "서울"}, {"region": "서울"}, {"region": "부산"}]
        result = hm.generate_regional_heatmap(deliveries)
        assert result.get("서울") == 2
        assert result.get("부산") == 1

    def test_heatmap_hourly(self):
        from src.logistics.logistics_analytics import DeliveryHeatmap
        hm = DeliveryHeatmap()
        deliveries = [{"created_at": time.time()}]
        result = hm.generate_hourly_distribution(deliveries)
        assert isinstance(result, dict)
        assert len(result) == 24


# ── TestLogisticsAutomation ────────────────────────────────────────────────

class TestLogisticsAutomation:
    def test_alert_service_send(self):
        from src.logistics.logistics_automation import LogisticsAlertService
        svc = LogisticsAlertService()
        alert = svc.send_alert("delay", "배송 지연", "warning")
        assert alert["alert_type"] == "delay"
        assert alert["severity"] == "warning"

    def test_alert_service_get_all(self):
        from src.logistics.logistics_automation import LogisticsAlertService
        svc = LogisticsAlertService()
        svc.send_alert("test", "테스트")
        alerts = svc.get_alerts()
        assert len(alerts) == 1

    def test_alert_service_get_by_type(self):
        from src.logistics.logistics_automation import LogisticsAlertService
        svc = LogisticsAlertService()
        svc.send_alert("delay", "지연")
        svc.send_alert("error", "오류")
        delays = svc.get_alerts("delay")
        assert len(delays) == 1
        assert delays[0]["alert_type"] == "delay"

    def test_check_delivery_delays_empty(self):
        from src.logistics.logistics_automation import LogisticsAlertService
        svc = LogisticsAlertService()
        result = svc.check_delivery_delays([])
        assert result == []

    def test_automation_auto_select_carrier(self):
        from src.logistics.logistics_automation import LogisticsAutomation
        automation = LogisticsAutomation()
        carrier = automation.auto_select_carrier(2.0, "서울")
        assert carrier is not None

    def test_automation_generate_waybill(self):
        from src.logistics.logistics_automation import LogisticsAutomation
        automation = LogisticsAutomation()
        waybill = automation.auto_generate_waybill("d1", "CJ")
        assert "waybill_number" in waybill
        assert "CJ" in waybill["waybill_number"]

    def test_automation_update_delivery_status(self):
        from src.logistics.logistics_automation import LogisticsAutomation
        automation = LogisticsAutomation()
        result = automation.auto_update_delivery_status("d1", "TRK123")
        assert "status" in result
        assert result["delivery_id"] == "d1"

    def test_automation_reassign_failed(self):
        from src.logistics.logistics_automation import LogisticsAutomation
        automation = LogisticsAutomation()
        result = automation.auto_reassign_failed_delivery("d1")
        assert result["action"] == "reassigned"
        assert "new_agent_id" in result

    def test_automation_process_batch(self):
        from src.logistics.logistics_automation import LogisticsAutomation
        automation = LogisticsAutomation()
        deliveries = [
            {"delivery_id": "d1", "weight_kg": 2.0, "region": "서울"},
            {"delivery_id": "d2", "weight_kg": 1.0, "region": "경기"},
        ]
        results = automation.process_batch_deliveries(deliveries)
        assert len(results) == 2
        assert all("waybill" in r for r in results)


# ── TestLogisticsAPI ───────────────────────────────────────────────────────

class TestLogisticsAPI:
    def setup_method(self):
        import src.order_webhook as wh
        wh.app.config["TESTING"] = True
        self.client = wh.app.test_client()
        self._ctx = wh.app.test_request_context()
        self._ctx.push()

    def test_dashboard_200(self):
        resp = self.client.get("/api/v1/logistics/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "active_deliveries" in data

    def test_list_deliveries_empty(self):
        resp = self.client.get("/api/v1/logistics/deliveries")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_create_delivery(self):
        payload = {
            "order_id": "test-order-1",
            "pickup_address": "서울 강남구",
            "delivery_address": "서울 마포구",
            "pickup_coordinate": {"lat": 37.5172, "lon": 127.0473},
            "delivery_coordinate": {"lat": 37.5547, "lon": 126.9236},
        }
        resp = self.client.post("/api/v1/logistics/deliveries",
                                json=payload, content_type="application/json")
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["order_id"] == "test-order-1"

    def test_get_delivery_not_found(self):
        resp = self.client.get("/api/v1/logistics/deliveries/nonexistent")
        assert resp.status_code == 404

    def test_get_delivery_found(self):
        payload = {
            "order_id": "test-order-2",
            "pickup_address": "픽업",
            "delivery_address": "배송지",
            "pickup_coordinate": {"lat": 37.5, "lon": 127.0},
            "delivery_coordinate": {"lat": 37.6, "lon": 127.1},
        }
        create_resp = self.client.post("/api/v1/logistics/deliveries",
                                       json=payload, content_type="application/json")
        delivery_id = create_resp.get_json()["delivery_id"]
        resp = self.client.get(f"/api/v1/logistics/deliveries/{delivery_id}")
        assert resp.status_code == 200

    def test_update_delivery_status(self):
        payload = {
            "order_id": "test-order-3",
            "pickup_address": "픽업",
            "delivery_address": "배송지",
            "pickup_coordinate": {"lat": 37.5, "lon": 127.0},
            "delivery_coordinate": {"lat": 37.6, "lon": 127.1},
        }
        create_resp = self.client.post("/api/v1/logistics/deliveries",
                                       json=payload, content_type="application/json")
        delivery_id = create_resp.get_json()["delivery_id"]
        resp = self.client.put(
            f"/api/v1/logistics/deliveries/{delivery_id}/status",
            json={"status": "picked_up"},
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_update_delivery_status_invalid(self):
        payload = {
            "order_id": "test-order-4",
            "pickup_address": "픽업",
            "delivery_address": "배송지",
            "pickup_coordinate": {"lat": 37.5, "lon": 127.0},
            "delivery_coordinate": {"lat": 37.6, "lon": 127.1},
        }
        create_resp = self.client.post("/api/v1/logistics/deliveries",
                                       json=payload, content_type="application/json")
        delivery_id = create_resp.get_json()["delivery_id"]
        resp = self.client.put(
            f"/api/v1/logistics/deliveries/{delivery_id}/status",
            json={"status": "delivered"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_get_eta(self):
        payload = {
            "order_id": "test-eta-1",
            "pickup_address": "픽업",
            "delivery_address": "배송지",
            "pickup_coordinate": {"lat": 37.5, "lon": 127.0},
            "delivery_coordinate": {"lat": 37.6, "lon": 127.1},
        }
        create_resp = self.client.post("/api/v1/logistics/deliveries",
                                       json=payload, content_type="application/json")
        delivery_id = create_resp.get_json()["delivery_id"]
        resp = self.client.get(f"/api/v1/logistics/deliveries/{delivery_id}/eta")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "eta_minutes" in data

    def test_get_eta_not_found(self):
        resp = self.client.get("/api/v1/logistics/deliveries/nonexistent/eta")
        assert resp.status_code == 404

    def test_submit_proof(self):
        payload_create = {
            "order_id": "test-pod-1",
            "pickup_address": "픽업",
            "delivery_address": "배송지",
            "pickup_coordinate": {"lat": 37.5, "lon": 127.0},
            "delivery_coordinate": {"lat": 37.6, "lon": 127.1},
        }
        create_resp = self.client.post("/api/v1/logistics/deliveries",
                                       json=payload_create, content_type="application/json")
        delivery_id = create_resp.get_json()["delivery_id"]
        proof_payload = {"recipient_name": "홍길동", "notes": "현관 앞 배송"}
        resp = self.client.post(
            f"/api/v1/logistics/deliveries/{delivery_id}/proof",
            json=proof_payload, content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["recipient_name"] == "홍길동"

    def test_list_agents_empty(self):
        resp = self.client.get("/api/v1/logistics/agents")
        assert resp.status_code == 200

    def test_register_agent(self):
        payload = {
            "name": "배달기사",
            "phone": "010-9999-9999",
            "location": {"lat": 37.5, "lon": 127.0},
            "capacity_kg": 30.0,
        }
        resp = self.client.post("/api/v1/logistics/agents",
                                json=payload, content_type="application/json")
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "배달기사"

    def test_assign_delivery_with_agent(self):
        # Register an agent first, then assign
        agent_payload = {
            "name": "배달기사_assign",
            "phone": "010-8888-8888",
            "location": {"lat": 37.5, "lon": 127.0},
        }
        self.client.post("/api/v1/logistics/agents",
                         json=agent_payload, content_type="application/json")
        payload = {
            "order_id": "test-assign-1",
            "pickup_address": "픽업",
            "delivery_address": "배송지",
            "pickup_coordinate": {"lat": 37.5, "lon": 127.0},
            "delivery_coordinate": {"lat": 37.6, "lon": 127.1},
        }
        create_resp = self.client.post("/api/v1/logistics/deliveries",
                                       json=payload, content_type="application/json")
        delivery_id = create_resp.get_json()["delivery_id"]
        resp = self.client.post(f"/api/v1/logistics/deliveries/{delivery_id}/assign")
        # Either 200 (agent available) or 409 (no available agent)
        assert resp.status_code in (200, 409)

    def test_optimize_route(self):
        payload = {
            "depot": {"lat": 37.5665, "lon": 126.9780},
            "strategy": "nearest_neighbor",
            "stops": [
                {"stop_id": "s1", "address": "강남구", "order_id": "o1",
                 "coordinate": {"lat": 37.5172, "lon": 127.0473}, "weight_kg": 2.0},
                {"stop_id": "s2", "address": "마포구", "order_id": "o2",
                 "coordinate": {"lat": 37.5547, "lon": 126.9236}, "weight_kg": 1.5},
            ],
        }
        resp = self.client.post("/api/v1/logistics/routes/optimize",
                                json=payload, content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "route_id" in data

    def test_get_route_not_found(self):
        resp = self.client.get("/api/v1/logistics/routes/nonexistent")
        assert resp.status_code == 404

    def test_analyze_consolidation(self):
        payload = {
            "orders": [
                {"order_id": "o1", "region": "서울", "weight_kg": 2.0,
                 "delivery_date": "2024-01-01"},
                {"order_id": "o2", "region": "서울", "weight_kg": 1.5,
                 "delivery_date": "2024-01-01"},
            ]
        }
        resp = self.client.post("/api/v1/logistics/consolidation/analyze",
                                json=payload, content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)

    def test_recommend_carrier(self):
        resp = self.client.get("/api/v1/logistics/carriers/recommend?weight=2.0&region=서울&priority=cost")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "carrier_id" in data

    def test_analytics(self):
        resp = self.client.get("/api/v1/logistics/analytics")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "success_rate" in data

    def test_heatmap(self):
        resp = self.client.get("/api/v1/logistics/heatmap")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "regional" in data
        assert "hourly" in data

    def test_list_deliveries_status_filter(self):
        resp = self.client.get("/api/v1/logistics/deliveries?status=assigned")
        assert resp.status_code == 200

    def test_list_deliveries_invalid_status(self):
        resp = self.client.get("/api/v1/logistics/deliveries?status=invalid_status")
        assert resp.status_code == 400


# ── TestBotCommands ────────────────────────────────────────────────────────

class TestBotCommands:
    def test_cmd_logistics_status(self):
        from src.bot.commands import cmd_logistics_status
        result = cmd_logistics_status()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_route_optimize_no_args(self):
        from src.bot.commands import cmd_route_optimize
        result = cmd_route_optimize("")
        assert "사용법" in result or "error" in result.lower() or "실패" in result

    def test_cmd_route_optimize_with_ids(self):
        from src.bot.commands import cmd_route_optimize
        result = cmd_route_optimize("d1,d2,d3")
        assert isinstance(result, str)

    def test_cmd_delivery_eta_no_args(self):
        from src.bot.commands import cmd_delivery_eta
        result = cmd_delivery_eta("")
        assert "사용법" in result or "error" in result.lower() or "실패" in result

    def test_cmd_delivery_eta_with_id(self):
        from src.bot.commands import cmd_delivery_eta
        result = cmd_delivery_eta("nonexistent-id")
        assert isinstance(result, str)

    def test_cmd_carrier_recommend_no_args(self):
        from src.bot.commands import cmd_carrier_recommend
        result = cmd_carrier_recommend("")
        assert "사용법" in result or "error" in result.lower() or "실패" in result

    def test_cmd_carrier_recommend_with_args(self):
        from src.bot.commands import cmd_carrier_recommend
        result = cmd_carrier_recommend("2.0 서울")
        assert isinstance(result, str)
        assert "CJ" in result or "택배사" in result or "추천" in result

    def test_cmd_logistics_report(self):
        from src.bot.commands import cmd_logistics_report
        result = cmd_logistics_report()
        assert isinstance(result, str)
        assert len(result) > 0
