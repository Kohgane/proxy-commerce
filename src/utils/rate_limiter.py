"""src/utils/rate_limiter.py — Flask-Limiter 기반 Rate Limiting 미들웨어.

웹훅 및 헬스체크 엔드포인트에 대한 요청 속도 제한을 적용한다.

기본 제한:
  - 웹훅 엔드포인트 (/webhook/*)    : 분당 60회
  - 헬스체크 엔드포인트 (/health/*) : 분당 120회

환경변수:
  RATE_LIMIT_WEBHOOK  — 웹훅 제한 (기본 "60 per minute")
  RATE_LIMIT_HEALTH   — 헬스체크 제한 (기본 "120 per minute")
  RATE_LIMIT_ENABLED  — 활성화 여부 (기본 "1", "0"이면 비활성화)
"""

import logging
import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logger = logging.getLogger(__name__)


def _get_limit_webhook() -> str:
    """웹훅 요청 제한값을 환경변수에서 읽는다."""
    return os.getenv('RATE_LIMIT_WEBHOOK', '60 per minute')


def _get_limit_health() -> str:
    """헬스체크 요청 제한값을 환경변수에서 읽는다."""
    return os.getenv('RATE_LIMIT_HEALTH', '120 per minute')


def create_limiter(app=None) -> Limiter:
    """Flask-Limiter 인스턴스를 생성하고 앱에 바인딩한다.

    Args:
        app: Flask 앱 인스턴스. None이면 init_app() 호출 필요.

    Returns:
        Limiter 인스턴스.
    """
    enabled = os.getenv('RATE_LIMIT_ENABLED', '1') == '1'
    if not enabled:
        logger.info("Rate limiting disabled (RATE_LIMIT_ENABLED=0)")

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[] if not enabled else ['200 per minute'],
        storage_uri='memory://',
        app=app,
    )
    return limiter


# ──────────────────────────────────────────────────────────
# 제한값 상수 (데코레이터에서 사용)
# ──────────────────────────────────────────────────────────

LIMIT_WEBHOOK = _get_limit_webhook
LIMIT_HEALTH = _get_limit_health
