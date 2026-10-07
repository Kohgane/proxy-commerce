"""src/api/auth_middleware.py — API 인증 미들웨어.

X-API-Key 헤더를 검증하는 데코레이터와 도우미 함수를 제공한다.

환경변수:
  DASHBOARD_API_KEY   — API 인증 키. **비어 있으면 닫는다**(fail-closed, Z8 2026-10-07 — 예전엔 인증을 건너뛰어
                        비로그인 외부인도 오너 주문·매출·CRM을 읽을 수 있었다).
  DASHBOARD_API_OPEN  — 개발·테스트에서만: 1이면 키 없이 연다. `APP_ENV=production`이면 이 값은 무시한다.
"""

import functools
import logging
import os

from flask import request, jsonify

from ..audit.audit_logger import AuditLogger
from ..audit.event_types import EventType

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("DASHBOARD_API_KEY", "")

_audit = AuditLogger()


def dev_open() -> bool:
    """개발·테스트에서만 키 없이 연다(`DASHBOARD_API_OPEN=1`). 운영(`APP_ENV=production`)에선 늘 False."""
    if os.getenv("APP_ENV", "").strip().lower() == "production":
        return False
    return os.getenv("DASHBOARD_API_OPEN", "").strip().lower() in ("1", "true", "yes", "on")


def require_api_key(func):
    """API 키 인증을 요구하는 데코레이터.

    X-API-Key 헤더를 검증한다. DASHBOARD_API_KEY 환경변수가
    설정되지 않으면 인증을 건너뛴다 (개발 환경용).

    인증 성공 시 감사 로그 기록.
    인증 실패 시 401 응답 반환.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        api_key = os.getenv("DASHBOARD_API_KEY", "").strip()
        if not api_key and not dev_open():
            # Z8: 키가 비었으면 닫는다 — 「설정 안 함 = 누구나」가 되면 안 된다(운영 env 누락 한 번이 곧 유출).
            logger.warning("대시보드 API 닫힘(DASHBOARD_API_KEY 미설정): endpoint=%s ip=%s", request.path, request.remote_addr)
            return jsonify({"error": "Service Unavailable",
                            "message": "DASHBOARD_API_KEY가 설정되지 않아 API를 닫아 두었습니다."}), 503
        if api_key:
            provided = request.headers.get("X-API-Key", "")
            if not provided or provided != api_key:
                logger.warning("대시보드 API 인증 실패: endpoint=%s ip=%s", request.path, request.remote_addr)
                _audit.log(
                    EventType.LOGIN_FAILURE,
                    actor="api_client",
                    resource=f"api:{request.path}",
                    details={"reason": "invalid_api_key"},
                    ip_address=request.remote_addr or "",
                )
                return jsonify({"error": "Unauthorized", "message": "Invalid or missing API key"}), 401

        _audit.log(
            EventType.LOGIN_SUCCESS,
            actor="api_client",
            resource=f"api:{request.path}",
            ip_address=request.remote_addr or "",
        )
        return func(*args, **kwargs)
    return wrapper
