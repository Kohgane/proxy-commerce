from __future__ import annotations

from datetime import datetime, timezone

import pytest


@pytest.fixture
def client():
    from src.order_webhook import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_collect_localize_returns_honest_unconfigured(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)

    resp = client.post(
        "/seller/collect/localize",
        json={"product": {"title": "테스트 상품"}, "target_locales": ["en-US"]},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["configured"] is False
    assert data["untranslated"] == 1


def test_collect_localize_generates_localized_payload(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("DEEPL_API_KEY", raising=False)

    from src.seller_console.localization_service import LocalizationResult, LocalizationService

    def _fake_localize(self, product, locale, source_lang=None):
        return LocalizationResult(
            locale=locale,
            translated={
                "locale": locale,
                "language": "en",
                "title": f"{product.get('title')}:{locale}",
                "description": "",
                "keywords": [],
                "options": [],
                "status": "translated",
                "untranslated": False,
            },
            translated_count=1,
            cache_hits=0,
            untranslated=False,
            status="translated",
        )

    monkeypatch.setattr(LocalizationService, "localize_product", _fake_localize)

    resp = client.post(
        "/seller/collect/localize",
        json={"product": {"title": "테스트 상품"}, "target_locales": ["en-US", "ja-JP"]},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["configured"] is True
    assert data["success"] == 1
    assert "en-US" in data["items"][0]["localized"]
    assert "ja-JP" in data["items"][0]["localized"]


def test_catalog_prefers_localized_title_for_market_locale(client):
    from src.seller_console.market_status import AllMarketStatus, MarketStatusItem
    from unittest.mock import patch

    item = MarketStatusItem(
        marketplace="amazon",
        product_id="A1",
        state="active",
        title="원문 제목",
        localized={
            "en-US": {"title": "Localized EN Title", "description": "", "keywords": [], "options": []},
        },
        localization_status="localized",
        last_synced_at=datetime.now(timezone.utc),
    )
    fetched = AllMarketStatus(summaries=[], items=[item], source="sheets")
    with patch("src.seller_console.market_status_sheets.MarketStatusSheetsAdapter.fetch_all", return_value=fetched):
        resp = client.get("/seller/catalog?marketplace=amazon")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Localized EN Title" in html
