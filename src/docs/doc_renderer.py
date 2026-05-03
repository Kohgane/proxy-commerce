"""src/docs/doc_renderer.py — OpenAPI JSON → HTML 문서 렌더링 (Phase 123 개선)."""
from __future__ import annotations

import html
import json
from collections import defaultdict

# 메서드별 배지 색상
_METHOD_BADGE = {
    "get":    "badge-get",
    "post":   "badge-post",
    "put":    "badge-put",
    "patch":  "badge-patch",
    "delete": "badge-delete",
}

# path prefix → 그룹명 매핑 (순서 중요 — 구체적인 것 먼저)
_PREFIX_GROUPS = [
    ("/api/v1/payments",    "💳 결제"),
    ("/api/v1/cs",          "🎧 고객서비스"),
    ("/api/v1/products",    "📦 상품"),
    ("/api/v1/orders",      "🛒 주문"),
    ("/api/v1/inventory",   "📋 재고"),
    ("/api/v1/shipping",    "🚚 배송"),
    ("/api/v1/pricing",     "💰 가격"),
    ("/api/v1/analytics",   "📊 분석"),
    ("/api/v1/tenants",     "🏢 테넌트"),
    ("/api/v1/auth",        "🔑 인증"),
    ("/api/v1",             "🔌 API v1"),
    ("/api/docs",           "📚 문서"),
    ("/api/dashboard",      "🖥 대시보드 API"),
    ("/admin",              "🛠 관리자"),
    ("/seller",             "🛒 셀러"),
    ("/webhook",            "🔔 웹훅"),
    ("/health",             "💚 헬스체크"),
]


def _group_for(path: str) -> str:
    for prefix, name in _PREFIX_GROUPS:
        if path.startswith(prefix):
            return name
    return "🗂 기타"


