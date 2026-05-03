"""src/middleware/security.py — 보안 미들웨어.

Flask 앱에 다음 보안 기능을 추가한다:
  - Security 헤더 (X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, HSTS)
  - CORS 강화 (CORS_ALLOWED_ORIGINS 환경변수)
  - 요청 크기 제한 (MAX_CONTENT_LENGTH)
  - JSON 페이로드 기본 검증

환경변수:
  CORS_ALLOWED_ORIGINS  — 허용 오리진 쉼표 구분 (기본 "*")
  MAX_CONTENT_LENGTH    — 최대 요청 본문 크기 bytes (기본 1048576 = 1MB)
  SECURITY_HSTS_ENABLED — HSTS 헤더 활성화 여부 (기본 "0", HTTPS 환경에서만 "1")

CSP 정책 (경로별 분기):
  HTML 페이지 (/admin/*, /seller/*, /api/docs, /):
      cdn.jsdelivr.net Bootstrap CDN 허용, unsafe-inline 허용
  API/웹훅 응답 (/api/v1/*, /api/dashboard, /webhook/*, /health/*):
      default-src 'none' — strict CSP
"""

import logging
import os

logger = logging.getLogger(__name__)

_MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(1 * 1024 * 1024)))  # 1MB
_HSTS_ENABLED = os.getenv("SECURITY_HSTS_ENABLED", "0") == "1"
_HSTS_MAX_AGE = int(os.getenv("SECURITY_HSTS_MAX_AGE", "31536000"))  # 1년

# HTML 페이지용 CSP — Bootstrap CDN 및 인라인 스타일/스크립트 허용
_CSP_HTML_PAGES = (
    "default-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "font-src 'self' https://cdn.jsdelivr.net data:; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'"
)

# API/웹훅 응답용 CSP — strict (리소스 로드 불필요)
_CSP_API = (
    "default-src 'none'; "
    "frame-ancestors 'none'"
)

# API 경로 prefix (이 prefix로 시작하면 strict CSP 적용)
# 각 prefix는 trailing slash 포함 — "/healthy" 같은 의도치 않은 매칭 방지
_API_PREFIXES = ("/api/v1/", "/api/dashboard/", "/webhook/", "/health/")
# 단, /api/docs 는 HTML 페이지이므로 제외
_API_DOCS_PREFIX = "/api/docs"


class SecurityMiddleware:
    """Flask 앱에 보안 헤더 및 요청 검증을 적용하는 미들웨어.

    사용 예:
        sec = SecurityMiddleware()
        sec.init_app(app)
    """

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app) -> None:
        """Flask 앱에 보안 설정과 after_request 훅을 등록한다."""
        # 요청 크기 제한
        app.config.setdefault("MAX_CONTENT_LENGTH", _MAX_CONTENT_LENGTH)

        # after_request 훅 — 보안 헤더 추가
        app.after_request(self._add_security_headers)

        # before_request 훅 — Content-Type 검증
        app.before_request(self._validate_request)

        logger.debug(
            "보안 미들웨어 초기화 완료: MAX_CONTENT_LENGTH=%d, HSTS=%s",
            _MAX_CONTENT_LENGTH,
            _HSTS_ENABLED,
        )

    def _add_security_headers(self, response):
        """응답에 보안 헤더를 추가한다.

        경로별 CSP 분기:
          - HTML 페이지 (/admin/*, /seller/*, /api/docs 등): CDN 허용 정책
          - API/웹훅 응답 (/api/v1/*, /webhook/*, /health/*): strict 정책
        """
        from flask import request
        path = request.path

        # /api/docs 는 HTML 문서이므로 먼저 확인 → HTML 정책 적용
        if path.startswith(_API_DOCS_PREFIX):
            csp = _CSP_HTML_PAGES
        elif path.startswith(_API_PREFIXES):
            csp = _CSP_API
        else:
            csp = _CSP_HTML_PAGES

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", csp)
        if _HSTS_ENABLED:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={_HSTS_MAX_AGE}; includeSubDomains",
            )
        return response

    def _validate_request(self):
        """POST/PUT/PATCH 요청의 Content-Type을 검증한다."""
        from flask import request, jsonify
        if request.method in ("POST", "PUT", "PATCH") and request.content_length:
            ct = request.content_type or ""
            # JSON 또는 form-data 허용
            if not (
                "application/json" in ct
                or "application/x-www-form-urlencoded" in ct
                or "multipart/form-data" in ct
                or "text/plain" in ct
            ):
                logger.warning(
                    "잘못된 Content-Type: %s path=%s", ct, request.path
                )
                return jsonify({"error": "Unsupported Media Type"}), 415
        return None
