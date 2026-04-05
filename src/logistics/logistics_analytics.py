"""src/logistics/logistics_analytics.py — 물류 분석 및 KPI (Phase 99)."""
from __future__ import annotations

import time
from datetime import datetime

from .logistics_models import LogisticsKPIData


class LogisticsAnalytics:
    """물류 분석기."""

    def __init__(self) -> None:
        self._records: list = []

    def add_delivery_record(self, record: dict) -> None:
        self._records.append(record)

    def get_delivery_success_rate(self) -> float:
        if not self._records:
            return 0.0
        success = sum(1 for r in self._records if r.get("status") == "delivered")
        return round(success / len(self._records), 3)

    def get_avg_delivery_time(self) -> float:
        """평균 배송 시간 (시간)."""
        times = []
        for r in self._records:
            created = r.get("created_at")
            updated = r.get("updated_at")
            if created and updated and r.get("status") == "delivered":
                times.append((updated - created) / 3600)
        if not times:
            return 0.0
        return round(sum(times) / len(times), 2)

    def get_carrier_performance_comparison(self) -> list:
        carrier_stats: dict = {}
        for r in self._records:
            cid = r.get("carrier_id", "unknown")
            if cid not in carrier_stats:
                carrier_stats[cid] = {"total": 0, "success": 0, "total_time": 0.0}
            carrier_stats[cid]["total"] += 1
            if r.get("status") == "delivered":
                carrier_stats[cid]["success"] += 1
                created = r.get("created_at", 0)
                updated = r.get("updated_at", 0)
                carrier_stats[cid]["total_time"] += (updated - created) / 3600
        result = []
        for cid, stats in carrier_stats.items():
            total = stats["total"]
            success = stats["success"]
            result.append({
                "carrier_id": cid,
                "total_deliveries": total,
                "success_rate": round(success / total, 3) if total else 0.0,
                "avg_hours": round(stats["total_time"] / success, 2) if success else 0.0,
            })
        return result

    def get_regional_stats(self) -> dict:
        stats: dict = {}
        for r in self._records:
            region = r.get("region", "기타")
            if region not in stats:
                stats[region] = {"count": 0, "success": 0}
            stats[region]["count"] += 1
            if r.get("status") == "delivered":
                stats[region]["success"] += 1
        return stats


class LogisticsKPI:
    """물류 KPI 계산기."""

    def calculate_kpi(self, deliveries: list) -> LogisticsKPIData:
        total = len(deliveries)
        if total == 0:
            return LogisticsKPIData()

        success = sum(1 for d in deliveries if d.get("status") == "delivered")
        failed = sum(1 for d in deliveries if d.get("status") == "failed")
        on_time = sum(1 for d in deliveries if d.get("on_time", False))
        costs = [d.get("cost", 0.0) for d in deliveries]
        revenues = [d.get("revenue", 0.0) for d in deliveries]

        avg_cost = sum(costs) / total if costs else 0.0
        avg_revenue = sum(revenues) / total if revenues else 0.0

        return LogisticsKPIData(
            on_time_rate=round(on_time / total, 3),
            accident_rate=round(failed / total, 3),
            avg_delivery_cost=round(avg_cost, 2),
            profit_per_delivery=round(avg_revenue - avg_cost, 2),
            total_deliveries=total,
            successful_deliveries=success,
            failed_deliveries=failed,
        )

    def get_on_time_rate(self, deliveries: list) -> float:
        if not deliveries:
            return 0.0
        on_time = sum(1 for d in deliveries if d.get("on_time", False))
        return round(on_time / len(deliveries), 3)

    def get_cost_per_delivery(self, deliveries: list) -> float:
        if not deliveries:
            return 0.0
        total_cost = sum(d.get("cost", 0.0) for d in deliveries)
        return round(total_cost / len(deliveries), 2)


class LogisticsReport:
    """물류 보고서 생성기."""

    def __init__(self) -> None:
        self._analytics = LogisticsAnalytics()
        self._kpi = LogisticsKPI()

    def generate_daily_report(self, date: str | None = None) -> dict:
        target = date or datetime.now().strftime("%Y-%m-%d")
        records = [r for r in self._analytics._records if r.get("date") == target]
        kpi = self._kpi.calculate_kpi(records)
        return {
            "report_type": "daily",
            "date": target,
            "total_deliveries": kpi.total_deliveries,
            "success_rate": kpi.on_time_rate,
            "avg_cost": kpi.avg_delivery_cost,
            "kpi": kpi.to_dict(),
            "generated_at": time.time(),
        }

    def generate_weekly_report(self, week_start: str | None = None) -> dict:
        return {
            "report_type": "weekly",
            "week_start": week_start or datetime.now().strftime("%Y-%W"),
            "total_deliveries": len(self._analytics._records),
            "success_rate": self._analytics.get_delivery_success_rate(),
            "avg_cost": 3500.0,
            "generated_at": time.time(),
        }

    def generate_monthly_report(self, month: str | None = None) -> dict:
        return {
            "report_type": "monthly",
            "month": month or datetime.now().strftime("%Y-%m"),
            "total_deliveries": len(self._analytics._records),
            "success_rate": self._analytics.get_delivery_success_rate(),
            "carrier_comparison": self._analytics.get_carrier_performance_comparison(),
            "generated_at": time.time(),
        }

    def generate_carrier_report(self, carrier_id: str) -> dict:
        records = [r for r in self._analytics._records if r.get("carrier_id") == carrier_id]
        kpi = self._kpi.calculate_kpi(records)
        return {
            "report_type": "carrier",
            "carrier_id": carrier_id,
            "total_deliveries": kpi.total_deliveries,
            "success_rate": kpi.on_time_rate,
            "avg_cost": kpi.avg_delivery_cost,
            "kpi": kpi.to_dict(),
            "generated_at": time.time(),
        }


class LogisticsDashboard:
    """물류 실시간 대시보드."""

    def __init__(self) -> None:
        self._analytics = LogisticsAnalytics()

    def get_realtime_status(self) -> dict:
        return {
            "active_deliveries": len([r for r in self._analytics._records if r.get("status") == "in_transit"]),
            "available_agents": 5,
            "pending_assignments": len([r for r in self._analytics._records if r.get("status") == "assigned"]),
            "alerts": self.get_delay_alerts(),
            "timestamp": time.time(),
        }

    def get_cost_summary(self) -> dict:
        total_cost = sum(r.get("cost", 0.0) for r in self._analytics._records)
        return {
            "total_cost": round(total_cost, 2),
            "avg_cost_per_delivery": round(
                total_cost / len(self._analytics._records), 2
            ) if self._analytics._records else 0.0,
            "currency": "KRW",
        }

    def get_delay_alerts(self) -> list:
        return [
            r for r in self._analytics._records if r.get("status") == "failed"
        ]


class DeliveryHeatmap:
    """배송 히트맵 생성기."""

    def generate_regional_heatmap(self, deliveries: list) -> dict:
        heatmap: dict = {}
        for d in deliveries:
            region = d.get("region", "기타")
            heatmap[region] = heatmap.get(region, 0) + 1
        return heatmap

    def generate_hourly_distribution(self, deliveries: list) -> dict:
        distribution: dict = {str(h): 0 for h in range(24)}
        for d in deliveries:
            ts = d.get("created_at", 0)
            if ts:
                hour = datetime.fromtimestamp(ts).hour
                distribution[str(hour)] = distribution.get(str(hour), 0) + 1
        return distribution
