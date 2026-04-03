"""src/docs/api_doc_generator.py — OpenAPI 3.0 문서 생성."""
import logging

logger = logging.getLogger(__name__)


class APIDocGenerator:
    """OpenAPI 3.0 스펙 생성."""

    def generate(self, app) -> dict:
        from .endpoint_scanner import EndpointScanner
        scanner = EndpointScanner()
        endpoints = scanner.scan(app)
        paths = {}
        for ep in endpoints:
            path = ep['path']
            if path not in paths:
                paths[path] = {}
            for method in ep['methods']:
                paths[path][method.lower()] = {
                    'summary': ep['endpoint'],
                    'tags': [ep['blueprint']] if ep['blueprint'] else ['default'],
                    'responses': {
                        '200': {'description': 'Success'},
                    },
                }
        return {
            'openapi': '3.0.0',
            'info': {
                'title': 'Proxy Commerce API',
                'version': '1.0.0',
                'description': 'Proxy Commerce 플랫폼 REST API',
            },
            'paths': paths,
        }
