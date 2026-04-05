"""src/data_pipeline/data_sources.py — 데이터 소스 (Phase 100)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class DataSource(ABC):
    """데이터 소스 추상 기반 클래스."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        ...

    @property
    @abstractmethod
    def source_type(self) -> str:
        ...

    @abstractmethod
    def extract(self, params: dict) -> list[dict]:
        ...

    @abstractmethod
    def validate_connection(self) -> bool:
        ...

    @abstractmethod
    def get_schema(self) -> list[dict]:
        ...


class InternalDBSource(DataSource):
    """내부 DB 데이터 소스."""

    def __init__(self, source_id: str = "internal_db") -> None:
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> str:
        return "internal_db"

    def extract(self, params: dict) -> list[dict]:
        table = params.get("table", "orders")
        limit = params.get("limit", 50)

        if table == "orders":
            return [
                {"order_id": f"O{i:04d}", "customer_id": f"C{i % 20:04d}",
                 "amount": 10000 + i * 500, "status": "completed",
                 "created_at": f"2024-01-{(i % 28) + 1:02d}"}
                for i in range(min(limit, 50))
            ]
        elif table == "products":
            return [
                {"product_id": f"P{i:04d}", "name": f"상품{i}", "price": 5000 + i * 100,
                 "category": ["전자", "의류", "식품"][i % 3], "stock": i * 10}
                for i in range(min(limit, 30))
            ]
        elif table == "customers":
            return [
                {"customer_id": f"C{i:04d}", "name": f"고객{i}",
                 "email": f"user{i}@example.com",
                 "grade": "vip" if i % 5 == 0 else "normal", "total_spent": i * 30000}
                for i in range(min(limit, 40))
            ]
        elif table == "inventory":
            return [
                {"item_id": f"I{i:04d}", "product_id": f"P{i:04d}",
                 "stock_level": i * 5, "reorder_point": 10, "location": f"창고{i % 3}"}
                for i in range(min(limit, 25))
            ]
        elif table == "reviews":
            return [
                {"review_id": f"R{i:04d}", "product_id": f"P{i % 30:04d}",
                 "rating": (i % 5) + 1, "comment": f"리뷰 내용 {i}", "helpful": i % 10}
                for i in range(min(limit, 60))
            ]
        return []

    def validate_connection(self) -> bool:
        return True

    def get_schema(self) -> list[dict]:
        return [
            {"name": "id", "type": "str", "nullable": False},
            {"name": "created_at", "type": "datetime", "nullable": True},
            {"name": "updated_at", "type": "datetime", "nullable": True},
        ]


class APISource(DataSource):
    """외부 API 데이터 소스."""

    def __init__(self, source_id: str = "api_source", endpoint: str = "", api_key: str = "") -> None:
        self._source_id = source_id
        self.endpoint = endpoint
        self.api_key = api_key

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> str:
        return "api"

    def extract(self, params: dict) -> list[dict]:
        data_type = params.get("type", "marketplace")
        limit = params.get("limit", 20)

        if data_type == "marketplace":
            return [
                {"marketplace": ["amazon", "coupang", "naver"][i % 3],
                 "product_id": f"MP{i:04d}", "price": 15000 + i * 200,
                 "rank": i + 1, "seller": f"셀러{i}"}
                for i in range(min(limit, 20))
            ]
        elif data_type == "competitor_price":
            return [
                {"competitor": f"경쟁사{i % 5}", "product_id": f"P{i:04d}",
                 "price": 12000 + i * 150, "updated_at": f"2024-01-{(i % 28) + 1:02d}"}
                for i in range(min(limit, 15))
            ]
        return [{"api_key": f"data_{i}", "value": i} for i in range(min(limit, 10))]

    def validate_connection(self) -> bool:
        return True

    def get_schema(self) -> list[dict]:
        return [
            {"name": "id", "type": "str", "nullable": False},
            {"name": "timestamp", "type": "datetime", "nullable": True},
            {"name": "data", "type": "dict", "nullable": True},
        ]


class FileSource(DataSource):
    """파일 데이터 소스."""

    def __init__(self, source_id: str = "file_source", file_type: str = "csv") -> None:
        self._source_id = source_id
        self.file_type = file_type

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> str:
        return "file"

    def extract(self, params: dict) -> list[dict]:
        filename = params.get("filename", "data")
        limit = params.get("limit", 30)

        if self.file_type == "csv":
            return [
                {"row_num": i, "col_a": f"값A{i}", "col_b": i * 10, "col_c": f"2024-01-{(i % 28) + 1:02d}"}
                for i in range(min(limit, 30))
            ]
        elif self.file_type == "json":
            return [
                {"id": i, "name": f"항목{i}", "metadata": {"source": filename, "index": i}}
                for i in range(min(limit, 30))
            ]
        return [{"line": i, "content": f"데이터 {i}"} for i in range(min(limit, 20))]

    def validate_connection(self) -> bool:
        return True

    def get_schema(self) -> list[dict]:
        return [
            {"name": "row_num", "type": "int", "nullable": False},
            {"name": "content", "type": "str", "nullable": True},
        ]


class EventStreamSource(DataSource):
    """이벤트 스트림 데이터 소스."""

    def __init__(self, source_id: str = "event_stream") -> None:
        self._source_id = source_id

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def source_type(self) -> str:
        return "event_stream"

    def extract(self, params: dict) -> list[dict]:
        limit = params.get("limit", 50)
        # EventStore 연동 시도, 실패 시 모의 이벤트 반환
        try:
            from ..event_sourcing.event_store import EventStore
            store = EventStore()
            events = store.get_all_events() if hasattr(store, "get_all_events") else []
            if events:
                return [{"event_id": e.event_id, "type": e.event_type,
                         "timestamp": str(e.timestamp), "data": e.data}
                        for e in events[:limit]]
        except Exception:
            pass

        return [
            {"event_id": f"EVT{i:04d}", "type": ["order_placed", "payment_completed", "shipped"][i % 3],
             "aggregate_id": f"AGG{i % 20:04d}", "timestamp": f"2024-01-{(i % 28) + 1:02d}T{i % 24:02d}:00:00",
             "version": i + 1}
            for i in range(min(limit, 50))
        ]

    def validate_connection(self) -> bool:
        return True

    def get_schema(self) -> list[dict]:
        return [
            {"name": "event_id", "type": "str", "nullable": False},
            {"name": "type", "type": "str", "nullable": False},
            {"name": "aggregate_id", "type": "str", "nullable": True},
            {"name": "timestamp", "type": "datetime", "nullable": False},
            {"name": "version", "type": "int", "nullable": False},
        ]


class SourceRegistry:
    """데이터 소스 레지스트리."""

    def __init__(self) -> None:
        self._sources: dict[str, DataSource] = {}

    def register(self, source: DataSource) -> None:
        self._sources[source.source_id] = source

    def get(self, source_id: str) -> Optional[DataSource]:
        return self._sources.get(source_id)

    def list_sources(self) -> list[dict]:
        return [
            {"source_id": s.source_id, "source_type": s.source_type}
            for s in self._sources.values()
        ]

    def unregister(self, source_id: str) -> bool:
        if source_id not in self._sources:
            return False
        del self._sources[source_id]
        return True
