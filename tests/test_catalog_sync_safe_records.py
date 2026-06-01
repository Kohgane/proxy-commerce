from unittest.mock import patch

import gspread

import src.catalog_sync as catalog_sync


class _SafeWorksheet:
    def __init__(self):
        self.get_all_values_called = False

    def get_all_records(self):
        raise gspread.exceptions.GSpreadException(
            "the header row in the worksheet is not unique, try passing 'expected_headers' to get_all_records"
        )

    def get_all_values(self):
        self.get_all_values_called = True
        return [
            [
                "sku", "title_ko", "title_en", "title_ja", "title_fr", "source_country",
                "src_url", "buy_currency", "buy_price", "stock", "tags", "vendor", "status", "status",
            ],
            [
                "SKU-001", "테스트 상품", "", "", "", "JP",
                "https://example.com/p/1", "JPY", "1000", "3", "bag", "porter", "active", "active",
            ],
        ]


class _NormalWorksheet:
    def __init__(self):
        self.get_all_values_called = False

    def get_all_records(self):
        return [
            {
                "sku": "SKU-001",
                "title_ko": "테스트 상품",
                "title_en": "",
                "title_ja": "",
                "title_fr": "",
                "source_country": "JP",
                "src_url": "https://example.com/p/1",
                "buy_currency": "JPY",
                "buy_price": "1000",
                "stock": "3",
                "tags": "bag",
                "vendor": "porter",
                "status": "active",
            }
        ]

    def get_all_values(self):
        self.get_all_values_called = True
        return []


def test_sync_once_handles_duplicate_headers_without_error(monkeypatch):
    monkeypatch.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("SHOPIFY_SHOP", raising=False)
    monkeypatch.delenv("WOO_CK", raising=False)
    monkeypatch.delenv("WOO_CS", raising=False)
    monkeypatch.delenv("WOO_BASE_URL", raising=False)

    ws = _SafeWorksheet()
    with patch.object(catalog_sync, "open_sheet", return_value=ws), \
         patch.object(catalog_sync, "ensure_images", return_value=[]), \
         patch.object(catalog_sync, "ko_to_en_if_needed", return_value="Test Product"), \
         patch.object(catalog_sync, "shopify_upsert") as mock_shopify, \
         patch.object(catalog_sync, "woo_upsert") as mock_woo, \
         patch.object(catalog_sync.time, "sleep", return_value=None):
        catalog_sync.sync_once()

    assert ws.get_all_values_called is True
    mock_shopify.assert_not_called()
    mock_woo.assert_not_called()


def test_sync_once_preserves_normal_header_behavior(monkeypatch):
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "token")
    monkeypatch.setenv("SHOPIFY_SHOP", "shop")
    monkeypatch.setenv("WOO_CK", "ck")
    monkeypatch.setenv("WOO_CS", "cs")
    monkeypatch.setenv("WOO_BASE_URL", "https://woo.example.com")

    ws = _NormalWorksheet()
    with patch.object(catalog_sync, "open_sheet", return_value=ws), \
         patch.object(catalog_sync, "ensure_images", return_value=[]), \
         patch.object(catalog_sync, "ko_to_en_if_needed", return_value="Test Product"), \
         patch.object(catalog_sync, "shopify_upsert") as mock_shopify, \
         patch.object(catalog_sync, "woo_upsert") as mock_woo, \
         patch.object(catalog_sync.time, "sleep", return_value=None):
        catalog_sync.sync_once()

    assert ws.get_all_values_called is False
    mock_shopify.assert_called_once()
    mock_woo.assert_called_once()
