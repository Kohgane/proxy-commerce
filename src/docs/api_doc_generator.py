"""src/docs/api_doc_generator.py — OpenAPI 3.0 스펙 자동 생성."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .endpoint_scanner import EndpointScanner
from .schema_builder import SchemaBuilder


class APIDocGenerator:
    """Flask Blueprint들을 스캔하여 OpenAPI 3.0 스펙 자동 생성."""

    def __init__(self,
                 title: str = "Proxy Commerce API",
                 version: str = "1.0.0",
                 description: str = "") -> None:
        self.title = title
        self.version = version
        self.description = description
        self.scanner = EndpointScanner()
        self.schema_builder = SchemaBuilder()
        self._extra_paths: Dict[str, Any] = {}

    def generate(self, app=None) -> dict:
        """OpenAPI 3.0 스펙 dict 생성."""
        spec: dict = {
            "openapi": "3.0.0",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": self.description,
            },
            "paths": {},
        }

        if app is not None:
            endpoints = self.scanner.scan(app)
            for ep in endpoints:
                path = ep["path"]
                if path not in spec["paths"]:
                    spec["paths"][path] = {}
                for method in ep.get("methods", []):
                    spec["paths"][path][method.lower()] = {
                        "operationId": f"{ep['endpoint']}_{method.lower()}",
                        "parameters": ep.get("parameters", []),
                        "responses": {
                            "200": {"description": "성공"},
                            "400": {"description": "잘못된 요청"},
                            "404": {"description": "리소스 없음"},
                            "500": {"description": "서버 오류"},
                        },
                    }

        # 수동 추가 경로 병합
        for path, operations in self._extra_paths.items():
            if path not in spec["paths"]:
                spec["paths"][path] = {}
            spec["paths"][path].update(operations)

        return spec

    def add_path(self, path: str, method: str, summary: str = "",
                 request_body: dict = None, responses: dict = None) -> None:
        """수동으로 경로 추가."""
        if path not in self._extra_paths:
            self._extra_paths[path] = {}
        self._extra_paths[path][method.lower()] = {
            "summary": summary,
            "requestBody": request_body or {},
            "responses": responses or {"200": {"description": "성공"}},
        }
