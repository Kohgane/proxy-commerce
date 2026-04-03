"""src/docs/endpoint_scanner.py — Flask 엔드포인트 스캐너."""
import logging
from typing import List

logger = logging.getLogger(__name__)


class EndpointScanner:
    """Flask URL map에서 엔드포인트 목록 추출."""

    def scan(self, app) -> List[dict]:
        endpoints = []
        for rule in app.url_map.iter_rules():
            methods = sorted(rule.methods - {'HEAD', 'OPTIONS'})
            blueprint = rule.endpoint.split('.')[0] if '.' in rule.endpoint else None
            endpoints.append({
                'path': str(rule.rule),
                'methods': methods,
                'endpoint': rule.endpoint,
                'blueprint': blueprint,
            })
        return endpoints
