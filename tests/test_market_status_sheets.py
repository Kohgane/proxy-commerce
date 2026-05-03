"""tests/test_market_status_sheets.py — Google Sheets 어댑터 mock 테스트 (Phase 127).

MarketStatusSheetsAdapter를 gspread mock으로 테스트.
실제 Google Sheets 연결 없이 동작.
"""
from __future__ import annotations

import sys
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def adapter():
    """테스트용 MarketStatusSheetsAdapter (sheet_id 고정)."""
    from src.seller_console.market_status_sheets import MarketStatusSheetsAdapter
    return MarketStatusSheetsAdapter(sheet_id="test-sheet-id")


@pytest.fixture
def sample_rows():
    """catalog 워크시트 샘플 행 리스트."""
    return [
        {
            "product_id": "P001",
            "sku": "CP-001",
            "title": "쿠팡 테스트 상품",
            "marketplace": "coupang",
            "state": "active",
            "price_krw": "29900",
            "last_synced_at": "2026-05-03T10:00:00",
            "error_message": "",
        },
        {
            "product_id": "P002",
            "sku": "SS-002",
            "title": "스마트스토어 품절 상품",
            "marketplace": "smartstore",
            "state": "out_of_stock",
            "price_krw": "15000",
            "last_synced_at": "2026-05-03T09:00:00",
            "error_message": "",
        },
        {
            "product_id": "P003",
            "sku": "11S-003",
            "title": "11번가 오류 상품",
            "marketplace": "11st",
            "state": "error",
            "price_krw": "",
            "last_synced_at": "",
            "error_message": "API 인증 실패",
        },
        {
            "product_id": "P004",
            "sku": "CP-004",
            "title": "쿠팡 품절 상품",
            "marketplace": "coupang",
            "state": "out_of_stock",
            "price_krw": "45000",
            "last_synced_at": "2026-05-03T08:00:00",
            "error_message": "",
        },
    ]


# ---------------------------------------------------------------------------
# 테스트: 시트에서 정상 데이터 읽기
# ---------------------------------------------------------------------------

class TestFetchAll:
    """fetch_all() 시트 데이터 집계 테스트."""

    def _make_mock_sheet(self, rows):
        """gspread 목업 시트 반환."""
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = rows
        mock_sh = MagicMock()
        return mock_sh, mock_ws

    @patch("src.utils.sheets.open_sheet_object")
    @patch("src.utils.sheets.get_or_create_worksheet")
    def test_fetch_all_returns_sheets_source(self, mock_create_ws, mock_open_sh, adapter, sample_rows):
        """시트 데이터 있을 때 source='sheets' 반환."""
        mock_sh = MagicMock()
        mock_open_sh.return_value = mock_sh
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = sample_rows
        mock_create_ws.return_value = mock_ws

        result = adapter.fetch_all()

        assert result.source == "sheets"
        assert len(result.items) == 4

    @patch("src.utils.sheets.open_sheet_object")
    @patch("src.utils.sheets.get_or_create_worksheet")
    def test_summarize_counts_correct(self, mock_create_ws, mock_open_sh, adapter, sample_rows):
        """마켓별 집계 수치 정확성 검증."""
        mock_open_sh.return_value = MagicMock()
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = sample_rows
        mock_create_ws.return_value = mock_ws

        result = adapter.fetch_all()
        summaries = {s.marketplace: s for s in result.summaries}

        # 쿠팡: 활성 1, 품절 1
        assert summaries["coupang"].active == 1
        assert summaries["coupang"].out_of_stock == 1
        assert summaries["coupang"].total == 2

        # 스마트스토어: 품절 1
        assert summaries["smartstore"].out_of_stock == 1
        assert summaries["smartstore"].total == 1

        # 11번가: 오류 1
        assert summaries["11st"].error == 1
        assert summaries["11st"].total == 1

    @patch("src.utils.sheets.open_sheet_object")
    @patch("src.utils.sheets.get_or_create_worksheet")
    def test_empty_sheet_returns_mock_fallback(self, mock_create_ws, mock_open_sh, adapter):
        """빈 시트 → mock 폴백."""
        mock_open_sh.return_value = MagicMock()
        mock_ws = MagicMock()
        mock_ws.get_all_records.return_value = []
        mock_create_ws.return_value = mock_ws

        result = adapter.fetch_all()

        assert result.source == "mock"
        # mock 폴백에 3개 마켓 있어야 함
        assert len(result.summaries) == 3

    def test_no_sheet_id_returns_mock_fallback(self):
        """sheet_id 없으면 mock 폴백."""
        from src.seller_console.market_status_sheets import MarketStatusSheetsAdapter
        adapter_no_id = MarketStatusSheetsAdapter(sheet_id="")

        result = adapter_no_id.fetch_all()
        assert result.source == "mock"

    def test_sheets_exception_returns_mock_fallback(self, adapter):
        """시트 열기 예외 → mock 폴백."""
        with patch(
            "src.utils.sheets.open_sheet_object",
            side_effect=Exception("연결 실패"),
        ):
            result = adapter.fetch_all()
            assert result.source == "mock"


