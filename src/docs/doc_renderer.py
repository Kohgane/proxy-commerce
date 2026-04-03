"""src/docs/doc_renderer.py — HTML 문서 렌더러."""
import logging

logger = logging.getLogger(__name__)

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 20px; background: #f9f9f9; }}
h1 {{ color: #333; }}
table {{ border-collapse: collapse; width: 100%; background: white; }}
th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
th {{ background: #4a90d9; color: white; }}
tr:nth-child(even) {{ background: #f2f2f2; }}
.method-GET {{ color: #2196F3; font-weight: bold; }}
.method-POST {{ color: #4CAF50; font-weight: bold; }}
.method-PUT {{ color: #FF9800; font-weight: bold; }}
.method-DELETE {{ color: #f44336; font-weight: bold; }}
</style>
</head>
<body>
<h1>{title}</h1>
<p>{description}</p>
<table>
<tr><th>Method</th><th>Path</th><th>Summary</th><th>Tags</th></tr>
{rows}
</table>
</body>
</html>"""


class DocRenderer:
    """OpenAPI 스펙을 HTML로 렌더링."""

    def render_html(self, openapi_spec: dict) -> str:
        info = openapi_spec.get('info', {})
        title = info.get('title', 'API Documentation')
        description = info.get('description', '')
        rows = []
        for path, methods in openapi_spec.get('paths', {}).items():
            for method, details in methods.items():
                summary = details.get('summary', '')
                tags = ', '.join(details.get('tags', []))
                m = method.upper()
                rows.append(
                    f'<tr>'
                    f'<td class="method-{m}">{m}</td>'
                    f'<td>{path}</td>'
                    f'<td>{summary}</td>'
                    f'<td>{tags}</td>'
                    f'</tr>'
                )
        return _HTML_TEMPLATE.format(
            title=title,
            description=description,
            rows='\n'.join(rows),
        )
