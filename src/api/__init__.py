"""src/api/ — 관리자 대시보드 REST API 패키지.

Flask Blueprint 기반의 관리자 대시보드 API.

환경변수:
  DASHBOARD_API_ENABLED  — API 활성화 여부 (기본 "1")
  DASHBOARD_API_KEY      — API 인증 키
"""

from .dashboard_routes import dashboard_bp
from .auth_middleware import require_api_key
from .reviews_api import reviews_bp
from .promotions_api import promotions_bp
from .crm_api import crm_bp
from .marketing_api import marketing_bp
from .reports_api import reports_bp
from .seo_api import seo_bp

__all__ = [
    "dashboard_bp", "require_api_key", "reviews_bp", "promotions_bp", "crm_bp",
    "marketing_bp", "reports_bp", "seo_bp",
]
