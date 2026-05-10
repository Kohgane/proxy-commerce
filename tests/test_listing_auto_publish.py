"""tests/test_listing_auto_publish.py — Phase 143: 상품 등록 자동화 테스트."""
from __future__ import annotations

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

def _make_product(**kwargs):
    from src.listing.auto_publish import Product
    defaults = dict(
        product_id="p1",
        title_ko="테스트 상품",
        title_original="テスト商品",
        description_ko="상품 설명입니다.",
        price_krw=50000,
        category="전자기기",
        image_urls=["https://example.com/img.jpg"],
        stock=10,
        source_platform="rakuten",
        source_url="https://item.rakuten.co.jp/dummy/1",
    )
    defaults.update(kwargs)
    return Product(**defaults)


def _make_candidate(**kwargs):
    from src.sourcing.pipeline import Candidate
    from datetime import datetime, timezone
    defaults = dict(
        candidate_id="cand1",
        watch_id="w1",
        platform="rakuten",
        product_name="テスト商品",
        product_url="https://item.rakuten.co.jp/dummy/1",
        source_price=5000.0,
        currency="JPY",
        source_price_krw=45000.0,
        estimated_selling_price_krw=90000.0,
        estimated_margin_pct=22.5,
        image_urls=[],
        category="전자기기",
        discovered_at=datetime.now(timezone.utc).isoformat(),
    )
    defaults.update(kwargs)
    return Candidate(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# Product
# ═══════════════════════════════════════════════════════════════════════════════

class TestProduct:
    def test_to_dict_keys(self):
        p = _make_product()
        d = p.to_dict()
        for key in ("product_id", "title_ko", "price_krw", "category", "image_urls"):
            assert key in d

    def test_default_lists_empty(self):
        from src.listing.auto_publish import Product
        p = Product(product_id="x", title_ko="t")
        assert p.image_urls == []
        assert p.options == []
        assert p.spec == {}


# ═══════════════════════════════════════════════════════════════════════════════
# ChannelListing
# ═══════════════════════════════════════════════════════════════════════════════

class TestChannelListing:
    def test_to_dict_keys(self):
        from src.listing.auto_publish import ChannelListing
        listing = ChannelListing(
            channel="coupang",
            product_id="p1",
            title="테스트",
            description="설명",
            price=55000,
            channel_category_id="56137",
            image_urls=[],
            options=[],
        )
        d = listing.to_dict()
        for key in ("channel", "product_id", "title", "price", "channel_category_id"):
            assert key in d


# ═══════════════════════════════════════════════════════════════════════════════
# adapt_for_channel
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdaptForChannel:
    def test_adapt_coupang(self):
        from src.listing.auto_publish import adapt_for_channel
        p = _make_product(price_krw=50000, category="전자기기")
        listing = adapt_for_channel(p, "coupang")
        assert listing.channel == "coupang"
        assert listing.price > 50000  # 수수료 반영
        assert listing.channel_category_id == "56137"

    def test_adapt_smartstore(self):
        from src.listing.auto_publish import adapt_for_channel
        p = _make_product(price_krw=50000, category="뷰티")
        listing = adapt_for_channel(p, "smartstore")
        assert listing.channel == "smartstore"
        assert listing.channel_category_id == "50000819"

    def test_adapt_11st(self):
        from src.listing.auto_publish import adapt_for_channel
        p = _make_product(price_krw=50000, category="패션")
        listing = adapt_for_channel(p, "11st")
        assert listing.channel == "11st"

    def test_title_truncation_coupang(self):
        from src.listing.auto_publish import adapt_for_channel
        p = _make_product(title_ko="A" * 200)
        listing = adapt_for_channel(p, "coupang")
        assert len(listing.title) <= 100

    def test_title_truncation_11st(self):
        from src.listing.auto_publish import adapt_for_channel
        p = _make_product(title_ko="A" * 200)
        listing = adapt_for_channel(p, "11st")
        assert len(listing.title) <= 80

    def test_price_100won_rounded(self):
        from src.listing.auto_publish import adapt_for_channel
        p = _make_product(price_krw=50001)
        listing = adapt_for_channel(p, "coupang")
        assert listing.price % 100 == 0

    def test_processed_images_preferred(self):
        from src.listing.auto_publish import adapt_for_channel
        p = _make_product(
            image_urls=["https://example.com/original.jpg"],
            processed_image_urls=["https://cdn.example.com/processed.jpg"],
        )
        listing = adapt_for_channel(p, "coupang")
        assert listing.image_urls == ["https://cdn.example.com/processed.jpg"]

    def test_fallback_to_original_images(self):
        from src.listing.auto_publish import adapt_for_channel
        p = _make_product(image_urls=["https://example.com/orig.jpg"])
        listing = adapt_for_channel(p, "coupang")
        assert listing.image_urls == ["https://example.com/orig.jpg"]

    def test_spec_added_to_description(self):
        from src.listing.auto_publish import adapt_for_channel
        p = _make_product(description_ko="기본 설명", spec={"사이즈": "M", "소재": "면"})
        listing = adapt_for_channel(p, "coupang")
        assert "사이즈" in listing.description
        assert "M" in listing.description

    def test_default_category_fallback(self):
        from src.listing.auto_publish import adapt_for_channel
        p = _make_product(category="알 수 없는 카테고리")
        listing = adapt_for_channel(p, "coupang")
        assert listing.channel_category_id != ""

    def test_unknown_channel_uses_default_fee(self):
        from src.listing.auto_publish import adapt_for_channel
        p = _make_product(price_krw=10000)
        listing = adapt_for_channel(p, "unknown_channel")
        assert listing.price >= 10000


# ═══════════════════════════════════════════════════════════════════════════════
# auto_publish (dry-run mode)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutoPublish:
    def test_dry_run_returns_summary(self, monkeypatch):
        monkeypatch.setenv("LISTING_AUTO_PUBLISH", "0")
        # reload module to pick up env
        import importlib
        import src.listing.auto_publish as m
        importlib.reload(m)
        c = _make_candidate()
        result = m.auto_publish(c, channels=["coupang", "smartstore"])
        assert "channels" in result
        assert result["success_count"] >= 0
        assert "product_id" in result

    def test_channels_in_result(self, monkeypatch):
        monkeypatch.setenv("LISTING_AUTO_PUBLISH", "0")
        import importlib
        import src.listing.auto_publish as m
        importlib.reload(m)
        c = _make_candidate()
        result = m.auto_publish(c, channels=["coupang", "smartstore"])
        assert "coupang" in result["channels"]
        assert "smartstore" in result["channels"]

    def test_partial_failure_allowed(self, monkeypatch):
        """부분 실패 시 다른 채널 결과 포함."""
        monkeypatch.setenv("LISTING_AUTO_PUBLISH", "1")
        import importlib
        import src.listing.auto_publish as m
        importlib.reload(m)

        # coupang publisher mock
        class _MockResult:
            success = True
            listing_id = "mock-lid"
            error = None

        class _MockPub:
            def publish(self, data):
                return _MockResult()

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("LISTING_AUTO_PUBLISH", "1")
            c = _make_candidate()
            result = m.auto_publish(c, channels=["coupang", "smartstore"])
            assert "coupang" in result["channels"]
            assert "smartstore" in result["channels"]
            assert result["fail_count"] + result["success_count"] == 2

    def test_history_stored(self, monkeypatch):
        monkeypatch.setenv("LISTING_AUTO_PUBLISH", "0")
        import importlib
        import src.listing.auto_publish as m
        importlib.reload(m)
        m._listing_history.clear()
        c = _make_candidate()
        m.auto_publish(c, channels=["coupang"])
        assert len(m._listing_history) == 1

    def test_published_at_in_result(self, monkeypatch):
        monkeypatch.setenv("LISTING_AUTO_PUBLISH", "0")
        import importlib
        import src.listing.auto_publish as m
        importlib.reload(m)
        c = _make_candidate()
        result = m.auto_publish(c, channels=["coupang"])
        assert "published_at" in result

    def test_auto_publish_enabled_flag(self, monkeypatch):
        monkeypatch.setenv("LISTING_AUTO_PUBLISH", "0")
        import importlib
        import src.listing.auto_publish as m
        importlib.reload(m)
        c = _make_candidate()
        result = m.auto_publish(c, channels=["coupang"])
        # dry-run에서도 success (내부 mock)
        assert result["auto_publish_enabled"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# listing_stats
# ═══════════════════════════════════════════════════════════════════════════════

class TestListingStats:
    def test_stats_keys(self):
        from src.listing.auto_publish import listing_stats
        stats = listing_stats()
        for key in ("total_listings", "listings_24h", "auto_publish_enabled", "default_channels"):
            assert key in stats

    def test_stats_after_publish(self, monkeypatch):
        monkeypatch.setenv("LISTING_AUTO_PUBLISH", "0")
        import importlib
        import src.listing.auto_publish as m
        importlib.reload(m)
        m._listing_history.clear()
        c = _make_candidate()
        m.auto_publish(c, channels=["coupang"])
        stats = m.listing_stats()
        assert stats["total_listings"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# ChannelUploadResult
# ═══════════════════════════════════════════════════════════════════════════════

class TestChannelUploadResult:
    def test_to_dict(self):
        from src.listing.auto_publish import ChannelUploadResult
        r = ChannelUploadResult(channel="coupang", success=True, listing_id="lid1")
        d = r.to_dict()
        assert d["channel"] == "coupang"
        assert d["success"] is True
        assert d["listing_id"] == "lid1"
        assert "uploaded_at" in d
