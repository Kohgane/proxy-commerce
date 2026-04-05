"""src/api/logistics_api.py — 물류 최적화 API Blueprint (Phase 99).

Blueprint: /api/v1/logistics

엔드포인트:
  POST /routes/optimize                    — 경로 최적화 요청
  GET  /routes/<route_id>                  — 경로 조회
  GET  /deliveries                         — 배송 목록
  POST /deliveries                         — 배송 생성
  GET  /deliveries/<delivery_id>           — 배송 상세
  PUT  /deliveries/<delivery_id>/status    — 배송 상태 업데이트
  POST /deliveries/<delivery_id>/assign    — 배달 기사 배정
  GET  /deliveries/<delivery_id>/eta       — ETA 조회
  POST /deliveries/<delivery_id>/proof     — 배송 완료 증빙 등록
  GET  /agents                             — 배달 기사 목록
  POST /agents                             — 배달 기사 등록
  POST /consolidation/analyze              — 통합 배송 분석
  GET  /carriers/recommend                 — 택배사 추천
  GET  /analytics                          — 물류 분석
  GET  /dashboard                          — 물류 대시보드
  GET  /heatmap                            — 배송 히트맵
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

logistics_bp = Blueprint("logistics", __name__, url_prefix="/api/v1/logistics")

# ── 지연 초기화 싱글턴 ────────────────────────────────────────────────────

_route_optimizer = None
_tracker = None
_assignment = None
_pod_service = None
_tw_manager = None
_cost_calc = None
_carrier_selector = None
_consolidation_mgr = None
_cost_optimizer = None
_eta_calc = None
_time_estimator = None
_analytics = None
_kpi = None
_report = None
_dashboard = None
_heatmap = None
_automation = None


def _get_services():
    global _route_optimizer, _tracker, _assignment, _pod_service, _tw_manager
    global _cost_calc, _carrier_selector, _consolidation_mgr, _cost_optimizer
    global _eta_calc, _time_estimator, _analytics, _kpi, _report, _dashboard
    global _heatmap, _automation

    if _route_optimizer is None:
        from ..logistics.route_optimizer import RouteOptimizer
        from ..logistics.last_mile import (
            LastMileTracker, DeliveryAssignment,
            ProofOfDeliveryService, DeliveryTimeWindowManager,
        )
        from ..logistics.cost_optimizer import (
            LogisticsCostCalculator, CarrierSelector,
            ConsolidationManager, CostOptimizer,
        )
        from ..logistics.delivery_prediction import ETACalculator, DeliveryTimeEstimator
        from ..logistics.logistics_analytics import (
            LogisticsAnalytics, LogisticsKPI, LogisticsReport,
            LogisticsDashboard, DeliveryHeatmap,
        )
        from ..logistics.logistics_automation import LogisticsAutomation

        _route_optimizer = RouteOptimizer()
        _tracker = LastMileTracker()
        _assignment = DeliveryAssignment()
        _pod_service = ProofOfDeliveryService()
        _tw_manager = DeliveryTimeWindowManager()
        _cost_calc = LogisticsCostCalculator()
        _carrier_selector = CarrierSelector()
        _consolidation_mgr = ConsolidationManager()
        _cost_optimizer = CostOptimizer()
        _eta_calc = ETACalculator()
        _time_estimator = DeliveryTimeEstimator()
        _analytics = LogisticsAnalytics()
        _kpi = LogisticsKPI()
        _report = LogisticsReport()
        _dashboard = LogisticsDashboard()
        _heatmap = DeliveryHeatmap()
        _automation = LogisticsAutomation()


# ── 경로 최적화 ───────────────────────────────────────────────────────────

@logistics_bp.post("/routes/optimize")
def optimize_route():
    try:
        _get_services()
        data = request.get_json(force=True) or {}
        from ..logistics.logistics_models import Coordinate, DeliveryStop
        from ..logistics.route_optimizer import RouteConstraint

        depot_data = data.get("depot", {"lat": 37.5665, "lon": 126.9780})
        depot = Coordinate(lat=depot_data["lat"], lon=depot_data["lon"])
        strategy = data.get("strategy", "nearest_neighbor")

        stops_data = data.get("stops", [])
        stops = []
        for s in stops_data:
            coord_data = s.get("coordinate", {"lat": 37.5, "lon": 127.0})
            stop = DeliveryStop(
                stop_id=s.get("stop_id", ""),
                address=s.get("address", ""),
                coordinate=Coordinate(lat=coord_data["lat"], lon=coord_data["lon"]),
                order_id=s.get("order_id", ""),
                weight_kg=s.get("weight_kg", 1.0),
                volume_m3=s.get("volume_m3", 0.01),
            )
            stops.append(stop)

        constraints_data = data.get("constraints", {})
        constraints = RouteConstraint(
            max_stops=constraints_data.get("max_stops", 20),
            max_distance_km=constraints_data.get("max_distance_km", 200.0),
            vehicle_capacity_kg=constraints_data.get("vehicle_capacity_kg", 50.0),
        )

        result = _route_optimizer.optimize(stops, depot, strategy, constraints)
        return jsonify(result.to_dict()), 200
    except Exception as exc:
        logger.error("optimize_route 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@logistics_bp.get("/routes/<route_id>")
def get_route(route_id: str):
    try:
        _get_services()
        route = _route_optimizer.get_route(route_id)
        if route is None:
            return jsonify({"error": "경로를 찾을 수 없습니다"}), 404
        return jsonify(route.to_dict()), 200
    except Exception as exc:
        logger.error("get_route 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── 배송 관리 ─────────────────────────────────────────────────────────────

@logistics_bp.get("/deliveries")
def list_deliveries():
    try:
        _get_services()
        from ..logistics.logistics_models import DeliveryStatus
        status_str = request.args.get("status")
        status = None
        if status_str:
            try:
                status = DeliveryStatus(status_str)
            except ValueError:
                return jsonify({"error": f"유효하지 않은 상태: {status_str}"}), 400
        deliveries = _tracker.list_deliveries(status)
        return jsonify([d.to_dict() for d in deliveries]), 200
    except Exception as exc:
        logger.error("list_deliveries 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@logistics_bp.post("/deliveries")
def create_delivery():
    try:
        _get_services()
        data = request.get_json(force=True) or {}
        from ..logistics.logistics_models import Coordinate

        pickup_coord_data = data.get("pickup_coordinate", {"lat": 37.5665, "lon": 126.9780})
        delivery_coord_data = data.get("delivery_coordinate", {"lat": 37.4979, "lon": 127.0276})

        record = _tracker.create_delivery(
            order_id=data.get("order_id", ""),
            pickup_address=data.get("pickup_address", ""),
            delivery_address=data.get("delivery_address", ""),
            pickup_coord=Coordinate(lat=pickup_coord_data["lat"], lon=pickup_coord_data["lon"]),
            delivery_coord=Coordinate(lat=delivery_coord_data["lat"], lon=delivery_coord_data["lon"]),
        )
        return jsonify(record.to_dict()), 201
    except Exception as exc:
        logger.error("create_delivery 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@logistics_bp.get("/deliveries/<delivery_id>")
def get_delivery(delivery_id: str):
    try:
        _get_services()
        record = _tracker.get_delivery(delivery_id)
        if record is None:
            return jsonify({"error": "배송을 찾을 수 없습니다"}), 404
        return jsonify(record.to_dict()), 200
    except Exception as exc:
        logger.error("get_delivery 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@logistics_bp.put("/deliveries/<delivery_id>/status")
def update_delivery_status(delivery_id: str):
    try:
        _get_services()
        data = request.get_json(force=True) or {}
        from ..logistics.logistics_models import DeliveryStatus
        new_status = DeliveryStatus(data.get("status", ""))
        record = _tracker.update_status(delivery_id, new_status)
        return jsonify(record.to_dict()), 200
    except (KeyError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.error("update_delivery_status 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@logistics_bp.post("/deliveries/<delivery_id>/assign")
def assign_delivery(delivery_id: str):
    try:
        _get_services()
        record = _tracker.get_delivery(delivery_id)
        if record is None:
            return jsonify({"error": "배송을 찾을 수 없습니다"}), 404
        agent = _assignment.assign_best_agent(record)
        if agent is None:
            return jsonify({"error": "사용 가능한 배달 기사가 없습니다"}), 409
        return jsonify({"delivery_id": delivery_id, "agent": agent.to_dict()}), 200
    except Exception as exc:
        logger.error("assign_delivery 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@logistics_bp.get("/deliveries/<delivery_id>/eta")
def get_eta(delivery_id: str):
    try:
        _get_services()
        eta = _tracker.calculate_eta(delivery_id)
        return jsonify({"delivery_id": delivery_id, "eta_minutes": eta}), 200
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        logger.error("get_eta 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@logistics_bp.post("/deliveries/<delivery_id>/proof")
def submit_proof(delivery_id: str):
    try:
        _get_services()
        data = request.get_json(force=True) or {}
        from ..logistics.logistics_models import Coordinate

        gps_data = data.get("gps_coordinate")
        gps = Coordinate(lat=gps_data["lat"], lon=gps_data["lon"]) if gps_data else None

        proof = _pod_service.record_proof(
            delivery_id=delivery_id,
            recipient_name=data.get("recipient_name", ""),
            gps_coord=gps,
            notes=data.get("notes", ""),
        )
        return jsonify(proof.to_dict()), 201
    except Exception as exc:
        logger.error("submit_proof 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── 배달 기사 ─────────────────────────────────────────────────────────────

@logistics_bp.get("/agents")
def list_agents():
    try:
        _get_services()
        status = request.args.get("status")
        agents = _assignment.list_agents(status)
        return jsonify([a.to_dict() for a in agents]), 200
    except Exception as exc:
        logger.error("list_agents 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@logistics_bp.post("/agents")
def register_agent():
    try:
        _get_services()
        data = request.get_json(force=True) or {}
        from ..logistics.logistics_models import Coordinate

        loc_data = data.get("location", {"lat": 37.5665, "lon": 126.9780})
        agent = _assignment.register_agent(
            name=data.get("name", ""),
            phone=data.get("phone", ""),
            location_coord=Coordinate(lat=loc_data["lat"], lon=loc_data["lon"]),
            capacity_kg=data.get("capacity_kg", 50.0),
        )
        return jsonify(agent.to_dict()), 201
    except Exception as exc:
        logger.error("register_agent 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── 통합 배송 & 택배사 ────────────────────────────────────────────────────

@logistics_bp.post("/consolidation/analyze")
def analyze_consolidation():
    try:
        _get_services()
        data = request.get_json(force=True) or {}
        orders = data.get("orders", [])
        groups = _consolidation_mgr.analyze_consolidation(orders)
        return jsonify([g.to_dict() for g in groups]), 200
    except Exception as exc:
        logger.error("analyze_consolidation 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@logistics_bp.get("/carriers/recommend")
def recommend_carrier():
    try:
        _get_services()
        weight = float(request.args.get("weight", 1.0))
        region = request.args.get("region", "서울")
        priority = request.args.get("priority", "cost")
        carrier = _carrier_selector.recommend_carrier(weight, region, priority)
        return jsonify(carrier.to_dict()), 200
    except Exception as exc:
        logger.error("recommend_carrier 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ── 분석 & 대시보드 ───────────────────────────────────────────────────────

@logistics_bp.get("/analytics")
def get_analytics():
    try:
        _get_services()
        return jsonify({
            "success_rate": _analytics.get_delivery_success_rate(),
            "avg_delivery_time_hours": _analytics.get_avg_delivery_time(),
            "carrier_comparison": _analytics.get_carrier_performance_comparison(),
            "regional_stats": _analytics.get_regional_stats(),
        }), 200
    except Exception as exc:
        logger.error("get_analytics 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@logistics_bp.get("/dashboard")
def get_dashboard():
    try:
        _get_services()
        return jsonify(_dashboard.get_realtime_status()), 200
    except Exception as exc:
        logger.error("get_dashboard 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500


@logistics_bp.get("/heatmap")
def get_heatmap():
    try:
        _get_services()
        deliveries = [d.to_dict() for d in _tracker.list_deliveries()]
        return jsonify({
            "regional": _heatmap.generate_regional_heatmap(deliveries),
            "hourly": _heatmap.generate_hourly_distribution(deliveries),
        }), 200
    except Exception as exc:
        logger.error("get_heatmap 오류: %s", exc)
        return jsonify({"error": str(exc)}), 500
