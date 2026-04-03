"""src/docs/doc_renderer.py — OpenAPI JSON → HTML 문서 렌더링."""
from __future__ import annotations

import json

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       margin: 0; padding: 20px; background: #f8f9fa; color: #333; }}
h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
h2 {{ color: #34495e; margin-top: 30px; }}
.path {{ background: #fff; border: 1px solid #ddd; border-radius: 8px;
         margin: 10px 0; padding: 15px; }}
.method {{ display: inline-block; padding: 3px 10px; border-radius: 4px;
           font-weight: bold; font-size: 12px; color: #fff; margin-right: 8px; }}
.get {{ background: #61affe; }} .post {{ background: #49cc90; }}
.put {{ background: #fca130; }} .delete {{ background: #f93e3e; }}
.endpoint {{ font-family: monospace; font-size: 14px; }}
pre {{ background: #f4f4f4; padding: 10px; border-radius: 4px;
      font-size: 12px; overflow-x: auto; }}
</style>
</head>
<body>
<h1>🛒 {title}</h1>
<p><strong>버전:</strong> {version}</p>
<p>{description}</p>
<h2>API 엔드포인트</h2>
{paths_html}
<hr>
<p><small>OpenAPI 3.0 스펙: <a href="/api/docs/openapi.json">/api/docs/openapi.json</a></small></p>
</body>
</html>"""

_METHOD_COLORS = {"get": "get", "post": "post", "put": "put",
                  "patch": "put", "delete": "delete"}


class DocRenderer:
    """OpenAPI JSON → HTML 문서 렌더링 (내장 템플릿)."""

    def render_html(self, spec: dict) -> str:
        """OpenAPI spec dict → HTML 문서."""
        info = spec.get("info", {})
        title = info.get("title", "API Docs")
        version = info.get("version", "1.0.0")
        description = info.get("description", "")

        paths_html_parts = []
        for path, operations in spec.get("paths", {}).items():
            for method, operation in operations.items():
                color = _METHOD_COLORS.get(method, "get")
                summary = operation.get("summary", "")
                op_id = operation.get("operationId", "")
                paths_html_parts.append(
                    f'<div class="path">'
                    f'<span class="method {color}">{method.upper()}</span>'
                    f'<span class="endpoint">{path}</span>'
                    + (f" — {summary}" if summary else "")
                    + f"</div>"
                )

        paths_html = "\n".join(paths_html_parts) if paths_html_parts else "<p>등록된 엔드포인트 없음</p>"
        return _HTML_TEMPLATE.format(
            title=title, version=version, description=description,
            paths_html=paths_html,
        )

    def render_json(self, spec: dict) -> str:
        """OpenAPI spec dict → JSON 문자열."""
        return json.dumps(spec, ensure_ascii=False, indent=2)
