"""src/logistics/route_optimizer.py — 배송 경로 최적화 (Phase 99)."""
from __future__ import annotations

import math
import uuid
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .logistics_models import Coordinate, DeliveryStop, RouteResult


class DistanceCalculator:
    """거리 계산 유틸리티."""

    @staticmethod
    def haversine(coord1: Coordinate, coord2: Coordinate) -> float:
        """Haversine 공식으로 두 좌표 사이의 거리(km) 반환."""
        R = 6371.0
        lat1 = math.radians(coord1.lat)
        lat2 = math.radians(coord2.lat)
        dlat = math.radians(coord2.lat - coord1.lat)
        dlon = math.radians(coord2.lon - coord1.lon)
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    @staticmethod
    def distance_matrix(stops: list) -> list:
        """모든 정류장 쌍의 거리 행렬 반환."""
        n = len(stops)
        matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    matrix[i][j] = DistanceCalculator.haversine(
                        stops[i].coordinate, stops[j].coordinate
                    )
        return matrix


@dataclass
class RouteConstraint:
    max_stops: int = 20
    max_distance_km: float = 200.0
    max_duration_min: float = 480.0
    vehicle_capacity_kg: float = 50.0
    vehicle_capacity_m3: float = 0.5


class RouteStrategy(ABC):
    """경로 최적화 전략 추상 기반 클래스."""

    @abstractmethod
    def optimize(
        self,
        stops: list,
        depot: Coordinate,
        constraints: RouteConstraint,
    ) -> list:
        """정류장 목록을 최적화된 순서로 반환."""


class NearestNeighborStrategy(RouteStrategy):
    """최근접 이웃 탐욕 알고리즘."""

    def optimize(
        self,
        stops: list,
        depot: Coordinate,
        constraints: RouteConstraint,
    ) -> list:
        if not stops:
            return []
        unvisited = list(stops)
        route = []
        current = depot
        total_weight = 0.0
        total_volume = 0.0

        while unvisited:
            nearest = min(
                unvisited,
                key=lambda s: DistanceCalculator.haversine(current, s.coordinate),
            )
            if (
                total_weight + nearest.weight_kg > constraints.vehicle_capacity_kg
                or total_volume + nearest.volume_m3 > constraints.vehicle_capacity_m3
            ):
                break
            route.append(nearest)
            total_weight += nearest.weight_kg
            total_volume += nearest.volume_m3
            current = nearest.coordinate
            unvisited.remove(nearest)

        return route


class TwoOptStrategy(RouteStrategy):
    """2-opt 지역 탐색 개선 알고리즘."""

    def optimize(
        self,
        stops: list,
        depot: Coordinate,
        constraints: RouteConstraint,
    ) -> list:
        if len(stops) <= 2:
            return list(stops)

        # 초기 경로: 최근접 이웃으로 생성
        route = NearestNeighborStrategy().optimize(stops, depot, constraints)
        if len(route) <= 2:
            return route

        improved = True
        while improved:
            improved = False
            for i in range(len(route) - 1):
                for j in range(i + 2, len(route)):
                    new_route = route[:i] + route[i:j + 1][::-1] + route[j + 1:]
                    if self._route_distance(new_route, depot) < self._route_distance(route, depot):
                        route = new_route
                        improved = True
        return route

    @staticmethod
    def _route_distance(route: list, depot: Coordinate) -> float:
        if not route:
            return 0.0
        dist = DistanceCalculator.haversine(depot, route[0].coordinate)
        for i in range(len(route) - 1):
            dist += DistanceCalculator.haversine(route[i].coordinate, route[i + 1].coordinate)
        dist += DistanceCalculator.haversine(route[-1].coordinate, depot)
        return dist


class ClusterFirstRouteSecond(RouteStrategy):
    """지역별 클러스터링 후 최근접 이웃 적용."""

    def optimize(
        self,
        stops: list,
        depot: Coordinate,
        constraints: RouteConstraint,
    ) -> list:
        if not stops:
            return []

        # 위도/경도 기준으로 2×2 격자 클러스터링
        lat_mid = sum(s.coordinate.lat for s in stops) / len(stops)
        lon_mid = sum(s.coordinate.lon for s in stops) / len(stops)

        clusters: dict = {
            "NW": [], "NE": [], "SW": [], "SE": []
        }
        for s in stops:
            lat_key = "N" if s.coordinate.lat >= lat_mid else "S"
            lon_key = "E" if s.coordinate.lon >= lon_mid else "W"
            clusters[lat_key + lon_key].append(s)

        route = []
        current = depot
        # 가장 가까운 클러스터부터 방문
        cluster_order = sorted(
            clusters.keys(),
            key=lambda k: DistanceCalculator.haversine(
                current, clusters[k][0].coordinate
            ) if clusters[k] else float("inf"),
        )
        for key in cluster_order:
            cluster_stops = clusters[key]
            if not cluster_stops:
                continue
            sub = NearestNeighborStrategy().optimize(cluster_stops, current, constraints)
            route.extend(sub)
            if sub:
                current = sub[-1].coordinate

        return route


class RouteOptimizer:
    """경로 최적화 관리자."""

    _STRATEGIES = {
        "nearest_neighbor": NearestNeighborStrategy,
        "two_opt": TwoOptStrategy,
        "cluster_first": ClusterFirstRouteSecond,
    }

    def __init__(self) -> None:
        self._routes: dict = {}

    def optimize(
        self,
        stops: list,
        depot_coordinate: Coordinate,
        strategy: str = "nearest_neighbor",
        constraints: RouteConstraint | None = None,
    ) -> RouteResult:
        if constraints is None:
            constraints = RouteConstraint()

        strategy_cls = self._STRATEGIES.get(strategy, NearestNeighborStrategy)
        optimizer = strategy_cls()
        optimized_stops = optimizer.optimize(stops, depot_coordinate, constraints)

        total_distance = 0.0
        if optimized_stops:
            total_distance += DistanceCalculator.haversine(depot_coordinate, optimized_stops[0].coordinate)
            for i in range(len(optimized_stops) - 1):
                total_distance += DistanceCalculator.haversine(
                    optimized_stops[i].coordinate, optimized_stops[i + 1].coordinate
                )
            total_distance += DistanceCalculator.haversine(optimized_stops[-1].coordinate, depot_coordinate)

        avg_speed_kmh = 30.0
        estimated_duration = (total_distance / avg_speed_kmh) * 60 + len(optimized_stops) * 5

        route = RouteResult(
            route_id=str(uuid.uuid4()),
            stops=optimized_stops,
            total_distance_km=round(total_distance, 3),
            estimated_duration_min=round(estimated_duration, 1),
            strategy_used=strategy,
            created_at=time.time(),
        )
        self._routes[route.route_id] = route
        return route

    def get_route(self, route_id: str) -> RouteResult | None:
        return self._routes.get(route_id)

    def list_routes(self) -> list:
        return list(self._routes.values())
