"""src/middleware/request_logger.py — 구조화된 요청/응답 로깅 미들웨어.

JSON 형식으로 요청과 응답을 기록하며, X-Request-ID 헤더를 생성한다.
민감 데이터(API 키, 토큰, 비밀번호 등)는 마스킹 처리한다.

환경변수:
  REQUEST_LOG_LEVEL       — 로그 레벨 (기본 "info")
  REQUEST_LOG_MASK_FIELDS — 마스킹할 필드명 쉼표 구분 (기본 "api_key,token,secret,password,authorization")
"""

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# 설정
# ──────────────────────────────────────────────────────────

_LOG_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

_LOG_LEVEL = _LOG_LEVEL_MAP.get(
    os.getenv("REQUEST_LOG_LEVEL", "info").lower(),
    logging.INFO,
)

_DEFAULT_MASK_FIELDS = "api_key,token,secret,password,authorization,x-api-key"
_MASK_FIELDS: Set[str] = {
    f.strip().lower()
    for f in os.getenv("REQUEST_LOG_MASK_FIELDS", _DEFAULT_MASK_FIELDS).split(",")
    if f.strip()
}

_MASK_VALUE = "***MASKED***"


# ──────────────────────────────────────────────────────────
# 민감 데이터 마스킹
# ──────────────────────────────────────────────────────────

def _mask_dict(data: Any, mask_fields: Optional[Set[str]] = None) -> Any:
    """딕셔너리(또는 중첩 구조)에서 민감 필드 값을 마스킹한다.

    Args:
        data: 마스킹할 데이터 (dict, list, scalar 모두 가능)
        mask_fields: 마스킹할 필드명 집합 (소문자). None이면 전역 설정 사용.

    Returns:
        마스킹된 복사본
    """
    fields = mask_fields if mask_fields is not None else _MASK_FIELDS
    if isinstance(data, dict):
        return {
            k: _MASK_VALUE if k.lower() in fields else _mask_dict(v, fields)
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [_mask_dict(item, fields) for item in data]
    return data


def _mask_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """요청 헤더에서 민감 값을 마스킹한다."""
    return {
        k: _MASK_VALUE if k.lower() in _MASK_FIELDS else v
        for k, v in headers.items()
    }


# ──────────────────────────────────────────────────────────
# 요청 로거
# ──────────────────────────────────────────────────────────

class RequestLogger:
    """Flask 애플리케이션의 요청/응답을 구조화된 JSON으로 로깅하는 미들웨어.

    사용 예 (Flask):
        request_logger = RequestLogger()
        request_logger.init_app(app)
    """

    def __init__(self, app=None, log_body: bool = False, max_body_length: int = 2048):
        """초기화.

        Args:
            app: Flask 앱 인스턴스. None이면 init_app() 호출 필요.
            log_body: 요청/응답 본문을 로그에 포함할지 여부 (기본 False).
            max_body_length: 본문 로그 최대 길이 (기본 2048 bytes).
        """
        self._log_body = log_body
        self._max_body_length = max_body_length
        self._request_log: logging.Logger = logging.getLogger("proxy_commerce.request")
        if app is not None:
            self.init_app(app)

    def init_app(self, app) -> None:
        """Flask 앱에 before/after_request 훅을 등록한다."""
        app.before_request(self._before_request)
        app.after_request(self._after_request)

    def _before_request(self):
        """요청 시작 시각을 기록하고 Request-ID를 생성한다."""
        from flask import g, request
        g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        g.request_start = time.perf_counter()

    def _after_request(self, response):
        """요청 완료 후 로그를 기록하고 응답에 헤더를 추가한다."""
        from flask import g, request

        request_id = getattr(g, "request_id", str(uuid.uuid4()))
        start = getattr(g, "request_start", time.perf_counter())
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

        # 응답 헤더에 Request-ID 추가
        response.headers["X-Request-ID"] = request_id

        log_entry = self._build_log_entry(request, response, request_id, elapsed_ms)
        self._request_log.log(_LOG_LEVEL, json.dumps(log_entry, ensure_ascii=False))
        return response

    def _build_log_entry(
        self,
        request,
        response,
        request_id: str,
        elapsed_ms: float,
    ) -> Dict[str, Any]:
        """로그 엔트리 딕셔너리를 구성한다."""
        entry: Dict[str, Any] = {
            "request_id": request_id,
            "method": request.method,
            "path": request.path,
            "query": request.query_string.decode("utf-8", errors="replace"),
            "remote_addr": request.remote_addr,
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
            "content_length": response.content_length,
        }

        # 요청 헤더 (마스킹)
        entry["request_headers"] = _mask_headers(dict(request.headers))

        # 요청 본문 (선택적)
        if self._log_body and request.content_length and request.content_length > 0:
            try:
                body_raw = request.get_data(as_text=True)
                body_preview = body_raw[: self._max_body_length]
                # JSON이면 민감 필드 마스킹
                try:
                    parsed = json.loads(body_preview)
                    entry["request_body"] = _mask_dict(parsed)
                except json.JSONDecodeError:
                    entry["request_body"] = body_preview
            except Exception:
                entry["request_body"] = "<읽기 실패>"

        return entry

    @staticmethod
    def make_request_id() -> str:
        """새 Request-ID를 생성한다."""
        return str(uuid.uuid4())

    @staticmethod
    def mask_sensitive(data: Any) -> Any:
        """외부에서 민감 데이터 마스킹에 사용할 수 있는 유틸리티."""
        return _mask_dict(data)