# ---------------------------------------------------------------------------
# 테스트: 행 변환
# ---------------------------------------------------------------------------

class TestRowToItem:
    """_row_to_item() 변환 테스트."""

    def test_basic_row_conversion(self, adapter):
        """기본 행 → MarketStatusItem 변환."""
        row = {
            "product_id": "P100",
            "sku": "SKU-100",
            "title": "테스트 상품",
            "marketplace": "coupang",
            "state": "active",
            "price_krw": "59800",
            "last_synced_at": "2026-05-03T12:00:00",
            "error_message": "",
        }
        item = adapter._row_to_item(row)

        assert item.product_id == "P100"
        assert item.sku == "SKU-100"
        assert item.marketplace == "coupang"
        assert item.state == "active"
        assert item.price_krw == 59800
        assert item.last_synced_at == datetime(2026, 5, 3, 12, 0, 0)

    def test_korean_state_normalization(self, adapter):
        """한국어 상태 값 정규화."""
        row = {
            "product_id": "P200",
            "marketplace": "smartstore",
            "state": "품절",
            "price_krw": "",
            "sku": "",
            "title": "",
            "last_synced_at": "",
            "error_message": "",
        }
        item = adapter._row_to_item(row)
        assert item.state == "out_of_stock"

    def test_unknown_state_maps_to_error(self, adapter):
        """알 수 없는 상태 → error."""
        row = {
            "product_id": "P300",
            "marketplace": "coupang",
            "state": "unknown_xyz",
            "price_krw": "",
            "sku": "",
            "title": "",
            "last_synced_at": "",
            "error_message": "",
        }
        item = adapter._row_to_item(row)
        assert item.state == "error"

    def test_empty_price_is_none(self, adapter):
        """빈 price_krw → None."""
        row = {
            "product_id": "P400",
            "marketplace": "coupang",
            "state": "active",
            "price_krw": "",
            "sku": "",
            "title": "",
            "last_synced_at": "",
            "error_message": "",
        }
        item = adapter._row_to_item(row)
        assert item.price_krw is None


# ---------------------------------------------------------------------------
# 테스트: mock 폴백 구조
# ---------------------------------------------------------------------------

class TestMockFallback:
    """_mock_fallback() 구조 검증."""

    def test_mock_fallback_has_three_markets(self, adapter):
        """mock 폴백 → 3개 마켓 요약."""
        result = adapter._mock_fallback()
        assert len(result.summaries) == 3
        markets = {s.marketplace for s in result.summaries}
        assert "coupang" in markets
        assert "smartstore" in markets
        assert "11st" in markets

    def test_mock_fallback_source_is_mock(self, adapter):
        """mock 폴백 source = 'mock'."""
        result = adapter._mock_fallback()
        assert result.source == "mock"
        for s in result.summaries:
            assert s.source == "mock"


# ---------------------------------------------------------------------------
# 테스트: to_legacy_dict 호환성
# ---------------------------------------------------------------------------

class TestLegacyDict:
    """AllMarketStatus.to_legacy_dict() 기존 포맷 호환 테스트."""

    def test_legacy_dict_has_markets_key(self, adapter):
        """to_legacy_dict() → 'markets' 키 존재."""
        result = adapter._mock_fallback()
        d = result.to_legacy_dict()
        assert "markets" in d
        assert isinstance(d["markets"], list)

    def test_legacy_dict_has_is_mock_flag(self, adapter):
        """to_legacy_dict() → 'is_mock' 플래그 존재."""
        result = adapter._mock_fallback()
        d = result.to_legacy_dict()
        assert "is_mock" in d
        assert d["is_mock"] is True

    def test_legacy_dict_market_has_label(self, adapter):
        """markets 항목에 label 키 존재."""
        result = adapter._mock_fallback()
        d = result.to_legacy_dict()
        for m in d["markets"]:
            assert "label" in m
            assert m["label"]  # 비어있지 않아야 함
