"""tests/test_data_pipeline.py — 데이터 파이프라인 Phase 100 테스트."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── TestPipelineModels ─────────────────────────────────────────────────────

class TestPipelineModels:
    def test_pipeline_status_values(self):
        from src.data_pipeline.pipeline_models import PipelineStatus
        assert PipelineStatus.idle.value == "idle"
        assert PipelineStatus.running.value == "running"
        assert PipelineStatus.completed.value == "completed"
        assert PipelineStatus.failed.value == "failed"
        assert PipelineStatus.paused.value == "paused"

    def test_pipeline_status_all_members(self):
        from src.data_pipeline.pipeline_models import PipelineStatus
        members = {s.value for s in PipelineStatus}
        assert members == {"idle", "running", "completed", "failed", "paused"}

    def test_etl_pipeline_to_dict(self):
        from src.data_pipeline.pipeline_models import ETLPipeline, PipelineStatus
        p = ETLPipeline(
            pipeline_id="p1",
            name="테스트 파이프라인",
            source="internal_db",
            transforms=[{"type": "filter"}],
            destination="dw_orders",
            created_at="2024-01-01T00:00:00",
        )
        d = p.to_dict()
        assert d["pipeline_id"] == "p1"
        assert d["name"] == "테스트 파이프라인"
        assert d["status"] == "idle"
        assert d["source"] == "internal_db"

    def test_etl_pipeline_defaults(self):
        from src.data_pipeline.pipeline_models import ETLPipeline, PipelineStatus
        p = ETLPipeline(
            pipeline_id="p2", name="기본", source="s", transforms=[], destination="d", created_at="2024-01-01"
        )
        assert p.schedule == ""
        assert p.last_run == ""
        assert p.metadata == {}
        assert p.status == PipelineStatus.idle

    def test_warehouse_schema_to_dict(self):
        from src.data_pipeline.pipeline_models import WarehouseSchema
        s = WarehouseSchema(name="order_id", type="str", nullable=False, primary_key=True)
        d = s.to_dict()
        assert d["name"] == "order_id"
        assert d["type"] == "str"
        assert d["primary_key"] is True
        assert d["nullable"] is False

    def test_warehouse_schema_defaults(self):
        from src.data_pipeline.pipeline_models import WarehouseSchema
        s = WarehouseSchema(name="amount", type="float")
        assert s.nullable is True
        assert s.primary_key is False
        assert s.description == ""

    def test_warehouse_table_to_dict(self):
        from src.data_pipeline.pipeline_models import WarehouseTable, WarehouseSchema
        schema = [WarehouseSchema(name="id", type="str")]
        t = WarehouseTable(table_name="orders", schema=schema, row_count=100, created_at="2024-01-01")
        d = t.to_dict()
        assert d["table_name"] == "orders"
        assert d["row_count"] == 100
        assert len(d["schema"]) == 1

    def test_run_record_to_dict(self):
        from src.data_pipeline.pipeline_models import RunRecord
        r = RunRecord(
            run_id="r1", pipeline_id="p1", status="completed",
            started_at="2024-01-01T00:00:00", finished_at="2024-01-01T00:01:00",
            rows_processed=50,
        )
        d = r.to_dict()
        assert d["run_id"] == "r1"
        assert d["status"] == "completed"
        assert d["rows_processed"] == 50

    def test_run_record_defaults(self):
        from src.data_pipeline.pipeline_models import RunRecord
        r = RunRecord(run_id="r2", pipeline_id="p2", status="failed", started_at="2024-01-01")
        assert r.finished_at == ""
        assert r.rows_processed == 0
        assert r.error == ""
        assert r.metrics == {}


# ── TestETLEngine ─────────────────────────────────────────────────────────

class TestETLEngine:
    def setup_method(self):
        from src.data_pipeline.etl_engine import ETLEngine
        self.engine = ETLEngine()

    def test_create_pipeline(self):
        p = self.engine.create_pipeline("파이프1", "internal_db", [], "dw_test")
        assert p.pipeline_id
        assert p.name == "파이프1"
        assert p.source == "internal_db"

    def test_get_pipeline(self):
        p = self.engine.create_pipeline("파이프2", "api_source", [], "dw_api")
        found = self.engine.get_pipeline(p.pipeline_id)
        assert found is not None
        assert found.pipeline_id == p.pipeline_id

    def test_get_pipeline_not_found(self):
        result = self.engine.get_pipeline("nonexistent")
        assert result is None

    def test_list_pipelines(self):
        self.engine.create_pipeline("P1", "s1", [], "d1")
        self.engine.create_pipeline("P2", "s2", [], "d2")
        pipelines = self.engine.list_pipelines()
        assert len(pipelines) >= 2

    def test_update_pipeline(self):
        p = self.engine.create_pipeline("원본", "s", [], "d")
        updated = self.engine.update_pipeline(p.pipeline_id, name="수정됨")
        assert updated.name == "수정됨"

    def test_update_pipeline_not_found(self):
        result = self.engine.update_pipeline("nonexistent", name="test")
        assert result is None

    def test_delete_pipeline(self):
        p = self.engine.create_pipeline("삭제용", "s", [], "d")
        deleted = self.engine.delete_pipeline(p.pipeline_id)
        assert deleted is True
        assert self.engine.get_pipeline(p.pipeline_id) is None

    def test_delete_pipeline_not_found(self):
        result = self.engine.delete_pipeline("nonexistent")
        assert result is False

    def test_run_pipeline_success(self):
        p = self.engine.create_pipeline("실행용", "orders", [], "dw_orders")
        record = self.engine.run_pipeline(p.pipeline_id)
        assert record.status == "completed"
        assert record.rows_processed > 0

    def test_run_pipeline_not_found(self):
        with pytest.raises(KeyError):
            self.engine.run_pipeline("nonexistent")

    def test_stop_pipeline(self):
        from src.data_pipeline.pipeline_models import PipelineStatus
        p = self.engine.create_pipeline("정지용", "s", [], "d")
        result = self.engine.stop_pipeline(p.pipeline_id)
        assert result is True
        assert p.status == PipelineStatus.paused

    def test_get_run_history(self):
        p = self.engine.create_pipeline("이력용", "orders", [], "dw")
        self.engine.run_pipeline(p.pipeline_id)
        history = self.engine.get_run_history(p.pipeline_id)
        assert len(history) == 1
        assert history[0].pipeline_id == p.pipeline_id


# ── TestPipelineScheduler ─────────────────────────────────────────────────

class TestPipelineScheduler:
    def setup_method(self):
        from src.data_pipeline.etl_engine import PipelineScheduler
        self.scheduler = PipelineScheduler()

    def test_next_run_hourly(self):
        result = self.scheduler.next_run("hourly")
        assert "T" in result  # ISO 포맷

    def test_next_run_daily(self):
        result = self.scheduler.next_run("daily")
        assert result

    def test_next_run_weekly(self):
        result = self.scheduler.next_run("weekly")
        assert result

    def test_next_run_monthly(self):
        result = self.scheduler.next_run("monthly")
        assert result

    def test_is_due_no_last_run(self):
        result = self.scheduler.is_due("daily", "")
        assert result is True

    def test_is_due_no_schedule(self):
        result = self.scheduler.is_due("", "2024-01-01T00:00:00")
        assert result is False

    def test_is_due_recent_run(self):
        from datetime import datetime
        last_run = datetime.utcnow().isoformat()
        result = self.scheduler.is_due("hourly", last_run)
        assert result is False

    def test_parse_cron(self):
        result = self.scheduler.parse_cron("0 9 * * 1")
        assert result["minute"] == "0"
        assert result["hour"] == "9"
        assert result["day_of_week"] == "1"

    def test_parse_cron_short(self):
        result = self.scheduler.parse_cron("*/15")
        assert result["minute"] == "*/15"


# ── TestDataSources ───────────────────────────────────────────────────────

class TestDataSources:
    def test_internal_db_source_orders(self):
        from src.data_pipeline.data_sources import InternalDBSource
        src = InternalDBSource()
        data = src.extract({"table": "orders"})
        assert len(data) > 0
        assert "order_id" in data[0]

    def test_internal_db_source_products(self):
        from src.data_pipeline.data_sources import InternalDBSource
        src = InternalDBSource()
        data = src.extract({"table": "products"})
        assert len(data) > 0
        assert "product_id" in data[0]

    def test_internal_db_source_customers(self):
        from src.data_pipeline.data_sources import InternalDBSource
        src = InternalDBSource()
        data = src.extract({"table": "customers"})
        assert len(data) > 0
        assert "customer_id" in data[0]

    def test_internal_db_source_inventory(self):
        from src.data_pipeline.data_sources import InternalDBSource
        src = InternalDBSource()
        data = src.extract({"table": "inventory"})
        assert len(data) > 0
        assert "stock_level" in data[0]

    def test_internal_db_source_reviews(self):
        from src.data_pipeline.data_sources import InternalDBSource
        src = InternalDBSource()
        data = src.extract({"table": "reviews"})
        assert len(data) > 0
        assert "rating" in data[0]

    def test_internal_db_validate_connection(self):
        from src.data_pipeline.data_sources import InternalDBSource
        src = InternalDBSource()
        assert src.validate_connection() is True

    def test_internal_db_get_schema(self):
        from src.data_pipeline.data_sources import InternalDBSource
        src = InternalDBSource()
        schema = src.get_schema()
        assert isinstance(schema, list)
        assert len(schema) > 0

    def test_api_source_extract(self):
        from src.data_pipeline.data_sources import APISource
        src = APISource()
        data = src.extract({"type": "marketplace"})
        assert len(data) > 0

    def test_api_source_competitor_price(self):
        from src.data_pipeline.data_sources import APISource
        src = APISource()
        data = src.extract({"type": "competitor_price"})
        assert len(data) > 0
        assert "price" in data[0]

    def test_file_source_csv(self):
        from src.data_pipeline.data_sources import FileSource
        src = FileSource(file_type="csv")
        data = src.extract({})
        assert len(data) > 0

    def test_file_source_json(self):
        from src.data_pipeline.data_sources import FileSource
        src = FileSource(file_type="json")
        data = src.extract({})
        assert len(data) > 0

    def test_event_stream_source(self):
        from src.data_pipeline.data_sources import EventStreamSource
        src = EventStreamSource()
        data = src.extract({})
        assert len(data) > 0

    def test_source_registry_register_and_get(self):
        from src.data_pipeline.data_sources import SourceRegistry, InternalDBSource
        registry = SourceRegistry()
        src = InternalDBSource("test_db")
        registry.register(src)
        found = registry.get("test_db")
        assert found is not None

    def test_source_registry_list(self):
        from src.data_pipeline.data_sources import SourceRegistry, APISource, FileSource
        registry = SourceRegistry()
        registry.register(APISource("api1"))
        registry.register(FileSource("file1"))
        sources = registry.list_sources()
        assert len(sources) == 2

    def test_source_registry_unregister(self):
        from src.data_pipeline.data_sources import SourceRegistry, InternalDBSource
        registry = SourceRegistry()
        registry.register(InternalDBSource("db1"))
        result = registry.unregister("db1")
        assert result is True
        assert registry.get("db1") is None

    def test_source_registry_unregister_not_found(self):
        from src.data_pipeline.data_sources import SourceRegistry
        registry = SourceRegistry()
        result = registry.unregister("nonexistent")
        assert result is False


# ── TestTransforms ────────────────────────────────────────────────────────

class TestTransforms:
    def _sample_data(self):
        return [
            {"id": "1", "name": "사과", "price": 1000, "category": "과일"},
            {"id": "2", "name": "바나나", "price": 500, "category": "과일"},
            {"id": "3", "name": "당근", "price": 800, "category": "채소"},
            {"id": "1", "name": "사과중복", "price": 1200, "category": "과일"},
        ]

    def test_filter_eq(self):
        from src.data_pipeline.transforms import FilterTransform
        data = self._sample_data()
        t = FilterTransform("category", "eq", "채소")
        result = t.apply(data)
        assert len(result) == 1
        assert result[0]["name"] == "당근"

    def test_filter_gt(self):
        from src.data_pipeline.transforms import FilterTransform
        data = self._sample_data()
        t = FilterTransform("price", "gt", 700)
        result = t.apply(data)
        assert all(r["price"] > 700 for r in result)

    def test_filter_in(self):
        from src.data_pipeline.transforms import FilterTransform
        data = self._sample_data()
        t = FilterTransform("name", "in", ["사과", "당근"])
        result = t.apply(data)
        assert len(result) == 2

    def test_map_rename_field(self):
        from src.data_pipeline.transforms import MapTransform
        data = [{"old_name": "val1"}, {"old_name": "val2"}]
        t = MapTransform({"old_name": "new_name"})
        result = t.apply(data)
        assert all("new_name" in r for r in result)
        assert all("old_name" not in r for r in result)

    def test_aggregate_sum(self):
        from src.data_pipeline.transforms import AggregateTransform
        data = [
            {"category": "과일", "price": 1000},
            {"category": "과일", "price": 500},
            {"category": "채소", "price": 800},
        ]
        t = AggregateTransform(group_by=["category"], aggregations={"price": "sum"})
        result = t.apply(data)
        fruit = next(r for r in result if r["category"] == "과일")
        assert fruit["price_sum"] == 1500.0

    def test_aggregate_count(self):
        from src.data_pipeline.transforms import AggregateTransform
        data = self._sample_data()
        t = AggregateTransform(group_by=["category"], aggregations={"id": "count"})
        result = t.apply(data)
        assert len(result) == 2

    def test_join_inner(self):
        from src.data_pipeline.transforms import JoinTransform
        left = [{"id": "1", "name": "A"}, {"id": "2", "name": "B"}, {"id": "3", "name": "C"}]
        right = [{"id": "1", "value": 100}, {"id": "2", "value": 200}]
        t = JoinTransform(right, "id", "inner")
        result = t.apply(left)
        assert len(result) == 2

    def test_join_left(self):
        from src.data_pipeline.transforms import JoinTransform
        left = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        right = [{"id": "1", "val": 10}]
        t = JoinTransform(right, "id", "left")
        result = t.apply(left)
        assert len(result) == 3  # 모든 left 레코드 유지

    def test_enrich(self):
        from src.data_pipeline.transforms import EnrichTransform
        data = [{"product_id": "P1"}, {"product_id": "P2"}]
        lookup = {"P1": {"category": "전자", "brand": "삼성"}, "P2": {"category": "의류", "brand": "나이키"}}
        t = EnrichTransform(lookup, "product_id", ["category", "brand"])
        result = t.apply(data)
        assert result[0]["category"] == "전자"
        assert result[1]["brand"] == "나이키"

    def test_deduplicate_last(self):
        from src.data_pipeline.transforms import DeduplicateTransform
        data = self._sample_data()
        t = DeduplicateTransform(key_fields=["id"], keep="last")
        result = t.apply(data)
        ids = [r["id"] for r in result]
        assert len(ids) == len(set(ids))

    def test_deduplicate_first(self):
        from src.data_pipeline.transforms import DeduplicateTransform
        data = self._sample_data()
        t = DeduplicateTransform(key_fields=["id"], keep="first")
        result = t.apply(data)
        # id "1" 중복 제거 후 3건
        assert len(result) == 3
        id1 = next(r for r in result if r["id"] == "1")
        assert id1["name"] == "사과"  # 첫 번째 유지

    def test_typecast_int(self):
        from src.data_pipeline.transforms import TypeCastTransform
        data = [{"price": "1000"}, {"price": "2500"}]
        t = TypeCastTransform({"price": "int"})
        result = t.apply(data)
        assert result[0]["price"] == 1000
        assert isinstance(result[0]["price"], int)

    def test_typecast_float(self):
        from src.data_pipeline.transforms import TypeCastTransform
        data = [{"rate": "0.15"}]
        t = TypeCastTransform({"rate": "float"})
        result = t.apply(data)
        assert result[0]["rate"] == 0.15

    def test_transform_chain(self):
        from src.data_pipeline.transforms import TransformChain, FilterTransform, MapTransform
        data = [{"id": "1", "price": 1000, "cat": "A"}, {"id": "2", "price": 500, "cat": "B"}]
        chain = TransformChain([
            FilterTransform("price", "gt", 600),
            MapTransform({"cat": "category"}),
        ])
        result = chain.apply(data)
        assert len(result) == 1
        assert "category" in result[0]

    def test_transform_chain_add(self):
        from src.data_pipeline.transforms import TransformChain, FilterTransform
        chain = TransformChain()
        chain.add(FilterTransform("x", "gt", 0))
        data = [{"x": 5}, {"x": -1}]
        result = chain.apply(data)
        assert len(result) == 1

    def test_transform_validate(self):
        from src.data_pipeline.transforms import FilterTransform
        t = FilterTransform("f", "eq", "v")
        assert t.validate([]) is True
        assert t.validate([{"f": "v"}]) is True


# ── TestDataWarehouse ─────────────────────────────────────────────────────

class TestDataWarehouse:
    def setup_method(self):
        from src.data_pipeline.data_warehouse import DataWarehouse
        self.wh = DataWarehouse()

    def test_create_table(self):
        from src.data_pipeline.pipeline_models import WarehouseSchema
        schema = [WarehouseSchema("id", "str"), WarehouseSchema("amount", "float")]
        table = self.wh.create_table("orders", schema)
        assert table.table_name == "orders"
        assert table.row_count == 0

    def test_drop_table(self):
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("temp", [WarehouseSchema("x", "str")])
        result = self.wh.drop_table("temp")
        assert result is True
        assert self.wh.get_table("temp") is None

    def test_drop_table_not_found(self):
        result = self.wh.drop_table("nonexistent")
        assert result is False

    def test_list_tables(self):
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("t1", [WarehouseSchema("a", "str")])
        self.wh.create_table("t2", [WarehouseSchema("b", "str")])
        tables = self.wh.list_tables()
        names = [t.table_name for t in tables]
        assert "t1" in names
        assert "t2" in names

    def test_load_data_append(self):
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("sales", [WarehouseSchema("id", "str")])
        data = [{"id": "1", "val": 100}, {"id": "2", "val": 200}]
        count = self.wh.load_data("sales", data, "append")
        assert count == 2
        assert self.wh.get_table("sales").row_count == 2

    def test_load_data_replace(self):
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("rep", [WarehouseSchema("id", "str")])
        self.wh.load_data("rep", [{"id": "1"}], "append")
        self.wh.load_data("rep", [{"id": "2"}, {"id": "3"}], "replace")
        assert self.wh.get_table("rep").row_count == 2

    def test_load_data_upsert(self):
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("ups", [WarehouseSchema("id", "str")])
        self.wh.load_data("ups", [{"id": "1", "val": 10}], "append")
        self.wh.load_data("ups", [{"id": "1", "val": 99}, {"id": "2", "val": 20}], "upsert")
        data = self.wh.query("ups")
        assert len(data) == 2
        id1 = next(r for r in data if r["id"] == "1")
        assert id1["val"] == 99

    def test_query_no_filter(self):
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("q1", [WarehouseSchema("x", "str")])
        self.wh.load_data("q1", [{"x": "a"}, {"x": "b"}], "append")
        result = self.wh.query("q1")
        assert len(result) == 2

    def test_query_with_filter(self):
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("q2", [WarehouseSchema("status", "str")])
        self.wh.load_data("q2", [{"status": "A"}, {"status": "B"}, {"status": "A"}], "append")
        result = self.wh.query("q2", {"status": "A"})
        assert len(result) == 2

    def test_get_sample(self):
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("samp", [WarehouseSchema("n", "int")])
        self.wh.load_data("samp", [{"n": i} for i in range(20)], "append")
        sample = self.wh.get_sample("samp", n=5)
        assert len(sample) == 5

    def test_get_stats(self):
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("st1", [WarehouseSchema("x", "str")])
        self.wh.load_data("st1", [{"x": "a"} for _ in range(10)], "append")
        stats = self.wh.get_stats()
        assert stats["total_tables"] >= 1
        assert stats["total_rows"] >= 10

    def test_auto_create_table_on_load(self):
        """테이블 없이 로드하면 자동 생성."""
        count = self.wh.load_data("auto_table", [{"a": 1, "b": 2}], "append")
        assert count == 1
        assert self.wh.get_table("auto_table") is not None


# ── TestDataLoaders ───────────────────────────────────────────────────────

class TestDataLoaders:
    def test_in_memory_loader_append(self):
        from src.data_pipeline.data_warehouse import DataWarehouse, InMemoryLoader
        from src.data_pipeline.pipeline_models import WarehouseSchema
        wh = DataWarehouse()
        wh.create_table("t", [WarehouseSchema("id", "str")])
        loader = InMemoryLoader(wh)
        count = loader.load([{"id": "1"}, {"id": "2"}], "t", "append")
        assert count == 2
        assert wh.get_table("t").row_count == 2

    def test_in_memory_loader_type(self):
        from src.data_pipeline.data_warehouse import DataWarehouse, InMemoryLoader
        loader = InMemoryLoader(DataWarehouse())
        assert loader.loader_type == "in_memory"

    def test_file_loader_append(self):
        from src.data_pipeline.data_warehouse import FileLoader
        loader = FileLoader()
        count = loader.load([{"x": 1}, {"x": 2}], "test_table", "append")
        assert count == 2

    def test_file_loader_replace(self):
        from src.data_pipeline.data_warehouse import FileLoader
        loader = FileLoader()
        loader.load([{"x": 1}], "ft", "append")
        count = loader.load([{"x": 2}, {"x": 3}], "ft", "replace")
        assert count == 2
        assert len(loader._files["ft"]) == 2

    def test_file_loader_type(self):
        from src.data_pipeline.data_warehouse import FileLoader
        loader = FileLoader()
        assert loader.loader_type == "file"


# ── TestPartitionManager ──────────────────────────────────────────────────

class TestPartitionManager:
    def setup_method(self):
        from src.data_pipeline.data_warehouse import DataWarehouse, PartitionManager
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh = DataWarehouse()
        schema = [WarehouseSchema("date", "str"), WarehouseSchema("value", "int")]
        self.wh.create_table("partitioned", schema)
        self.wh.load_data("partitioned", [
            {"date": "2024-01", "value": 100},
            {"date": "2024-01", "value": 200},
            {"date": "2024-02", "value": 300},
        ], "append")
        self.pm = PartitionManager(self.wh)

    def test_create_partition(self):
        p = self.pm.create_partition("partitioned", "date", "2024-01")
        assert p["table_name"] == "partitioned"
        assert p["partition_key"] == "date"
        assert p["partition_value"] == "2024-01"

    def test_get_partitions(self):
        self.pm.create_partition("partitioned", "date", "2024-01")
        self.pm.create_partition("partitioned", "date", "2024-02")
        partitions = self.pm.get_partitions("partitioned")
        assert len(partitions) == 2

    def test_delete_partition(self):
        self.pm.create_partition("partitioned", "date", "2024-01")
        result = self.pm.delete_partition("partitioned", "date", "2024-01")
        assert result is True

    def test_delete_partition_not_found(self):
        result = self.pm.delete_partition("partitioned", "date", "9999-99")
        assert result is False

    def test_get_partition_data(self):
        data = self.pm.get_partition_data("partitioned", "date", "2024-01")
        assert len(data) == 2
        assert all(r["date"] == "2024-01" for r in data)


# ── TestDataQuality ───────────────────────────────────────────────────────

class TestDataQuality:
    def _sample_data(self):
        return [
            {"id": "1", "email": "a@b.com", "age": 25, "status": "active"},
            {"id": "2", "email": "c@d.com", "age": 30, "status": "inactive"},
            {"id": "3", "email": None, "age": -1, "status": "active"},
            {"id": "2", "email": "dup@test.com", "age": 40, "status": "deleted"},
        ]

    def test_not_null_rule_pass(self):
        from src.data_pipeline.data_quality import NotNullRule
        rule = NotNullRule(["id"])
        data = [{"id": "1"}, {"id": "2"}]
        passed, violations = rule.check(data)
        assert passed == 2
        assert len(violations) == 0

    def test_not_null_rule_fail(self):
        from src.data_pipeline.data_quality import NotNullRule
        rule = NotNullRule(["email"])
        data = self._sample_data()
        passed, violations = rule.check(data)
        assert len(violations) > 0

    def test_unique_rule_pass(self):
        from src.data_pipeline.data_quality import UniqueRule
        rule = UniqueRule(["id"])
        data = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        passed, violations = rule.check(data)
        assert len(violations) == 0

    def test_unique_rule_fail(self):
        from src.data_pipeline.data_quality import UniqueRule
        rule = UniqueRule(["id"])
        data = self._sample_data()
        passed, violations = rule.check(data)
        assert len(violations) > 0

    def test_range_rule_pass(self):
        from src.data_pipeline.data_quality import RangeRule
        rule = RangeRule("age", min_val=0, max_val=150)
        data = [{"age": 25}, {"age": 30}]
        passed, violations = rule.check(data)
        assert len(violations) == 0

    def test_range_rule_fail(self):
        from src.data_pipeline.data_quality import RangeRule
        rule = RangeRule("age", min_val=0)
        data = self._sample_data()
        passed, violations = rule.check(data)
        neg = [v for v in violations if "최솟값" in v.message]
        assert len(neg) > 0

    def test_pattern_rule_pass(self):
        from src.data_pipeline.data_quality import PatternRule
        rule = PatternRule("email", r".+@.+\..+")
        data = [{"email": "a@b.com"}, {"email": "c@d.org"}]
        passed, violations = rule.check(data)
        assert len(violations) == 0

    def test_pattern_rule_fail(self):
        from src.data_pipeline.data_quality import PatternRule
        rule = PatternRule("email", r".+@.+\..+")
        data = [{"email": "not-an-email"}]
        passed, violations = rule.check(data)
        assert len(violations) == 1

    def test_referential_integrity_pass(self):
        from src.data_pipeline.data_quality import ReferentialIntegrityRule
        rule = ReferentialIntegrityRule("status", {"active", "inactive"})
        data = [{"status": "active"}, {"status": "inactive"}]
        passed, violations = rule.check(data)
        assert len(violations) == 0

    def test_referential_integrity_fail(self):
        from src.data_pipeline.data_quality import ReferentialIntegrityRule
        rule = ReferentialIntegrityRule("status", {"active", "inactive"})
        data = self._sample_data()
        passed, violations = rule.check(data)
        assert len(violations) > 0

    def test_freshness_rule_pass(self):
        from src.data_pipeline.data_quality import FreshnessRule
        from datetime import datetime
        rule = FreshnessRule("ts", max_age_hours=24)
        data = [{"ts": datetime.utcnow().isoformat()}]
        passed, violations = rule.check(data)
        assert len(violations) == 0

    def test_freshness_rule_fail(self):
        from src.data_pipeline.data_quality import FreshnessRule
        rule = FreshnessRule("ts", max_age_hours=1)
        data = [{"ts": "2020-01-01T00:00:00"}]
        passed, violations = rule.check(data)
        assert len(violations) == 1

    def test_quality_checker_check(self):
        from src.data_pipeline.data_quality import DataQualityChecker, NotNullRule
        checker = DataQualityChecker()
        checker.add_rule(NotNullRule(["id"]))
        data = [{"id": "1"}, {"id": "2"}]
        report = checker.check(data, "test_table")
        assert report.table_name == "test_table"
        assert report.total_rows == 2
        assert 0 <= report.score <= 100

    def test_quality_checker_add_remove_rule(self):
        from src.data_pipeline.data_quality import DataQualityChecker, NotNullRule
        checker = DataQualityChecker()
        rule = NotNullRule(["id"])
        checker.add_rule(rule)
        assert rule.rule_name in {r for r in [rule.rule_name]}
        removed = checker.remove_rule(rule.rule_name)
        assert removed is True

    def test_quality_checker_get_reports(self):
        from src.data_pipeline.data_quality import DataQualityChecker, UniqueRule
        checker = DataQualityChecker()
        checker.add_rule(UniqueRule(["id"]))
        checker.check([{"id": "1"}, {"id": "2"}], "t1")
        checker.check([{"id": "3"}], "t2")
        all_reports = checker.get_reports()
        assert len(all_reports) == 2
        t1_reports = checker.get_reports("t1")
        assert len(t1_reports) == 1

    def test_quality_alert(self):
        from src.data_pipeline.data_quality import DataQualityChecker, NotNullRule
        checker = DataQualityChecker()
        checker.add_rule(NotNullRule(["id", "email"]))
        data = [{"id": None, "email": None} for _ in range(10)]
        report = checker.check(data, "bad_table")
        alert = checker.check_threshold(report, threshold=95.0)
        assert alert is not None
        assert alert.table_name == "bad_table"

    def test_quality_no_alert_when_above_threshold(self):
        from src.data_pipeline.data_quality import DataQualityChecker, NotNullRule
        checker = DataQualityChecker()
        checker.add_rule(NotNullRule(["id"]))
        data = [{"id": str(i)} for i in range(10)]
        report = checker.check(data, "good_table")
        alert = checker.check_threshold(report, threshold=50.0)
        assert alert is None

    def test_quality_violation_to_dict(self):
        from src.data_pipeline.data_quality import QualityViolation
        v = QualityViolation(rule_name="test", field="id", row_index=0, value=None, message="test msg")
        d = v.to_dict()
        assert d["rule_name"] == "test"
        assert d["row_index"] == 0


# ── TestAnalyticsViews ────────────────────────────────────────────────────

class TestAnalyticsViews:
    def setup_method(self):
        from src.data_pipeline.data_warehouse import DataWarehouse
        self.wh = DataWarehouse()

    def test_query_engine_basic(self):
        from src.data_pipeline.analytics_views import QueryEngine
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("items", [WarehouseSchema("id", "str"), WarehouseSchema("val", "int")])
        self.wh.load_data("items", [{"id": str(i), "val": i} for i in range(10)], "append")
        engine = QueryEngine(self.wh)
        result = engine.execute({"table": "items"})
        assert len(result) == 10

    def test_query_engine_with_limit(self):
        from src.data_pipeline.analytics_views import QueryEngine
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("lmt", [WarehouseSchema("x", "int")])
        self.wh.load_data("lmt", [{"x": i} for i in range(20)], "append")
        engine = QueryEngine(self.wh)
        result = engine.execute({"table": "lmt", "limit": 5})
        assert len(result) == 5

    def test_query_engine_with_order(self):
        from src.data_pipeline.analytics_views import QueryEngine
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("ord", [WarehouseSchema("v", "int")])
        self.wh.load_data("ord", [{"v": 3}, {"v": 1}, {"v": 2}], "append")
        engine = QueryEngine(self.wh)
        result = engine.execute({"table": "ord", "order_by": "v", "order_dir": "asc"})
        vals = [r["v"] for r in result]
        assert vals == sorted(vals)

    def test_query_engine_select_fields(self):
        from src.data_pipeline.analytics_views import QueryEngine
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("sel", [WarehouseSchema("a", "str"), WarehouseSchema("b", "str")])
        self.wh.load_data("sel", [{"a": "x", "b": "y"}], "append")
        engine = QueryEngine(self.wh)
        result = engine.execute({"table": "sel", "select": ["a"]})
        assert "a" in result[0]
        assert "b" not in result[0]

    def test_materialized_view_is_stale(self):
        from src.data_pipeline.analytics_views import MaterializedView
        view = MaterializedView(
            view_name="test_view",
            query={"table": "x"},
            refresh_interval_sec=3600,
        )
        assert view.is_stale() is True  # refreshed_at 없으면 stale

    def test_materialized_view_not_stale(self):
        from src.data_pipeline.analytics_views import MaterializedView
        from datetime import datetime
        view = MaterializedView(
            view_name="fresh_view",
            query={},
            refreshed_at=datetime.utcnow().isoformat(),
            refresh_interval_sec=3600,
        )
        assert view.is_stale() is False

    def test_materialized_view_to_dict(self):
        from src.data_pipeline.analytics_views import MaterializedView
        view = MaterializedView(view_name="v1", query={"table": "t"})
        d = view.to_dict()
        assert d["view_name"] == "v1"

    def test_view_manager_create_and_get(self):
        from src.data_pipeline.analytics_views import AnalyticsViewManager
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("vt", [WarehouseSchema("n", "int")])
        manager = AnalyticsViewManager(self.wh)
        view = manager.create_view("my_view", {"table": "vt"})
        assert view.view_name == "my_view"
        found = manager.get_view("my_view")
        assert found is not None

    def test_view_manager_refresh(self):
        from src.data_pipeline.analytics_views import AnalyticsViewManager
        from src.data_pipeline.pipeline_models import WarehouseSchema
        self.wh.create_table("rv", [WarehouseSchema("x", "int")])
        self.wh.load_data("rv", [{"x": 1}], "append")
        manager = AnalyticsViewManager(self.wh)
        manager.create_view("ref_view", {"table": "rv"})
        view = manager.refresh_view("ref_view")
        assert view.refreshed_at

    def test_view_manager_delete(self):
        from src.data_pipeline.analytics_views import AnalyticsViewManager
        manager = AnalyticsViewManager(self.wh)
        manager.create_view("del_view", {"table": "x"})
        result = manager.delete_view("del_view")
        assert result is True
        assert manager.get_view("del_view") is None

    def test_sales_fact_mart(self):
        from src.data_pipeline.analytics_views import SalesFactMart
        mart = SalesFactMart(self.wh)
        data = mart.build()
        assert len(data) > 0
        assert "date" in data[0]
        assert "revenue" in data[0]

    def test_customer_dimension_mart(self):
        from src.data_pipeline.analytics_views import CustomerDimensionMart
        mart = CustomerDimensionMart(self.wh)
        data = mart.build()
        assert len(data) > 0
        assert "customer_id" in data[0]
        assert "ltv" in data[0]

    def test_product_performance_mart(self):
        from src.data_pipeline.analytics_views import ProductPerformanceMart
        mart = ProductPerformanceMart(self.wh)
        data = mart.build()
        assert len(data) > 0
        assert "product_id" in data[0]
        assert "margin_rate" in data[0]

    def test_inventory_snapshot_mart(self):
        from src.data_pipeline.analytics_views import InventorySnapshotMart
        mart = InventorySnapshotMart(self.wh)
        data = mart.build()
        assert len(data) > 0
        assert "stock_level" in data[0]

    def test_vendor_performance_mart(self):
        from src.data_pipeline.analytics_views import VendorPerformanceMart
        mart = VendorPerformanceMart(self.wh)
        data = mart.build()
        assert len(data) > 0
        assert "vendor_id" in data[0]
        assert "commission" in data[0]


# ── TestPipelineMonitor ───────────────────────────────────────────────────

class TestPipelineMonitor:
    def test_record_and_get_metrics(self):
        from src.data_pipeline.pipeline_monitor import PipelineMonitor
        from src.data_pipeline.pipeline_models import RunRecord
        monitor = PipelineMonitor()
        record = RunRecord(
            run_id="r1", pipeline_id="p1", status="completed",
            started_at="2024-01-01T00:00:00", rows_processed=100,
        )
        monitor.record_run(record, duration_sec=5.0)
        metrics = monitor.get_metrics("p1")
        assert metrics["total_runs"] == 1
        assert metrics["success_rate"] == 1.0
        assert metrics["avg_rows"] == 100.0

    def test_metrics_empty(self):
        from src.data_pipeline.pipeline_monitor import PipelineMonitor
        monitor = PipelineMonitor()
        metrics = monitor.get_metrics("nonexistent")
        assert metrics["total_runs"] == 0

    def test_throughput(self):
        from src.data_pipeline.pipeline_monitor import PipelineMonitor
        from src.data_pipeline.pipeline_models import RunRecord
        monitor = PipelineMonitor()
        record = RunRecord("r1", "p1", "completed", "2024-01-01", rows_processed=100)
        monitor.record_run(record, duration_sec=10.0)
        tput = monitor.get_throughput("p1")
        assert tput == 10.0

    def test_error_rate(self):
        from src.data_pipeline.pipeline_monitor import PipelineMonitor
        from src.data_pipeline.pipeline_models import RunRecord
        monitor = PipelineMonitor()
        monitor.record_run(RunRecord("r1", "p1", "completed", "2024-01-01"), 1.0)
        monitor.record_run(RunRecord("r2", "p1", "failed", "2024-01-02"), 1.0)
        rate = monitor.get_error_rate("p1")
        assert rate == 0.5

    def test_lineage_tracker_record_and_get(self):
        from src.data_pipeline.pipeline_monitor import LineageTracker
        from src.data_pipeline.pipeline_models import ETLPipeline, PipelineStatus
        tracker = LineageTracker()
        pipeline = ETLPipeline(
            pipeline_id="p1", name="테스트", source="db_source",
            transforms=[{"type": "filter"}], destination="dw_output",
            created_at="2024-01-01",
        )
        tracker.record_lineage(pipeline)
        lineage = tracker.get_lineage("p1")
        assert lineage["pipeline_id"] == "p1"
        assert len(lineage["nodes"]) >= 2

    def test_lineage_tracker_get_table_lineage(self):
        from src.data_pipeline.pipeline_monitor import LineageTracker
        from src.data_pipeline.pipeline_models import ETLPipeline
        tracker = LineageTracker()
        pipeline = ETLPipeline(
            pipeline_id="p2", name="DW로더", source="events",
            transforms=[], destination="dw_orders",
            created_at="2024-01-01",
        )
        tracker.record_lineage(pipeline)
        result = tracker.get_table_lineage("dw_orders")
        assert len(result) > 0

    def test_etl_dashboard_summary(self):
        from src.data_pipeline.pipeline_monitor import PipelineMonitor, ETLDashboard
        from src.data_pipeline.etl_engine import ETLEngine
        from src.data_pipeline.data_warehouse import DataWarehouse
        engine = ETLEngine()
        wh = DataWarehouse()
        monitor = PipelineMonitor()
        dashboard = ETLDashboard(engine, wh, monitor)
        summary = dashboard.get_summary()
        assert "pipeline_count" in summary
        assert "warehouse_stats" in summary

    def test_etl_dashboard_pipeline_statuses(self):
        from src.data_pipeline.pipeline_monitor import PipelineMonitor, ETLDashboard
        from src.data_pipeline.etl_engine import ETLEngine
        from src.data_pipeline.data_warehouse import DataWarehouse
        engine = ETLEngine()
        engine.create_pipeline("P1", "s", [], "d")
        dashboard = ETLDashboard(engine, DataWarehouse(), PipelineMonitor())
        statuses = dashboard.get_pipeline_statuses()
        assert len(statuses) >= 1

    def test_etl_dashboard_recent_runs(self):
        from src.data_pipeline.pipeline_monitor import PipelineMonitor, ETLDashboard
        from src.data_pipeline.etl_engine import ETLEngine
        from src.data_pipeline.data_warehouse import DataWarehouse
        engine = ETLEngine()
        p = engine.create_pipeline("P1", "orders", [], "dw")
        engine.run_pipeline(p.pipeline_id)
        dashboard = ETLDashboard(engine, DataWarehouse(), PipelineMonitor())
        runs = dashboard.get_recent_runs(limit=5)
        assert isinstance(runs, list)


# ── TestDataPipelineAPI ───────────────────────────────────────────────────

class TestDataPipelineAPI:
    def setup_method(self):
        import importlib
        import src.api.data_pipeline_api as dp_api
        importlib.reload(dp_api)
        from flask import Flask
        self.app = Flask(__name__)
        self.app.register_blueprint(dp_api.data_pipeline_bp)
        self.client = self.app.test_client()

    def test_create_pipeline(self):
        resp = self.client.post(
            "/api/v1/data-pipeline/pipelines",
            json={"name": "API 파이프라인", "source": "internal_db", "destination": "dw_test"},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["name"] == "API 파이프라인"

    def test_list_pipelines(self):
        resp = self.client.get("/api/v1/data-pipeline/pipelines")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_get_pipeline(self):
        create_resp = self.client.post(
            "/api/v1/data-pipeline/pipelines",
            json={"name": "조회용", "source": "db", "destination": "dw"},
        )
        pid = create_resp.get_json()["pipeline_id"]
        resp = self.client.get(f"/api/v1/data-pipeline/pipelines/{pid}")
        assert resp.status_code == 200

    def test_get_pipeline_not_found(self):
        resp = self.client.get("/api/v1/data-pipeline/pipelines/nonexistent")
        assert resp.status_code == 404

    def test_update_pipeline(self):
        create_resp = self.client.post(
            "/api/v1/data-pipeline/pipelines",
            json={"name": "수정전", "source": "db", "destination": "dw"},
        )
        pid = create_resp.get_json()["pipeline_id"]
        resp = self.client.put(
            f"/api/v1/data-pipeline/pipelines/{pid}",
            json={"name": "수정후"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["name"] == "수정후"

    def test_delete_pipeline(self):
        create_resp = self.client.post(
            "/api/v1/data-pipeline/pipelines",
            json={"name": "삭제용", "source": "db", "destination": "dw"},
        )
        pid = create_resp.get_json()["pipeline_id"]
        resp = self.client.delete(f"/api/v1/data-pipeline/pipelines/{pid}")
        assert resp.status_code == 200

    def test_run_pipeline(self):
        create_resp = self.client.post(
            "/api/v1/data-pipeline/pipelines",
            json={"name": "실행용", "source": "orders", "destination": "dw_orders"},
        )
        pid = create_resp.get_json()["pipeline_id"]
        resp = self.client.post(f"/api/v1/data-pipeline/pipelines/{pid}/run")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "completed"

    def test_get_run_history(self):
        create_resp = self.client.post(
            "/api/v1/data-pipeline/pipelines",
            json={"name": "이력용", "source": "orders", "destination": "dw"},
        )
        pid = create_resp.get_json()["pipeline_id"]
        self.client.post(f"/api/v1/data-pipeline/pipelines/{pid}/run")
        resp = self.client.get(f"/api/v1/data-pipeline/pipelines/{pid}/history")
        assert resp.status_code == 200
        assert len(resp.get_json()) >= 1

    def test_list_sources(self):
        resp = self.client.get("/api/v1/data-pipeline/sources")
        assert resp.status_code == 200
        sources = resp.get_json()
        assert len(sources) >= 4

    def test_list_warehouse_tables(self):
        resp = self.client.get("/api/v1/data-pipeline/warehouse/tables")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    def test_warehouse_query(self):
        resp = self.client.post(
            "/api/v1/data-pipeline/warehouse/query",
            json={"table": "nonexistent"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "rows" in data

    def test_get_quality_reports(self):
        resp = self.client.get("/api/v1/data-pipeline/quality/reports")
        assert resp.status_code == 200

    def test_run_quality_check(self):
        resp = self.client.post(
            "/api/v1/data-pipeline/quality/check",
            json={"table": "", "threshold": 80.0},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "report" in data

    def test_list_views(self):
        resp = self.client.get("/api/v1/data-pipeline/views")
        assert resp.status_code == 200

    def test_refresh_view(self):
        resp = self.client.post("/api/v1/data-pipeline/views/test_view/refresh")
        assert resp.status_code == 200

    def test_get_dashboard(self):
        resp = self.client.get("/api/v1/data-pipeline/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "pipeline_count" in data

    def test_get_lineage(self):
        resp = self.client.get("/api/v1/data-pipeline/lineage/dw_orders")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "table_name" in data


# ── TestBotCommands ───────────────────────────────────────────────────────

class TestBotCommands:
    def test_cmd_etl_status(self):
        from src.bot.commands import cmd_etl_status
        result = cmd_etl_status()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_etl_run_no_id(self):
        from src.bot.commands import cmd_etl_run
        result = cmd_etl_run("")
        assert "사용법" in result or "error" in result.lower() or "실패" in result

    def test_cmd_etl_run_invalid_id(self):
        from src.bot.commands import cmd_etl_run
        result = cmd_etl_run("nonexistent_pipeline_id")
        assert isinstance(result, str)

    def test_cmd_warehouse_tables(self):
        from src.bot.commands import cmd_warehouse_tables
        result = cmd_warehouse_tables()
        assert isinstance(result, str)

    def test_cmd_data_quality(self):
        from src.bot.commands import cmd_data_quality
        result = cmd_data_quality()
        assert isinstance(result, str)
        assert "품질" in result or "quality" in result.lower() or "오류" in result.lower()

    def test_cmd_etl_dashboard(self):
        from src.bot.commands import cmd_etl_dashboard
        result = cmd_etl_dashboard()
        assert isinstance(result, str)
        assert len(result) > 0
