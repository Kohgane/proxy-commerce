"""tests/test_yoshida_adapter.py — Yoshida Kaban 어댑터 테스트 (Phase 135).

일본어 상품 + 엔화 변환 테스트.
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from unittest.mock import patch

import pytest

os.environ.setdefault("ADAPTER_DRY_RUN", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.collectors.adapters.yoshida_kaban_adapter import (
    YoshidaKabanAdapter,
    _detect_category,
    _jpy_to_krw,
    _translate_text,
)


class TestUtils:
    def test_detect_category_bag(self):
        assert _detect_category("PORTER トートバッグ 新作") == "토트백"

    def test_detect_category_wallet(self):
        assert _detect_category("吉田カバン 財布") == "지갑"

    def test_detect_category_backpack(self):
        assert _detect_category("PORTER リュック") == "백팩"

    def test_detect_category_default(self):
        assert _detect_category("不明な商品") == "가방"

    def test_jpy_to_krw_default_rate(self):
        """기본 환율 9.0 적용."""
        with patch.dict(os.environ, {"JPY_KRW_RATE": "9.0", "GOOGLE_SHEET_ID": ""}):
            result = _jpy_to_krw(Decimal("33000"))
        assert result == Decimal("297000.0")

    def test_translate_text_dry_run(self):
        """DRY_RUN=1에서는 번역 안 하고 원문 반환."""
        result = _translate_text("テスト商品", "JA", "KO")
        assert result == "テスト商品"

    def test_translate_text_empty(self):
        result = _translate_text("", "JA", "KO")
        assert result == ""


class TestYoshidaKabanAdapterDryRun:
    def setup_method(self):
        self.adapter = YoshidaKabanAdapter()

    def test_name_and_domain(self):
        assert self.adapter.name == "yoshida_kaban"
        assert self.adapter.domain == "yoshidakaban.com"

    def test_fetch_dry_run(self):
        result = self.adapter.fetch("https://yoshidakaban.com/products/tote")
        assert "PORTER" in result.title
        assert result.price == Decimal("33000")
        assert result.currency == "JPY"
        assert "price_krw" in result.raw_meta
        assert result.brand == "PORTER / 吉田カバン"
        assert result.confidence == 1.0

    def test_dry_run_category_in_meta(self):
        result = self.adapter.fetch("https://yoshidakaban.com/products/tote")
        assert "category" in result.raw_meta


class TestYoshidaKabanAdapterParse:
    def setup_method(self):
        self.adapter = YoshidaKabanAdapter()

    def _make_soup(self, html: str):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser")

    def test_parse_jsonld(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type":"Product","name":"ポーター トートバッグ","description":"PORTERの新作トートバッグです。",
         "sku":"PT-001",
         "image":["https://yoshidakaban.com/img.jpg"],
         "offers":{"price":"33000","priceCurrency":"JPY"}}
        </script>
        </head></html>
        """
        soup = self._make_soup(html)
        # DRY_RUN=1이므로 번역 없이 원문 유지
        result = self.adapter._parse(soup, "https://yoshidakaban.com/p", "yoshidakaban.com")
        assert result.title == "ポーター トートバッグ"
        assert result.price == Decimal("33000")
        assert result.currency == "JPY"
        assert result.brand == "PORTER / 吉田カバン"
        assert result.raw_meta.get("category") == "토트백"

    def test_parse_sets_title_ja_in_meta(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type":"Product","name":"財布","description":"","offers":{"price":"15000","priceCurrency":"JPY"}}
        </script>
        </head></html>
        """
        soup = self._make_soup(html)
        result = self.adapter._parse(soup, "https://yoshidakaban.com/p", "yoshidakaban.com")
        assert result.raw_meta.get("title_ja") == "財布"
        assert result.raw_meta.get("category") == "지갑"
