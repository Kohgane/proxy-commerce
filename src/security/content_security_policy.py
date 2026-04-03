"""src/security/content_security_policy.py — 콘텐츠 보안 정책."""
from __future__ import annotations


class ContentSecurityPolicy:
    """콘텐츠 보안 정책 관리자."""

    def __init__(self) -> None:
        self._policy: dict[str, list[str]] = {
            "default-src": ["'self'"],
            "script-src": ["'self'"],
            "style-src": ["'self'", "'unsafe-inline'"],
            "img-src": ["'self'", "data:"],
            "connect-src": ["'self'"],
            "font-src": ["'self'"],
            "object-src": ["'none'"],
            "frame-ancestors": ["'none'"],
        }

    def add_directive(self, directive: str, value: str) -> None:
        """정책 지시어에 값을 추가한다."""
        self._policy.setdefault(directive, []).append(value)

    def generate_header(self) -> str:
        """CSP 헤더 문자열을 생성한다."""
        parts = []
        for directive, values in self._policy.items():
            parts.append(f"{directive} {' '.join(values)}")
        return "; ".join(parts)

    def get_policy(self) -> dict:
        """정책을 딕셔너리로 반환한다."""
        return dict(self._policy)
