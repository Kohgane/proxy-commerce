"""tests/test_data_exchange.py — Phase 68 데이터 교환 테스트."""
from __future__ import annotations

import json
import pytest
from src.data_exchange.export_manager import ExportManager
from src.data_exchange.import_manager import ImportManager
from src.data_exchange.data_transformer import DataTransformer
from src.data_exchange.export_template import ExportTemplate
from src.data_exchange.import_validator import ImportValidator
from src.data_exchange.bulk_operation import BulkOperation


class TestExportManager:
    def test_export_json(self):
        mgr = ExportManager()
        data = [{"id": 1, "name": "A"}]
        result = mgr.export(data, format_="json")
        assert result["format"] == "json"
        assert result["records"] == 1
        assert "content" in result
        assert json.loads(result["content"]) == data

    def test_export_csv(self):
        mgr = ExportManager()
        data = [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]
        result = mgr.export(data, format_="csv")
        assert result["format"] == "csv"
        assert result["records"] == 2

    def test_export_empty(self):
        mgr = ExportManager()
        result = mgr.export([], format_="json")
        assert result["records"] == 0

    def test_export_has_exported_at(self):
        mgr = ExportManager()
        result = mgr.export([], format_="json")
        assert "exported_at" in result


class TestImportManager:
    def test_import_json(self):
        mgr = ImportManager()
        content = json.dumps([{"id": 1}, {"id": 2}])
        result = mgr.import_data(content, format_="json")
        assert result["records_valid"] == 2
        assert result["records_invalid"] == 0

    def test_import_csv(self):
        mgr = ImportManager()
        content = "id,name\n1,A\n2,B"
        result = mgr.import_data(content, format_="csv")
        assert result["records_valid"] == 2

    def test_import_invalid_json(self):
        mgr = ImportManager()
        result = mgr.import_data("not-json", format_="json")
        assert result["records_invalid"] > 0 or result["errors"]

    def test_import_unsupported_format(self):
        mgr = ImportManager()
        result = mgr.import_data("data", format_="xml")
        assert result["errors"]


class TestDataTransformer:
    def test_transform_no_ops(self):
        dt = DataTransformer()
        data = [{"a": 1}, {"a": 2}]
        result = dt.transform(data)
        assert result == data

    def test_transform_mapping(self):
        dt = DataTransformer()
        data = [{"old_key": "val"}]
        result = dt.transform(data, mapping={"old_key": "new_key"})
        assert result[0]["new_key"] == "val"

    def test_transform_filter_eq(self):
        dt = DataTransformer()
        data = [{"status": "active"}, {"status": "inactive"}]
        result = dt.transform(data, filters=[{"field": "status", "op": "eq", "value": "active"}])
        assert len(result) == 1

    def test_transform_filter_gt(self):
        dt = DataTransformer()
        data = [{"score": 5}, {"score": 8}, {"score": 3}]
        result = dt.transform(data, filters=[{"field": "score", "op": "gt", "value": 6}])
        assert len(result) == 1
        assert result[0]["score"] == 8


class TestExportTemplate:
    def test_create(self):
        tmpl = ExportTemplate()
        result = tmpl.create("test", ["id", "name"])
        assert result["name"] == "test"
        assert "template_id" in result

    def test_get(self):
        tmpl = ExportTemplate()
        created = tmpl.create("t", ["id"])
        fetched = tmpl.get(created["template_id"])
        assert fetched["name"] == "t"

    def test_get_nonexistent(self):
        tmpl = ExportTemplate()
        assert tmpl.get("nonexistent") == {}

    def test_list_templates(self):
        tmpl = ExportTemplate()
        tmpl.create("t1", ["id"])
        tmpl.create("t2", ["name"])
        assert len(tmpl.list_templates()) == 2


class TestImportValidator:
    def test_validate_all_valid(self):
        v = ImportValidator()
        data = [{"id": 1, "name": "A"}]
        schema = {"required": ["id", "name"]}
        result = v.validate(data, schema)
        assert len(result["valid"]) == 1
        assert len(result["invalid"]) == 0

    def test_validate_missing_required(self):
        v = ImportValidator()
        data = [{"id": 1}]
        schema = {"required": ["id", "name"]}
        result = v.validate(data, schema)
        assert len(result["invalid"]) == 1

    def test_validate_no_schema(self):
        v = ImportValidator()
        data = [{"a": 1}, {"b": 2}]
        result = v.validate(data)
        assert len(result["valid"]) == 2


class TestBulkOperation:
    def test_start(self):
        bulk = BulkOperation()
        job = bulk.start("import", 100)
        assert job["status"] == "running"
        assert job["total_records"] == 100

    def test_update_progress(self):
        bulk = BulkOperation()
        job = bulk.start("import", 10)
        result = bulk.update_progress(job["job_id"], 5)
        assert result is True
        status = bulk.get_status(job["job_id"])
        assert status["processed"] == 5

    def test_update_progress_complete(self):
        bulk = BulkOperation()
        job = bulk.start("import", 5)
        bulk.update_progress(job["job_id"], 5)
        status = bulk.get_status(job["job_id"])
        assert status["status"] == "completed"

    def test_get_status_not_found(self):
        bulk = BulkOperation()
        assert bulk.get_status("nonexistent") == {}

    def test_list_jobs(self):
        bulk = BulkOperation()
        bulk.start("import", 10)
        bulk.start("export", 20)
        assert len(bulk.list_jobs()) == 2
