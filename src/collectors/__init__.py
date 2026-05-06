"""src/collectors 패키지 — 해외 쇼핑몰 상품 수집 엔진 (Phase 135 갱신)."""

from .base_collector import BaseCollector
from .amazon_collector import AmazonCollector
from .taobao_collector import TaobaoCollector
from .collection_manager import CollectionManager
from .universal_scraper import UniversalScraper, ScrapedProduct
from .dispatcher import CollectorDispatcher, collect, supported_domains

__all__ = [
    'BaseCollector',
    'AmazonCollector',
    'TaobaoCollector',
    'CollectionManager',
    'UniversalScraper',
    'ScrapedProduct',
    'CollectorDispatcher',
    'collect',
    'supported_domains',
]
