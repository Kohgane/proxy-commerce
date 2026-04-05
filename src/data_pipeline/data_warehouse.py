"""src/data_pipeline/data_warehouse.py — 데이터 웨어하우스 (Phase 100)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from .pipeline_models import WarehouseSchema, WarehouseTable


class DataLoader(ABC):
    """데이터 적재 추상 기반 클래스."""

    @property
    @abstractmethod
    def loader_type(self) -> str:
        ...

    @abstractmethod
    def load(self, data: list[dict], table_name: str, mode: str) -> int:
        ...


class InMemoryLoader(DataLoader):
    """인메모리 웨어하우스 적재기."""

    def __init__(self, warehouse: "DataWarehouse") -> None:
        self._warehouse = warehouse

    @property
    def loader_type(self) -> str:
        return "in_memory"

    def load(self, data: list[dict], table_name: str, mode: str = "append") -> int:
        return self._warehouse.load_data(table_name, data, mode)


class FileLoader(DataLoader):
    """파일 적재기 (인메모리 시뮬레이션)."""

    def __init__(self, base_path: str = "/warehouse") -> None:
        self._base_path = base_path
        self._files: dict[str, list[dict]] = {}

    @property
    def loader_type(self) -> str:
        return "file"

    def load(self, data: list[dict], table_name: str, mode: str = "append") -> int:
        if mode == "replace":
            self._files[table_name] = list(data)
        elif mode == "upsert":
            existing = self._files.get(table_name, [])
            existing.extend(data)
            self._files[table_name] = existing
        else:  # append
            existing = self._files.get(table_name, [])
            existing.extend(data)
            self._files[table_name] = existing
        return len(data)


class PartitionManager:
    """파티션 관리자."""

    def __init__(self, warehouse: "DataWarehouse") -> None:
        self._warehouse = warehouse
        self._partitions: dict[str, list[dict]] = {}

    def create_partition(self, table_name: str, partition_key: str, partition_value: str) -> dict:
        key = f"{table_name}/{partition_key}={partition_value}"
        partition = {
            "table_name": table_name,
            "partition_key": partition_key,
            "partition_value": partition_value,
            "created_at": datetime.utcnow().isoformat(),
            "row_count": 0,
        }
        self._partitions.setdefault(table_name, []).append(partition)

        # 웨어하우스 테이블 파티션 목록 업데이트
        table = self._warehouse.get_table(table_name)
        if table and partition_value not in table.partitions:
            table.partitions.append(partition_value)

        return partition

    def get_partitions(self, table_name: str) -> list[dict]:
        return [p for p in self._partitions.get(table_name, [])]

    def delete_partition(self, table_name: str, partition_key: str, partition_value: str) -> bool:
        partitions = self._partitions.get(table_name, [])
        before = len(partitions)
        self._partitions[table_name] = [
            p for p in partitions
            if not (p["partition_key"] == partition_key and p["partition_value"] == partition_value)
        ]
        return len(self._partitions[table_name]) < before

    def get_partition_data(self, table_name: str, partition_key: str, partition_value: str) -> list[dict]:
        all_data = self._warehouse._data.get(table_name, [])
        return [row for row in all_data if str(row.get(partition_key)) == str(partition_value)]


class DataWarehouse:
    """인메모리 데이터 웨어하우스."""

    def __init__(self) -> None:
        self._tables: dict[str, WarehouseTable] = {}
        self._data: dict[str, list[dict]] = {}

    def create_table(self, table_name: str, schema: list[WarehouseSchema]) -> WarehouseTable:
        now = datetime.utcnow().isoformat()
        table = WarehouseTable(
            table_name=table_name,
            schema=list(schema),
            row_count=0,
            created_at=now,
        )
        self._tables[table_name] = table
        self._data[table_name] = []
        return table

    def drop_table(self, table_name: str) -> bool:
        if table_name not in self._tables:
            return False
        del self._tables[table_name]
        self._data.pop(table_name, None)
        return True

    def list_tables(self) -> list[WarehouseTable]:
        return list(self._tables.values())

    def get_table(self, table_name: str) -> Optional[WarehouseTable]:
        return self._tables.get(table_name)

    def load_data(self, table_name: str, data: list[dict], mode: str = "append") -> int:
        if table_name not in self._tables:
            # 자동으로 테이블 생성
            schema = [WarehouseSchema(name=k, type="str") for k in (data[0].keys() if data else [])]
            self.create_table(table_name, schema)

        if mode == "replace":
            self._data[table_name] = list(data)
        elif mode == "upsert":
            existing = self._data[table_name]
            id_key = next((k for k in (data[0].keys() if data else []) if "id" in k.lower()), None)
            if id_key:
                existing_ids = {r.get(id_key): i for i, r in enumerate(existing)}
                for row in data:
                    row_id = row.get(id_key)
                    if row_id in existing_ids:
                        existing[existing_ids[row_id]] = row
                    else:
                        existing.append(row)
                        existing_ids[row_id] = len(existing) - 1
            else:
                existing.extend(data)
        else:  # append
            self._data[table_name].extend(data)

        self._tables[table_name].row_count = len(self._data[table_name])
        self._tables[table_name].updated_at = datetime.utcnow().isoformat()
        return len(data)

    def query(self, table_name: str, filters: dict | None = None) -> list[dict]:
        data = list(self._data.get(table_name, []))
        if not filters:
            return data
        result = []
        for row in data:
            match = all(row.get(k) == v for k, v in filters.items())
            if match:
                result.append(row)
        return result

    def get_sample(self, table_name: str, n: int = 10) -> list[dict]:
        data = self._data.get(table_name, [])
        return list(data[:n])

    def get_stats(self) -> dict:
        total_rows = sum(len(d) for d in self._data.values())
        return {
            "total_tables": len(self._tables),
            "total_rows": total_rows,
            "disk_size_mb": round(total_rows * 0.001, 3),  # 모의 크기 계산
            "tables": [t.table_name for t in self._tables.values()],
        }
