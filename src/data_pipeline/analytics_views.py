"""src/data_pipeline/analytics_views.py — 분석 뷰 & 마트 (Phase 100)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from .data_warehouse import DataWarehouse


class QueryEngine:
    """인메모리 쿼리 엔진."""

    def __init__(self, warehouse: DataWarehouse) -> None:
        self._warehouse = warehouse

    def execute(self, query: dict) -> list[dict]:
        table = query.get("table", "")
        select_fields = query.get("select", [])
        where = query.get("where", {})
        group_by = query.get("group_by", [])
        order_by = query.get("order_by", "")
        order_dir = query.get("order_dir", "asc")
        limit = query.get("limit", 0)

        data = self._warehouse.query(table, where if where else None)

        # 필드 선택
        if select_fields and select_fields != ["*"]:
            data = [{k: row.get(k) for k in select_fields} for row in data]

        # 그룹화
        if group_by:
            groups: dict = {}
            for row in data:
                key = tuple(row.get(g) for g in group_by)
                if key not in groups:
                    groups[key] = []
                groups[key].append(row)
            # 각 그룹의 첫 번째 레코드와 count 반환
            grouped = []
            for key, rows in groups.items():
                rep = dict(rows[0])
                rep["_count"] = len(rows)
                grouped.append(rep)
            data = grouped

        # 정렬
        if order_by:
            reverse = order_dir.lower() == "desc"
            try:
                data = sorted(data, key=lambda r: (r.get(order_by) is None, r.get(order_by)), reverse=reverse)
            except TypeError:
                data = sorted(data, key=lambda r: str(r.get(order_by, "")), reverse=reverse)

        # 제한
        if limit > 0:
            data = data[:limit]

        return data


@dataclass
class MaterializedView:
    view_name: str
    query: dict
    data: list = field(default_factory=list)
    created_at: str = ""
    refreshed_at: str = ""
    refresh_interval_sec: int = 3600

    def to_dict(self) -> dict:
        return {
            "view_name": self.view_name,
            "query": self.query,
            "row_count": len(self.data),
            "created_at": self.created_at,
            "refreshed_at": self.refreshed_at,
            "refresh_interval_sec": self.refresh_interval_sec,
        }

    def is_stale(self) -> bool:
        if not self.refreshed_at:
            return True
        try:
            last = datetime.fromisoformat(self.refreshed_at)
            return datetime.utcnow() >= last + timedelta(seconds=self.refresh_interval_sec)
        except ValueError:
            return True


class AnalyticsViewManager:
    """분석 뷰 관리자."""

    def __init__(self, warehouse: DataWarehouse) -> None:
        self._views: dict[str, MaterializedView] = {}
        self._query_engine = QueryEngine(warehouse)

    def create_view(self, view_name: str, query: dict, refresh_interval_sec: int = 3600) -> MaterializedView:
        now = datetime.utcnow().isoformat()
        view = MaterializedView(
            view_name=view_name,
            query=query,
            created_at=now,
            refresh_interval_sec=refresh_interval_sec,
        )
        view.data = self._query_engine.execute(query)
        view.refreshed_at = now
        self._views[view_name] = view
        return view

    def refresh_view(self, view_name: str) -> MaterializedView:
        view = self._views.get(view_name)
        if view is None:
            raise KeyError(f"뷰 없음: {view_name}")
        view.data = self._query_engine.execute(view.query)
        view.refreshed_at = datetime.utcnow().isoformat()
        return view

    def get_view(self, view_name: str) -> Optional[MaterializedView]:
        return self._views.get(view_name)

    def list_views(self) -> list[MaterializedView]:
        return list(self._views.values())

    def delete_view(self, view_name: str) -> bool:
        if view_name not in self._views:
            return False
        del self._views[view_name]
        return True


class SalesFactMart:
    """일별 매출 팩트 마트."""

    def __init__(self, warehouse: DataWarehouse) -> None:
        self._warehouse = warehouse
        self._data: list[dict] = []

    def build(self) -> list[dict]:
        raw = self._warehouse.query("orders") if self._warehouse.get_table("orders") else []

        if raw:
            daily: dict = {}
            for row in raw:
                date_key = str(row.get("created_at", ""))[:10] or "2024-01-01"
                channel = row.get("channel", "direct")
                category = row.get("category", "기타")
                key = (date_key, channel, category)
                if key not in daily:
                    daily[key] = {"date": date_key, "channel": channel, "category": category,
                                  "revenue": 0.0, "order_count": 0, "avg_order_value": 0.0}
                daily[key]["revenue"] += float(row.get("amount", 0))
                daily[key]["order_count"] += 1
            result = []
            for d in daily.values():
                d["avg_order_value"] = d["revenue"] / max(1, d["order_count"])
                result.append(d)
        else:
            channels = ["direct", "coupang", "naver", "amazon"]
            categories = ["전자", "의류", "식품", "생활"]
            result = [
                {
                    "date": f"2024-01-{i + 1:02d}",
                    "channel": channels[i % len(channels)],
                    "category": categories[i % len(categories)],
                    "revenue": 500000 + i * 50000,
                    "order_count": 10 + i,
                    "avg_order_value": (500000 + i * 50000) / (10 + i),
                }
                for i in range(30)
            ]
        self._data = result
        return result

    def get_data(self) -> list[dict]:
        return list(self._data)


class CustomerDimensionMart:
    """고객 차원 마트."""

    def __init__(self, warehouse: DataWarehouse) -> None:
        self._warehouse = warehouse
        self._data: list[dict] = []

    def build(self) -> list[dict]:
        raw = self._warehouse.query("customers") if self._warehouse.get_table("customers") else []

        if raw:
            result = [
                {
                    "customer_id": r.get("customer_id", f"C{i}"),
                    "tier": r.get("grade", "normal"),
                    "segment": "vip" if r.get("total_spent", 0) > 500000 else "regular",
                    "ltv": float(r.get("total_spent", 0)) * 2.5,
                    "last_order_date": r.get("last_order_date", "2024-01-15"),
                    "total_spent": float(r.get("total_spent", 0)),
                }
                for i, r in enumerate(raw)
            ]
        else:
            result = [
                {
                    "customer_id": f"C{i:04d}",
                    "tier": "vip" if i % 5 == 0 else "normal",
                    "segment": "premium" if i % 3 == 0 else "regular",
                    "ltv": 1000000 + i * 50000,
                    "last_order_date": f"2024-01-{(i % 28) + 1:02d}",
                    "total_spent": 500000 + i * 20000,
                }
                for i in range(40)
            ]
        self._data = result
        return result

    def get_data(self) -> list[dict]:
        return list(self._data)


class ProductPerformanceMart:
    """상품 성과 마트."""

    def __init__(self, warehouse: DataWarehouse) -> None:
        self._warehouse = warehouse
        self._data: list[dict] = []

    def build(self) -> list[dict]:
        result = [
            {
                "product_id": f"P{i:04d}",
                "name": f"상품{i}",
                "sales_count": 100 + i * 5,
                "revenue": (100 + i * 5) * (10000 + i * 200),
                "margin_rate": round(0.15 + (i % 10) * 0.02, 3),
                "return_rate": round(0.02 + (i % 5) * 0.005, 4),
                "rating": round(3.5 + (i % 10) * 0.15, 1),
            }
            for i in range(50)
        ]
        self._data = result
        return result

    def get_data(self) -> list[dict]:
        return list(self._data)


class InventorySnapshotMart:
    """재고 스냅샷 마트."""

    def __init__(self, warehouse: DataWarehouse) -> None:
        self._warehouse = warehouse
        self._data: list[dict] = []

    def build(self) -> list[dict]:
        result = [
            {
                "date": f"2024-01-{(i % 28) + 1:02d}",
                "product_id": f"P{i:04d}",
                "stock_level": max(0, 500 - i * 10),
                "turnover_rate": round(1.5 + (i % 8) * 0.3, 2),
                "stockout_rate": round(0.01 + (i % 5) * 0.005, 4),
            }
            for i in range(60)
        ]
        self._data = result
        return result

    def get_data(self) -> list[dict]:
        return list(self._data)


class VendorPerformanceMart:
    """판매자 성과 마트."""

    def __init__(self, warehouse: DataWarehouse) -> None:
        self._warehouse = warehouse
        self._data: list[dict] = []

    def build(self) -> list[dict]:
        result = [
            {
                "vendor_id": f"V{i:04d}",
                "name": f"판매자{i}",
                "revenue": 5000000 + i * 500000,
                "commission": round((5000000 + i * 500000) * 0.05, 0),
                "settlement_amount": round((5000000 + i * 500000) * 0.95, 0),
                "score": round(60 + (i % 40), 1),
            }
            for i in range(20)
        ]
        self._data = result
        return result

    def get_data(self) -> list[dict]:
        return list(self._data)
