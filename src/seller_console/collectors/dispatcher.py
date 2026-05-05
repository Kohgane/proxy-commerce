"""src/seller_console/collectors/dispatcher.py — URL → 컬렉터 분기 (Phase 128).

도메인 감지 → 적절한 collector 분기.

지원:
- amazon.com / amazon.co.jp → AmazonCollector (PA-API 또는 OG meta 폴백)
- rakuten.co.jp → RakutenCollector (Rakuten WS API 또는 OG meta)
- aloyoga.com → AloCollector (스크래핑)
- shop.lululemon.com / lululemon.com → LululemonCollector (스크래핑)
- 1688.com / taobao.com → 미지원 안내 + OG meta 폴백
- 기타 → GenericOgCollector (Open Graph 메타태그 파싱)
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from .base import BaseCollector, CollectorResult
from .amazon import AmazonCollector
from .rakuten import RakutenCollector
from .alo import AloCollector
from .lululemon import LululemonCollector
from .generic_og import GenericOgCollector

logger = logging.getLogger(__name__)

# 도메인 → 컬렉터 매핑
DOMAIN_MAP: dict = {
    "amazon.com": AmazonCollector,
    "amazon.co.jp": AmazonCollector,
    "amazon.co.uk": AmazonCollector,
    "amazon.de": AmazonCollector,
    "amazon.fr": AmazonCollector,
    "rakuten.co.jp": RakutenCollector,
    "aloyoga.com": AloCollector,
    "shop.lululemon.com": LululemonCollector,
    "lululemon.com": LululemonCollector,
}

# 미지원 안내 도메인 (OG 폴백 + 경고)
_UNSUPPORTED_WARN: dict = {
    "1688.com": "1688.com은 직접 API가 없습니다. OG 메타로 기본 정보만 수집됩니다. 수동 입력을 권장합니다.",
    "taobao.com": "타오바오는 직접 API가 없습니다. OG 메타로 기본 정보만 수집됩니다. 수동 입력을 권장합니다.",
    "tmall.com": "티몰은 직접 API가 없습니다. OG 메타로 기본 정보만 수집됩니다.",
}


def detect_collector(url: str) -> BaseCollector:
    """URL의 도메인에 맞는 컬렉터 인스턴스 반환.

    Args:
        url: 상품 URL

    Returns:
        적절한 BaseCollector 인스턴스
    """
    try:
        raw_host = urlparse(url).netloc.lower()
        # www. 접두사만 정확하게 제거 (lstrip은 개별 문자 제거로 오동작할 수 있음)
        host = raw_host[4:] if raw_host.startswith("www.") else raw_host
    except Exception:
        return GenericOgCollector()

    # 정확 매칭 또는 서브도메인 포함 매칭
    for domain, klass in DOMAIN_MAP.items():
        if host == domain or host.endswith(f".{domain}"):
            return klass()

    return GenericOgCollector()


def collect(url: str) -> CollectorResult:
    """URL에서 상품 정보 수집 (도메인 기반 자동 분기).

    Args:
        url: 상품 URL

    Returns:
        CollectorResult 인스턴스
    """
    if not url or not url.strip():
        return CollectorResult(
            success=False,
            url=url or "",
            source="dispatcher",
            error="URL이 비어있습니다.",
        )

    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # 미지원 도메인 경고
    try:
        raw_host = urlparse(url).netloc.lower()
        host = raw_host[4:] if raw_host.startswith("www.") else raw_host
        warn_msg = None
        for domain, msg in _UNSUPPORTED_WARN.items():
            if host == domain or host.endswith(f".{domain}"):
                warn_msg = msg
                break
    except Exception:
        warn_msg = None

    collector = detect_collector(url)
    logger.info("URL 수집 시작: %s (collector: %s)", url, collector.name)

    result = collector.collect(url)

    if warn_msg and warn_msg not in result.warnings:
        result.warnings.insert(0, warn_msg)

    return result
