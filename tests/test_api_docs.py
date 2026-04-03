"""tests/test_api_docs.py — Phase 52: API 문서 생성 테스트."""
import pytest
from flask import Flask
from src.docs.endpoint_scanner import EndpointScanner
from src.docs.schema_builder import SchemaBuilder
from src.docs.api_doc_generator import APIDocGenerator
from src.docs.doc_renderer import DocRenderer


def _make_app():
    app = Flask(__name__)

    @app.get('/health')
    def health():
        return 'ok'

    @app.post('/api/v1/orders')
    def create_order():
        return 'ok'

    return app


class TestEndpointScanner:
    def setup_method(self):
        self.scanner = EndpointScanner()
        self.app = _make_app()

    def test_scan_returns_list(self):
        with self.app.app_context():
            endpoints = self.scanner.scan(self.app)
        assert isinstance(endpoints, list)
        assert len(endpoints) > 0

    def test_scan_has_required_fields(self):
        with self.app.app_context():
            endpoints = self.scanner.scan(self.app)
        for ep in endpoints:
            assert 'path' in ep
            assert 'methods' in ep
            assert 'endpoint' in ep

    def test_scan_finds_routes(self):
        with self.app.app_context():
            endpoints = self.scanner.scan(self.app)
        paths = [ep['path'] for ep in endpoints]
        assert '/health' in paths


class TestSchemaBuilder:
    def setup_method(self):
        self.builder = SchemaBuilder()

    def test_build_parameter_schema(self):
        schema = self.builder.build_parameter_schema('page', 'int', required=False)
        assert schema['name'] == 'page'
        assert schema['schema']['type'] == 'integer'

    def test_build_response_schema(self):
        schema = self.builder.build_response_schema(200, 'OK', {'id': '123'})
        assert '200' in schema
        assert schema['200']['description'] == 'OK'

    def test_build_request_schema(self):
        schema = self.builder.build_request_schema({'name': 'str', 'count': 'int'})
        props = schema['content']['application/json']['schema']['properties']
        assert props['name']['type'] == 'string'
        assert props['count']['type'] == 'integer'


class TestAPIDocGenerator:
    def setup_method(self):
        self.generator = APIDocGenerator()
        self.app = _make_app()

    def test_generate_returns_openapi(self):
        with self.app.app_context():
            spec = self.generator.generate(self.app)
        assert spec['openapi'] == '3.0.0'
        assert 'info' in spec
        assert 'paths' in spec

    def test_generate_includes_paths(self):
        with self.app.app_context():
            spec = self.generator.generate(self.app)
        assert '/health' in spec['paths']

    def test_generate_includes_methods(self):
        with self.app.app_context():
            spec = self.generator.generate(self.app)
        assert 'get' in spec['paths']['/health']


class TestDocRenderer:
    def setup_method(self):
        self.renderer = DocRenderer()

    def _make_spec(self):
        return {
            'openapi': '3.0.0',
            'info': {'title': 'Test API', 'description': 'Test'},
            'paths': {
                '/health': {'get': {'summary': 'Health check', 'tags': ['health'], 'responses': {'200': {'description': 'OK'}}}},
            },
        }

    def test_render_html_returns_string(self):
        html = self.renderer.render_html(self._make_spec())
        assert isinstance(html, str)
        assert '<html' in html

    def test_render_includes_title(self):
        html = self.renderer.render_html(self._make_spec())
        assert 'Test API' in html

    def test_render_includes_path(self):
        html = self.renderer.render_html(self._make_spec())
        assert '/health' in html

    def test_render_empty_paths(self):
        spec = {'openapi': '3.0.0', 'info': {'title': 'Empty'}, 'paths': {}}
        html = self.renderer.render_html(spec)
        assert '<html' in html
