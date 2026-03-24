"""src/api/config_routes.py — 설정 관리 REST API 엔드포인트.

Flask Blueprint으로 구현된 설정 관리 API.

엔드포인트:
  GET  /api/config/status    — 현재 설정 현황 (민감 값 마스킹)
  POST /api/config/reload    — ConfigManager 재로드 트리거
  GET  /api/config/validate  — 설정 유효성 검증 결과

환경변수:
  DASHBOARD_API_KEY — API 인증 키
"""

import datetime
import logging
import os

from flask import Blueprint, jsonify

from .auth_middleware import require_api_key

logger = logging.getLogger(__name__)

config_bp = Blueprint("config", __name__, url_prefix="/api/config")

# 마스킹할 민감 키워드 목록
_SENSITIVE_KEYWORDS = (
    "secret", "token", "password", "key", "api_key", "access_token",
    "client_secret", "ck", "cs", "b64", "json_b64",
)


def _mask_value(key: str, value) -> str:
    """민감한 설정 값을 마스킹한다."""
    key_lower = key.lower()
    for kw in _SENSITIVE_KEYWORDS:
        if kw in key_lower:
            if value and len(str(value)) > 4:
                return str(value)[:4] + "****"
            return "****"
    return value


@config_bp.get("/status")
@require_api_key
def config_status():
    """현재 설정 현황을 반환한다 (민감 값 마스킹)."""
    from ..config import ConfigManager, get_all_config_schema

    mgr = ConfigManager.get_instance()
    schema = get_all_config_schema()

    result = {}
    for entry in schema:
        name = entry["name"]
        raw = mgr.get(name)
        result[name] = {
            "value": _mask_value(name, raw) if raw is not None else None,
            "group": entry.get("group", ""),
            "required": entry.get("required", False),
            "description": entry.get("description", ""),
            "set": os.environ.get(name) is not None,
        }

    return jsonify({
        "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "config": result,
        "total": len(result),
    })


@config_bp.post("/reload")
@require_api_key
def config_reload():
    """ConfigManager를 강제 재로드한다."""
    from ..config import ConfigManager

    mgr = ConfigManager.get_instance()
    try:
        mgr.force_reload()
        logger.info("설정 재로드 완료 (API 요청)")
        return jsonify({
            "ok": True,
            "message": "설정이 재로드되었습니다.",
            "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.error("설정 재로드 실패: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500


@config_bp.get("/validate")
@require_api_key
def config_validate():
    """설정 유효성 검증 결과를 반환한다."""
    from ..config import ConfigValidator

    validator = ConfigValidator()
    is_valid, warnings, errors = validator.validate()

    return jsonify({
        "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        "is_valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "error_count": len(errors),
        "warning_count": len(warnings),
    }), 200 if is_valid else 422
