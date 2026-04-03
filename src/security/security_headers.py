"""src/security/security_headers.py — 보안 헤더."""
from __future__ import annotations


class SecurityHeaders:
    """보안 HTTP 헤더 관리자."""

    def get_headers(self) -> dict:
        """보안 헤더 딕셔너리를 반환한다."""
        return {
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
        }
