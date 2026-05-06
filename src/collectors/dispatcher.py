"""src/collectors/dispatcher.py — CollectorDispatcher (Phase 135).

도메인 → 적합한 수집기 자동 선택.
브랜드 어댑터 우선, 없으면 UniversalScraper 폴백.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse
from typing import Optional

from .universal_scraper import UniversalScraper, ScrapedProduct
from .adapters import (
    AloAdapter,
    LululemonAdapter,
    MarketStudioAdapter,
    PleasuresAdapter,
    YoshidaKabanAdapter,
)

logger = logging.getLogger(__name__)


class CollectorDispatcher:
    """도메인 → 적합한 수집기 자동 선택."""

    def __init__(self):
        self.adapters: dict = {
            "aloyoga.com": AloAdapter(),
            "lululemon.com": LululemonAdapter(),
            "shop.lululemon.com": LululemonAdapter(),
            "marketstudio.com": MarketStudioAdapter(),
            "pleasuresnow.com": PleasuresAdapter(),
            "yoshidakaban.com": YoshidaKabanAdapter(),
        }
        self.fallback = UniversalScraper()

    def collect(self, url: str) -> ScrapedProduct:
        """URL에서 상품 정보 수집 (도메인 기반 자동 분기)."""
        if not url or not url.strip():
            return ScrapedProduct(
                source_url=url or "",
                domain="",
                title="",
                description="",
                confidence=0.0,
                extraction_method="error",
            )

        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        domain = self._extract_domain(url)
        adapter = self._get_adapter(domain)

        if adapter:
            try:
                result = adapter.fetch(url)
                if not result.extraction_method.startswith("adapter:"):
                    result.extraction_method = f"adapter:{adapter.name}"
                logger.info("어댑터 수집 완료: %s → %s (confidence=%.2f)", domain, adapter.name, result.confidence)
                return result
            except Exception as exc:
                logger.warning("어댑터 실패, 범용으로 폴백: %s — %s", domain, exc)

        logger.info("범용 수집기 사용: %s", domain)
        return self.fallback.fetch(url)

    def _get_adapter(self, domain: str):
        """도메인에 맞는 어댑터 반환 (www. 처리 포함)."""
        # 정확 매칭
        adapter = self.adapters.get(domain)
        if adapter:
            return adapter
        # www. 제거 후 재매칭
        if domain.startswith("www."):
            adapter = self.adapters.get(domain[4:])
            if adapter:
                return adapter
        # 서브도메인 매칭 (e.g. shop.lululemon.com → lululemon.com)
        for registered_domain, adp in self.adapters.items():
            if domain.endswith(f".{registered_domain}"):
                return adp
        return None

    def _extract_domain(self, url: str) -> str:
        """URL → 도메인 추출."""
        try:
            host = urlparse(url).netloc.lower()
            return host
        except Exception:
            return ""

    def supported_domains(self) -> list:
        """지원 도메인 목록 반환."""
        return list(self.adapters.keys())


# 모듈 수준 편의 함수
_dispatcher = CollectorDispatcher()


def collect(url: str) -> ScrapedProduct:
    """URL에서 상품 정보 수집 (모듈 레벨 편의 함수)."""
    return _dispatcher.collect(url)


def supported_domains() -> list:
    """지원 도메인 목록."""
    return _dispatcher.supported_domains()
