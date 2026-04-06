"""src/security_advanced/request_signer.py — API 요청 서명/검증 (HMAC-SHA256) (Phase 116)."""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 타임스탬프 허용 오차 (초) — 리플레이 공격 방지
_TIMESTAMP_TOLERANCE_SECONDS = 300  # ±5분 (300초)


@dataclass
class APIKeyRecord:
    api_key: str
    description: str
    created_by: str
    created_at: datetime
    is_active: bool = True
    last_used_at: Optional[datetime] = None


class RequestSigner:
    """HMAC-SHA256 기반 API 요청 서명/검증."""

    def __init__(self) -> None:
        # api_key -> (api_secret, APIKeyRecord)
        self._keys: Dict[str, tuple] = {}

    # ── 키 관리 ────────────────────────────────────────────────────────────

    def generate_api_key(
        self, description: str = "", created_by: str = "system"
    ) -> tuple:
        """(api_key, api_secret) 페어 발급."""
        api_key = "ak_" + secrets.token_hex(16)
        api_secret = secrets.token_hex(32)
        record = APIKeyRecord(
            api_key=api_key,
            description=description,
            created_by=created_by,
            created_at=datetime.now(tz=timezone.utc),
        )
        self._keys[api_key] = (api_secret, record)
        logger.info("API 키 발급: %s...(%s)", api_key[:8], created_by)
        return api_key, api_secret

    def revoke_api_key(self, api_key: str) -> None:
        if api_key not in self._keys:
            raise KeyError(f"API 키를 찾을 수 없음: {api_key[:8]}...")
        secret, record = self._keys[api_key]
        record.is_active = False
        logger.info("API 키 비활성화: %s...", api_key[:8])

    def list_api_keys(self) -> List[APIKeyRecord]:
        """secret 제외한 키 목록 반환."""
        return [record for _, record in self._keys.values()]

    # ── 서명 생성/검증 ────────────────────────────────────────────────────

    def sign_request(
        self,
        method: str,
        path: str,
        body: str,
        timestamp: str,
        api_secret: str,
    ) -> str:
        """HMAC-SHA256 서명 생성."""
        message = f"{method.upper()}\n{path}\n{body}\n{timestamp}"
        signature = hmac.new(
            api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def verify_signature(
        self,
        method: str,
        path: str,
        body: str,
        timestamp: str,
        signature: str,
        api_key: str,
    ) -> bool:
        """서명 검증. 타임스탬프 유효성 + HMAC 일치 확인."""
        if api_key not in self._keys:
            logger.warning("알 수 없는 API 키: %s...", api_key[:8] if api_key else "")
            return False
        api_secret, record = self._keys[api_key]
        if not record.is_active:
            logger.warning("비활성화된 API 키: %s...", api_key[:8])
            return False

        # 타임스탬프 유효성 검사
        try:
            ts = float(timestamp)
        except (ValueError, TypeError):
            logger.warning("유효하지 않은 타임스탬프: %s", timestamp)
            return False
        now = time.time()
        if abs(now - ts) > _TIMESTAMP_TOLERANCE_SECONDS:
            logger.warning("타임스탬프 만료: %s (현재 %s)", ts, now)
            return False

        expected = self.sign_request(method, path, body, timestamp, api_secret)
        result = hmac.compare_digest(expected, signature)
        if result:
            record.last_used_at = datetime.now(tz=timezone.utc)
        return result


class SignatureVerificationMiddleware:
    """Flask before_request 서명 검증 미들웨어."""

    def __init__(
        self,
        signer: RequestSigner,
        excluded_paths: Optional[List[str]] = None,
    ) -> None:
        self._signer = signer
        self._excluded = set(excluded_paths or ["/health", "/api/docs"])

    def init_app(self, app: Any) -> None:
        @app.before_request
        def _verify_signature() -> Any:
            from flask import request, jsonify
            if request.path in self._excluded:
                return None
            api_key = request.headers.get("X-API-Key", "")
            timestamp = request.headers.get("X-Timestamp", "")
            signature = request.headers.get("X-Signature", "")
            if not (api_key and timestamp and signature):
                return None  # 헤더 없으면 검증 생략 (선택적 적용)
            body = request.get_data(as_text=True) or ""
            if not self._signer.verify_signature(
                request.method, request.path, body, timestamp, signature, api_key
            ):
                return jsonify({"error": "서명 검증 실패"}), 401
            return None