class DocRenderer:
    """OpenAPI JSON → HTML 문서 렌더링 (Bootstrap 5 + 검색 + 그룹 accordion)."""

    def render_html(self, spec: dict) -> str:
        """OpenAPI spec dict → HTML 문서."""
        info = spec.get("info", {})
        title = html.escape(info.get("title", "API Docs"))
        version = html.escape(info.get("version", "1.0.0"))
        description = html.escape(info.get("description", ""))

        # 엔드포인트를 그룹별로 분류
        groups: dict[str, list] = defaultdict(list)
        for path, operations in spec.get("paths", {}).items():
            for method, operation in operations.items():
                group = _group_for(path)
                summary = html.escape(operation.get("summary", ""))
                groups[group].append({
                    "method": method.upper(),
                    "path": path,
                    "summary": summary,
                    "badge": _METHOD_BADGE.get(method.lower(), "badge-get"),
                })

        # 그룹별 accordion 빌드
        accordion_parts = []
        for idx, (group_name, endpoints) in enumerate(sorted(groups.items())):
            group_id = f"group-{idx}"
            rows = []
            for ep in sorted(endpoints, key=lambda e: e["path"]):
                rows.append(
                    f'<div class="d-flex align-items-start py-1 border-bottom endpoint-row" '
                    f'data-method="{ep["method"]}" data-path="{html.escape(ep["path"])}">'
                    f'<span class="badge {ep["badge"]} me-2 mt-1 method-badge" '
                    f'style="min-width:56px;font-size:.7rem;">{ep["method"]}</span>'
                    f'<div>'
                    f'<code class="endpoint-path text-dark">{html.escape(ep["path"])}</code>'
                    + (f'<br><small class="text-muted">{ep["summary"]}</small>' if ep["summary"] else "")
                    + '</div></div>'
                )
            rows_html = "\n".join(rows) if rows else '<p class="text-muted small">엔드포인트 없음</p>'
            count = len(endpoints)
            accordion_parts.append(f"""
            <div class="accordion-item">
              <h2 class="accordion-header" id="heading-{group_id}">
                <button class="accordion-button collapsed" type="button"
                        data-bs-toggle="collapse" data-bs-target="#collapse-{group_id}"
                        aria-expanded="false" aria-controls="collapse-{group_id}">
                  {html.escape(group_name)}
                  <span class="badge bg-secondary ms-2">{count}</span>
                </button>
              </h2>
              <div id="collapse-{group_id}" class="accordion-collapse collapse"
                   aria-labelledby="heading-{group_id}">
                <div class="accordion-body p-2">
                  {rows_html}
                </div>
              </div>
            </div>""")

        accordion_html = "\n".join(accordion_parts) if accordion_parts else '<p class="text-muted">등록된 엔드포인트 없음</p>'
        total = sum(len(v) for v in groups.values())

        return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — API 문서</title>
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css">
  <style>
    body {{ background:#f5f7fa; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    .endpoint-path {{ font-family: 'JetBrains Mono','Fira Code',monospace; font-size:.85rem; }}
    .badge-get    {{ background:#22c55e; color:#fff; }}
    .badge-post   {{ background:#3b82f6; color:#fff; }}
    .badge-put    {{ background:#f97316; color:#fff; }}
    .badge-patch  {{ background:#a855f7; color:#fff; }}
    .badge-delete {{ background:#ef4444; color:#fff; }}
    .endpoint-row {{ transition: background .1s; }}
    .endpoint-row:hover {{ background: #f0f9ff; }}
    .accordion-button:not(.collapsed) {{ background:#e0f2fe; color:#0369a1; }}
    #search-input:focus {{ border-color:#0d9488; box-shadow: 0 0 0 .2rem rgba(13,148,136,.25); }}
    .hidden {{ display: none !important; }}
  </style>
</head>
<body>
<nav class="navbar navbar-dark bg-dark">
  <div class="container-fluid">
    <a class="navbar-brand fw-bold" href="/">
      <i class="bi bi-bag-check-fill text-success me-1"></i> Proxy Commerce
    </a>
    <div class="d-flex gap-2">
      <a href="/" class="btn btn-sm btn-outline-light">🏠 홈</a>
      <a href="/api/docs/openapi.json" class="btn btn-sm btn-outline-light">
        <i class="bi bi-filetype-json"></i> OpenAPI JSON
      </a>
    </div>
  </div>
</nav>

<div class="container-fluid py-4" style="max-width:960px;">
  <div class="mb-4">
    <h1 class="h3 fw-bold mb-1">
      <i class="bi bi-book-half text-primary me-2"></i>{title}
    </h1>
    <p class="text-muted mb-0">버전: {version} &nbsp;·&nbsp; {description}
      &nbsp;·&nbsp; <span class="text-primary fw-semibold">{total}개</span> 엔드포인트
    </p>
  </div>

  <!-- 검색 + 메서드 필터 -->
  <div class="card shadow-sm mb-4">
    <div class="card-body py-3">
      <div class="row g-2 align-items-center">
        <div class="col-md-6">
          <div class="input-group">
            <span class="input-group-text"><i class="bi bi-search"></i></span>
            <input id="search-input" type="text" class="form-control"
                   placeholder="경로 또는 설명 검색…" autocomplete="off">
          </div>
        </div>
        <div class="col-md-6">
          <div class="d-flex flex-wrap gap-2 align-items-center">
            <small class="text-muted me-1">메서드:</small>
            {"".join(f'<div class="form-check form-check-inline mb-0"><input class="form-check-input method-filter" type="checkbox" id="chk-{m}" value="{m}" checked><label class="form-check-label badge badge-{m.lower()} px-2" for="chk-{m}">{m}</label></div>' for m in ["GET","POST","PUT","PATCH","DELETE"])}
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 그룹별 accordion -->
  <div class="accordion api-accordion shadow-sm" id="apiAccordion">
    {accordion_html}
  </div>

  <hr class="mt-5">
  <p class="text-center text-muted small">
    Phase 123 &nbsp;·&nbsp;
    <a href="/api/docs/openapi.json" class="text-muted">openapi.json</a>
  </p>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
<script src="/static/api_docs.js"></script>
</body>
</html>"""

    def render_json(self, spec: dict) -> str:
        """OpenAPI spec dict → JSON 문자열."""
        return json.dumps(spec, ensure_ascii=False, indent=2)

