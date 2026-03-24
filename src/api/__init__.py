"""src/api/ — 관리자 대시보드 REST API 패키지.

Flask Blueprint 기반의 관리자 대시보드 API.

환경변수:
  DASHBOARD_API_ENABLED  — API 활성화 여부 (기본 "1")
  DASHBOARD_API_KEY      — API 인증 키
"""

from .dashboard_routes import dashboard_bp
from .auth_middleware import require_api_key

__all__ = ["dashboard_bp", "require_api_key"]
