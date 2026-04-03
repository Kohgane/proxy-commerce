"""src/docs/endpoint_scanner.py — 등록된 라우트 수집."""
from __future__ import annotations

from typing import List


class EndpointScanner:
    """Flask 앱에서 등록된 모든 라우트, 메서드, 파라미터 수집."""

    def scan(self, app) -> List[dict]:
        """Flask 앱의 모든 라우트를 스캔하여 엔드포인트 목록 반환."""
        endpoints = []
        for rule in app.url_map.iter_rules():
            if rule.endpoint in ("static",):
                continue
            methods = sorted(m for m in rule.methods if m not in ("HEAD", "OPTIONS"))
            path_params = [
                {"name": p.strip("<>").split(":")[0], "in": "path", "required": True,
                 "schema": {"type": self._infer_type(p)}}
                for p in rule.rule.split("/")
                if p.startswith("<")
            ]
            endpoints.append({
                "path": rule.rule,
                "methods": methods,
                "endpoint": rule.endpoint,
                "parameters": path_params,
            })
        return endpoints

    def _infer_type(self, param_token: str) -> str:
        """파라미터 타입 추론."""
        # Flask param formats: <int:id>, <float:val>, <string:name>
        if "int:" in param_token:
            return "integer"
        if "float:" in param_token:
            return "number"
        return "string"
