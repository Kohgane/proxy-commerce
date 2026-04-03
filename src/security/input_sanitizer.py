"""src/security/input_sanitizer.py — 입력 살균기."""
from __future__ import annotations

import re


class InputSanitizer:
    """입력 살균기."""

    _XSS_PATTERNS = [
        (re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL), ''),
        (re.compile(r'<[^>]+on\w+\s*=', re.IGNORECASE), '<'),
        (re.compile(r'javascript:', re.IGNORECASE), ''),
        (re.compile(r'<[^>]*>', re.IGNORECASE), ''),
    ]

    _SQL_PATTERNS = [
        (re.compile(r"('|--|;|/\*|\*/|xp_)", re.IGNORECASE), ''),
        (re.compile(r'\b(UNION|SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC)\b', re.IGNORECASE), ''),
    ]

    _PATH_PATTERNS = [
        (re.compile(r'\.\.[\\/]'), ''),
        (re.compile(r'[\x00-\x1f\x7f]'), ''),
    ]

    def sanitize_xss(self, text: str) -> str:
        """XSS 패턴을 제거한다."""
        for pattern, replacement in self._XSS_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def sanitize_sql(self, text: str) -> str:
        """SQL 인젝션 패턴을 제거한다."""
        for pattern, replacement in self._SQL_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def sanitize_path(self, text: str) -> str:
        """경로 순회 패턴을 제거한다."""
        for pattern, replacement in self._PATH_PATTERNS:
            text = pattern.sub(replacement, text)
        return text

    def sanitize_all(self, text: str) -> str:
        """모든 살균을 적용한다."""
        text = self.sanitize_xss(text)
        text = self.sanitize_sql(text)
        text = self.sanitize_path(text)
        return text
