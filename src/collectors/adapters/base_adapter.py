"""src/collectors/adapters/base_adapter.py — 브랜드 어댑터 추상 기반 (Phase 135)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..universal_scraper import ScrapedProduct  # noqa: F401 — re-export


class BrandAdapter(ABC):
    """브랜드 수집 어댑터 추상 기반 클래스."""

    name: str = "base"
    domain: str = ""

    @abstractmethod
    def fetch(self, url: str) -> ScrapedProduct:
        """URL에서 상품 정보 수집."""
        ...

    def health_check(self) -> dict:
        """도메인 도달성 확인."""
        import requests
        try:
            resp = requests.head(
                f"https://www.{self.domain}",
                timeout=5,
                headers={"User-Agent": "KohganePercentiii/1.0"},
                allow_redirects=True,
            )
            return {"domain": self.domain, "ok": resp.status_code < 400, "status_code": resp.status_code}
        except Exception as exc:
            return {"domain": self.domain, "ok": False, "error": str(exc)}
