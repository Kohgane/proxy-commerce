"""src/api/auth_middleware.py — API 인증 미들웨어.

X-API-Key 헤더를 검증하는 데코레이터와 도우미 함수를 제공한다.

환경변수:
  DASHBOARD_API_KEY  — API 인증 키 (미설정 시 인증 비활성화)
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


def require_api_key(func):
    """API 키 인증을 요구하는 데코레이터.

    X-API-Key 헤더를 검증한다. DASHBOARD_API_KEY 환경변수가
    설정되지 않으면 인증을 건너뛴다 (개발 환경용).

    인증 성공 시 감사 로그 기록.
    인증 실패 시 401 응답 반환.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        api_key = os.getenv("DASHBOARD_API_KEY", "")
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
