"""tests/test_dispatcher.py — CollectorDispatcher 테스트 (Phase 135)."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.collectors.universal_scraper import ScrapedProduct
from src.collectors.dispatcher import CollectorDispatcher, collect, supported_domains


class TestCollectorDispatcher:
    def setup_method(self):
        self.dispatcher = CollectorDispatcher()

    def test_supported_domains_includes_aloyoga(self):
        domains = self.dispatcher.supported_domains()
        assert "aloyoga.com" in domains

    def test_supported_domains_includes_lululemon(self):
        domains = self.dispatcher.supported_domains()
        assert "lululemon.com" in domains

    def test_supported_domains_includes_marketstudio(self):
        domains = self.dispatcher.supported_domains()
        assert "marketstudio.com" in domains

    def test_supported_domains_includes_pleasuresnow(self):
        domains = self.dispatcher.supported_domains()
        assert "pleasuresnow.com" in domains

    def test_supported_domains_includes_yoshidakaban(self):
        domains = self.dispatcher.supported_domains()
        assert "yoshidakaban.com" in domains

    def test_no_shein_in_supported_domains(self):
        """Shein은 수집 대상에서 제외됨."""
        domains = self.dispatcher.supported_domains()
        for d in domains:
            assert "shein" not in d.lower()

    def test_alo_adapter_selected(self):
        adapter = self.dispatcher._get_adapter("aloyoga.com")
        assert adapter is not None
        assert adapter.name == "alo"

    def test_lululemon_shop_subdomain(self):
        adapter = self.dispatcher._get_adapter("shop.lululemon.com")
        assert adapter is not None
        assert adapter.name == "lululemon"

    def test_www_prefix_stripped(self):
        adapter = self.dispatcher._get_adapter("www.aloyoga.com")
        assert adapter is not None
        assert adapter.name == "alo"

    def test_unknown_domain_returns_none(self):
        adapter = self.dispatcher._get_adapter("unknown-store.com")
        assert adapter is None

    def test_collect_known_domain_uses_adapter(self):
        """알려진 도메인은 어댑터 사용 (DRY_RUN)."""
        result = self.dispatcher.collect("https://aloyoga.com/products/legging")
        assert isinstance(result, ScrapedProduct)
        assert result.domain == "aloyoga.com"
        assert "alo" in result.extraction_method

    def test_collect_unknown_domain_uses_fallback(self):
        """알 수 없는 도메인은 범용 수집기 폴백."""
        with patch("src.collectors.universal_scraper._fetch_html", return_value=None):
            result = self.dispatcher.collect("https://unknown-store.com/product")
        assert isinstance(result, ScrapedProduct)
        assert result.domain == "unknown-store.com"

    def test_collect_empty_url(self):
        result = self.dispatcher.collect("")
        assert result.confidence == 0.0
        assert result.extraction_method == "error"

    def test_collect_no_scheme(self):
        """스키마 없는 URL도 처리."""
        with patch("src.collectors.universal_scraper._fetch_html", return_value=None):
            result = self.dispatcher.collect("aloyoga.com/products/legging")
        # https:// 자동 추가
        assert "aloyoga" in result.source_url

    def test_adapter_fallback_on_exception(self):
        """어댑터 오류 시 범용 수집기로 폴백."""
        mock_adapter = MagicMock()
        mock_adapter.fetch.side_effect = Exception("어댑터 오류")
        mock_adapter.name = "mock"

        dispatcher = CollectorDispatcher()
        dispatcher.adapters["mock-store.com"] = mock_adapter

        with patch("src.collectors.universal_scraper._fetch_html", return_value=None):
            result = dispatcher.collect("https://mock-store.com/product")
        assert isinstance(result, ScrapedProduct)

    def test_module_level_collect(self):
        """모듈 레벨 collect() 함수."""
        result = collect("https://aloyoga.com/products/item")
        assert isinstance(result, ScrapedProduct)

    def test_module_level_supported_domains(self):
        """모듈 레벨 supported_domains() 함수."""
        domains = supported_domains()
        assert isinstance(domains, list)
        assert len(domains) >= 5
