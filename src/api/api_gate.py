"""Z10(오너 2026-10-07): `/api/` 단일 관문 — 키 또는 공유 사용자 세션 없이는 닫는다.

Z8 범위 밖 발견: 대시보드 API 바깥의 `/api/v1/*` 블루프린트 약 85개(email_marketing·returns·cs·users·
payments·security(ip 차단 POST)…)가 인증 없이 응답했다. 데코레이터를 85곳에 다는 대신 요청 앞에서 한 번 막는다.

통과 조건(하나라도):
- `X-API-Key` == `DASHBOARD_API_KEY`(Z8과 같은 키) · 공유 사용자 세션(관리자·FAMILY_EMAILS) · `dev_open()`(개발·테스트).
열어 두는 블루프린트(자기 인증이 있거나 공개가 맞는 것)만 `OPEN_BLUEPRINTS`.
키가 비었으면 503(닫힘, Z8과 같은 문구), 키가 있는데 안 맞으면 401.
"""
from __future__ import annotations

import hmac
import logging
import os

from flask import jsonify, request

logger = logging.getLogger(__name__)

# 자기 인증이 있거나(확장 = 개인 토큰) 공개가 맞는 것(헬스·문서)만.
OPEN_BLUEPRINTS = frozenset({
    "extension_api",   # /api/v1/collect/* — 개인 토큰(Bearer) 자체 검사
    "monitoring",      # /api/v1/health · /api/v1/metrics
    "api_docs",        # /api/docs — 엔드포인트 목록(데이터 없음)
})


def _key_ok(api_key: str) -> bool:
    provided = request.headers.get("X-API-Key", "")
    return bool(provided) and hmac.compare_digest(provided.encode(), api_key.encode())


def _shared_session() -> bool:
    try:
        from src.seller_console.market_pick import session_is_shared
        return bool(session_is_shared())
    except Exception:
        return False


def check():
    """before_request — 통과면 None, 막으면 (json, status)."""
    path = request.path or ""
    if not path.startswith("/api/") or request.method == "OPTIONS":
        return None
    if (request.blueprint or "") in OPEN_BLUEPRINTS:
        return None
    from .auth_middleware import dev_open
    if dev_open():
        return None
    api_key = os.getenv("DASHBOARD_API_KEY", "").strip()
    if api_key and _key_ok(api_key):
        return None
    if _shared_session():
        return None
    logger.warning("API 관문 차단: bp=%s path=%s ip=%s key_set=%s",
                   request.blueprint, path, request.remote_addr, bool(api_key))
    if not api_key:
        return jsonify({"error": "Service Unavailable",
                        "message": "DASHBOARD_API_KEY가 설정되지 않아 API를 닫아 두었습니다."}), 503
    return jsonify({"error": "Unauthorized", "message": "Invalid or missing API key"}), 401


def install(app) -> None:
    app.before_request(check)
