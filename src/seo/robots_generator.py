"""src/seo/robots_generator.py — robots.txt 동적 생성 (Phase 91).

robots.txt 규칙:
  - Disallow: /admin/, /api/
  - Allow: /products/, /categories/
  - Sitemap URL 포함

API 엔드포인트: GET /robots.txt
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class RobotsGenerator:
    """robots.txt 동적 생성기."""

    def __init__(self, base_url: str = "https://example.com") -> None:
        self.base_url = base_url.rstrip("/")

    def generate(
        self,
        sitemap_url: str | None = None,
        extra_disallows: list | None = None,
        extra_allows: list | None = None,
    ) -> str:
        """robots.txt 내용을 생성한다.

        Args:
            sitemap_url: Sitemap URL (없으면 기본 경로 사용)
            extra_disallows: 추가 Disallow 경로 목록
            extra_allows: 추가 Allow 경로 목록

        Returns:
            robots.txt 문자열
        """
        sitemap = sitemap_url or f"{self.base_url}/sitemap.xml"

        disallows = ["/admin/", "/api/"]
        if extra_disallows:
            disallows.extend(extra_disallows)

        allows = ["/products/", "/categories/"]
        if extra_allows:
            allows.extend(extra_allows)

        lines = ["User-agent: *"]
        for path in disallows:
            lines.append(f"Disallow: {path}")
        for path in allows:
            lines.append(f"Allow: {path}")
        lines.append("")
        lines.append(f"Sitemap: {sitemap}")

        return "\n".join(lines)
