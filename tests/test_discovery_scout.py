"""tests/test_discovery_scout.py — Discovery 봇 테스트 (Phase 135).

후보 추출 mock 테스트.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
os.environ.setdefault("GOOGLE_SHEET_ID", "")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.discovery.scout import (
    DiscoveryScout,
    _extract_domain,
    _get_keywords_from_env,
    _KNOWN_PLATFORMS,
)


class TestUtils:
    def test_extract_domain_basic(self):
        assert _extract_domain("https://www.example.com/path") == "example.com"

    def test_extract_domain_no_www(self):
        assert _extract_domain("https://aloyoga.com/p") == "aloyoga.com"

    def test_extract_domain_invalid_scheme(self):
        assert _extract_domain("ftp://example.com") is None

    def test_extract_domain_no_dot(self):
        assert _extract_domain("https://localhost/path") is None

    def test_known_platforms_contains_amazon(self):
        assert "amazon.com" in _KNOWN_PLATFORMS

    def test_known_platforms_contains_instagram(self):
        assert "instagram.com" in _KNOWN_PLATFORMS

    def test_get_keywords_from_env_empty(self):
        with patch.dict(os.environ, {"DISCOVERY_KEYWORDS": ""}):
            assert _get_keywords_from_env() == []

    def test_get_keywords_from_env_csv(self):
        with patch.dict(os.environ, {"DISCOVERY_KEYWORDS": "yoga, outdoor, bags"}):
            keywords = _get_keywords_from_env()
            assert "yoga" in keywords
            assert "outdoor" in keywords
            assert "bags" in keywords


class TestDiscoveryScout:
    def setup_method(self):
        self.scout = DiscoveryScout()

    def test_run_once_dry_run(self):
        """DRY_RUN=1: 실제 요청 없이 빈 결과."""
        results = self.scout.run_once()
        assert isinstance(results, list)
        # DRY_RUN이면 Reddit 요청 안 함 → 보통 빈 결과
        assert len(results) == 0

    def test_get_candidates_no_sheet(self):
        """Sheets 없으면 빈 리스트."""
        candidates = self.scout.get_candidates("pending")
        assert candidates == []

    def test_approve_no_sheet(self):
        """Sheets 없으면 False."""
        result = self.scout.approve("unknown-store.com")
        assert result is False

    def test_reject_no_sheet(self):
        result = self.scout.reject("unknown-store.com")
        assert result is False

    def test_get_keywords_uses_default(self):
        """Sheets 없으면 기본 키워드 사용."""
        keywords = self.scout.get_keywords()
        assert isinstance(keywords, list)
        assert len(keywords) > 0

    def test_get_keywords_env_override(self):
        """env 키워드가 있으면 그 키워드 사용."""
        with patch.dict(os.environ, {"DISCOVERY_KEYWORDS": "custom-keyword"}):
            keywords = self.scout.get_keywords()
        assert "custom-keyword" in keywords

    def test_add_keyword_no_sheet(self):
        """Sheets 없으면 False."""
        result = self.scout.add_keyword("new keyword")
        assert result is False

    def test_remove_keyword_no_sheet(self):
        result = self.scout.remove_keyword("old keyword")
        assert result is False

    def test_run_once_skips_known_platforms(self):
        """알려진 플랫폼 도메인은 후보로 등록 안 됨."""
        mock_reddit_urls = [
            "https://www.amazon.com/product",
            "https://instagram.com/brand",
            "https://new-brand.com/product",
        ]
        with patch("src.discovery.scout._search_reddit", return_value=mock_reddit_urls):
            with patch("src.discovery.scout._save_candidate") as mock_save:
                with patch("src.discovery.scout._notify_telegram"):
                    results = self.scout.run_once()

        saved_domains = [r["domain"] for r in results]
        assert "amazon.com" not in saved_domains
        assert "instagram.com" not in saved_domains

    def test_run_once_skips_registered_adapters(self):
        """이미 등록된 어댑터 도메인은 후보로 등록 안 됨."""
        mock_reddit_urls = ["https://aloyoga.com/products/legging"]
        with patch("src.discovery.scout._search_reddit", return_value=mock_reddit_urls):
            with patch("src.discovery.scout._save_candidate") as mock_save:
                with patch("src.discovery.scout._notify_telegram"):
                    results = self.scout.run_once()

        saved_domains = [r["domain"] for r in results]
        assert "aloyoga.com" not in saved_domains
