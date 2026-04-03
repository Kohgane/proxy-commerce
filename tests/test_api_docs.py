"""tests/test_api_docs.py — API 문서 자동 생성 테스트 (Phase 52)."""
from __future__ import annotations

import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─────────────────────────────────────────────────────────────
# EndpointScanner
# ─────────────────────────────────────────────────────────────

class TestEndpointScanner:
    def setup_method(self):
        from src.docs.endpoint_scanner import EndpointScanner
        self.scanner = EndpointScanner()
        self.app = Flask(__name__)

        @self.app.get("/api/test")
        def test_endpoint():
            return "ok"

        @self.app.get("/api/items/<item_id>")
        def get_item(item_id):
            return item_id

    def test_scan_finds_routes(self):
        endpoints = self.scanner.scan(self.app)
        paths = [e["path"] for e in endpoints]
        assert "/api/test" in paths

    def test_scan_includes_methods(self):
        endpoints = self.scanner.scan(self.app)
        test_ep = next(e for e in endpoints if e["path"] == "/api/test")
        assert "GET" in test_ep["methods"]

    def test_scan_path_params(self):
        endpoints = self.scanner.scan(self.app)
        item_ep = next(e for e in endpoints if e["path"] == "/api/items/<item_id>")
        params = item_ep["parameters"]
        assert len(params) == 1
        assert params[0]["name"] == "item_id"
        assert params[0]["required"] is True

    def test_infer_type_string(self):
        assert self.scanner._infer_type("<name>") == "string"

    def test_infer_type_int(self):
        assert self.scanner._infer_type("<int:id>") == "integer"


# ─────────────────────────────────────────────────────────────
# SchemaBuilder
# ─────────────────────────────────────────────────────────────

class TestSchemaBuilder:
    def setup_method(self):
        from src.docs.schema_builder import SchemaBuilder
        self.builder = SchemaBuilder()

    def test_build_from_dict_string(self):
        schema = self.builder.build_from_dict({"name": "test"})
        assert schema["type"] == "object"
        assert schema["properties"]["name"]["type"] == "string"

    def test_build_from_dict_int(self):
        schema = self.builder.build_from_dict({"count": 5})
        assert schema["properties"]["count"]["type"] == "integer"

    def test_build_from_dict_float(self):
        schema = self.builder.build_from_dict({"price": 9.99})
        assert schema["properties"]["price"]["type"] == "number"

    def test_build_from_dict_bool(self):
        schema = self.builder.build_from_dict({"active": True})
        assert schema["properties"]["active"]["type"] == "boolean"

    def test_build_from_dict_list(self):
        schema = self.builder.build_from_dict({"items": [1, 2, 3]})
        assert schema["properties"]["items"]["type"] == "array"

    def test_error_schema(self):
        schema = self.builder.error_schema()
        assert "error" in str(schema)

    def test_response_schema(self):
        schema = self.builder.response_schema("OK", {"id": 1})
        assert schema["description"] == "OK"


# ─────────────────────────────────────────────────────────────
# APIDocGenerator
# ─────────────────────────────────────────────────────────────

class TestAPIDocGenerator:
    def setup_method(self):
        from src.docs.api_doc_generator import APIDocGenerator
        self.gen = APIDocGenerator(title="Test API", version="2.0.0")
        self.app = Flask(__name__)

        @self.app.get("/api/products")
        def list_products():
            return "ok"

    def test_generate_without_app(self):
        spec = self.gen.generate()
        assert spec["openapi"] == "3.0.0"
        assert spec["info"]["title"] == "Test API"
        assert spec["info"]["version"] == "2.0.0"

    def test_generate_with_app(self):
        spec = self.gen.generate(self.app)
        assert "paths" in spec
        assert "/api/products" in spec["paths"]

    def test_generate_operations(self):
        spec = self.gen.generate(self.app)
        ops = spec["paths"]["/api/products"]
        assert "get" in ops

    def test_add_path(self):
        self.gen.add_path("/custom", "post", summary="Custom endpoint")
        spec = self.gen.generate()
        assert "/custom" in spec["paths"]
        assert "post" in spec["paths"]["/custom"]


# ─────────────────────────────────────────────────────────────
# DocRenderer
# ─────────────────────────────────────────────────────────────

class TestDocRenderer:
    def setup_method(self):
        from src.docs.doc_renderer import DocRenderer
        from src.docs.api_doc_generator import APIDocGenerator
        self.renderer = DocRenderer()
        self.gen = APIDocGenerator(title="Proxy Commerce API", version="1.0.0")
        app = Flask(__name__)

        @app.get("/api/health")
        def health():
            return "ok"

        self.spec = self.gen.generate(app)

    def test_render_html_produces_html(self):
        html = self.renderer.render_html(self.spec)
        assert "<!DOCTYPE html>" in html
        assert "Proxy Commerce API" in html

    def test_render_html_includes_endpoints(self):
        html = self.renderer.render_html(self.spec)
        assert "/api/health" in html

    def test_render_json(self):
        import json
        json_str = self.renderer.render_json(self.spec)
        parsed = json.loads(json_str)
        assert parsed["openapi"] == "3.0.0"

    def test_render_html_empty_paths(self):
        empty_spec = {"openapi": "3.0.0", "info": {"title": "T", "version": "1.0.0"}, "paths": {}}
        html = self.renderer.render_html(empty_spec)
        assert "<!DOCTYPE html>" in html


# ─────────────────────────────────────────────────────────────
# API Docs Blueprint
# ─────────────────────────────────────────────────────────────

class TestAPIDocsBlueprint:
    def setup_method(self):
        from src.api.api_docs_api import api_docs_bp
        app = Flask(__name__)
        app.register_blueprint(api_docs_bp)
        self.client = app.test_client()

    def test_get_html(self):
        resp = self.client.get("/api/docs/")
        assert resp.status_code == 200
        assert b"<!DOCTYPE html>" in resp.data

    def test_get_openapi_json(self):
        resp = self.client.get("/api/docs/openapi.json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["openapi"] == "3.0.0"
        assert "info" in data
        assert "paths" in data
