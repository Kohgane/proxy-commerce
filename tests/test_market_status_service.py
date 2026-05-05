"""tests/test_market_status_service.py — MarketStatusService 캐시/통합 테스트 (Phase 127).

캐시 TTL, 강제 갱신, sync_marketplace stub 동작 검증.
"""
from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.seller_console.market_status import AllMarketStatus, MarketStatusSummary


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_all_market_status():
    """AllMarketStatus 목업 (sheets source)."""
    return AllMarketStatus(
        summaries=[
            MarketStatusSummary(marketplace="coupang", active=10, out_of_stock=1, error=0, total=11, source="sheets"),
            MarketStatusSummary(marketplace="smartstore", active=8, out_of_stock=2, error=0, total=10, source="sheets"),
        ],
        items=[],
        source="sheets",
    )


@pytest.fixture
def service():
    """MarketStatusService 인스턴스."""
    from src.seller_console.market_status_service import MarketStatusService
    return MarketStatusService(sheet_id="test-sheet-id")


# ---------------------------------------------------------------------------
# 테스트: 기본 동작
# ---------------------------------------------------------------------------

class TestGetAll:
    """get_all() 기본 동작 테스트."""

    def test_get_all_returns_all_market_status(self, service, mock_all_market_status):
        """get_all() → AllMarketStatus 반환."""
        service.sheets_adapter.fetch_all = MagicMock(return_value=mock_all_market_status)

        result = service.get_all()
        assert isinstance(result, AllMarketStatus)
        assert result.source == "sheets"

    def test_get_all_uses_cache(self, service, mock_all_market_status):
        """두 번째 get_all() 호출 시 캐시 사용 (fetch_all 1회만 호출)."""
        service.sheets_adapter.fetch_all = MagicMock(return_value=mock_all_market_status)

        service.get_all()
        service.get_all()

        # fetch_all은 1번만 호출
        assert service.sheets_adapter.fetch_all.call_count == 1

    def test_force_refresh_bypasses_cache(self, service, mock_all_market_status):
        """force_refresh=True 시 캐시 무시하고 fetch_all 재호출."""
        service.sheets_adapter.fetch_all = MagicMock(return_value=mock_all_market_status)

        service.get_all()
        service.get_all(force_refresh=True)

        assert service.sheets_adapter.fetch_all.call_count == 2

    def test_invalidate_cache_clears_cache(self, service, mock_all_market_status):
        """invalidate_cache() 호출 후 재조회 시 fetch_all 재호출."""
        service.sheets_adapter.fetch_all = MagicMock(return_value=mock_all_market_status)

        service.get_all()
        service.invalidate_cache()
        service.get_all()

        assert service.sheets_adapter.fetch_all.call_count == 2

    def test_cache_expires_after_ttl(self, service, mock_all_market_status):
        """TTL(300초) 초과 후 재조회 시 fetch_all 재호출."""
        from src.seller_console import market_status_service as svc_module
        service.sheets_adapter.fetch_all = MagicMock(return_value=mock_all_market_status)

        service.get_all()
        # 캐시 시각을 매우 오래 전으로 조작
        service._cache_at = 0.0
        service.get_all()

        assert service.sheets_adapter.fetch_all.call_count == 2


# ---------------------------------------------------------------------------
# 테스트: sync_marketplace
# ---------------------------------------------------------------------------

class TestSyncMarketplace:
    """sync_marketplace() 테스트."""

    def test_sync_unknown_marketplace_returns_zero(self, service):
        """알 수 없는 마켓 → 0 반환."""
        count = service.sync_marketplace("unknown_market")
        assert count == 0

    def test_sync_known_marketplace_with_stub_returns_zero(self, service):
        """stub 어댑터(빈 리스트 반환) → 0 갱신."""
        # 쿠팡 어댑터는 stub이므로 fetch_inventory() → []
        count = service.sync_marketplace("coupang")
        assert count == 0

    def test_sync_clears_cache(self, service, mock_all_market_status):
        """sync 후 캐시 무효화 확인."""
        service.sheets_adapter.fetch_all = MagicMock(return_value=mock_all_market_status)

        # 첫 캐싱
        service.get_all()
        # mock 어댑터로 items 반환 + bulk_upsert 모킹
        mock_adapter = MagicMock()
        from src.seller_console.market_status import MarketStatusItem
        mock_adapter.fetch_inventory.return_value = [
            MarketStatusItem(marketplace="coupang", product_id="P999", state="active")
        ]
        service.live_adapters["coupang"] = mock_adapter
        service.sheets_adapter.bulk_upsert = MagicMock(return_value=1)

        service.sync_marketplace("coupang")

        # 캐시 무효화 확인 → 다음 get_all은 fetch_all 재호출
        assert service._cache is None


# ---------------------------------------------------------------------------
# 테스트: 어댑터 로드
# ---------------------------------------------------------------------------

class TestAdapterLoad:
    """어댑터 graceful import 테스트."""

    def test_live_adapters_contains_known_markets(self, service):
        """live_adapters에 4개 마켓 키 존재."""
        expected = {"coupang", "smartstore", "11st", "kohganemultishop"}
        assert expected.issubset(set(service.live_adapters.keys()))

    def test_adapter_health_check_returns_stub(self, service):
        """어댑터 health_check() → stub/missing/dry_run/ok/fail 상태 반환 (Phase 131: 자체몰 어댑터는 ok 반환)."""
        for key, adapter in service.live_adapters.items():
            result = adapter.health_check()
            assert "status" in result
            # Phase 128: API 키 미설정 시 "missing" 반환, 기존 stub 모드 어댑터는 "stub"
            # Phase 131: 자체몰(kohganemultishop) 어댑터는 Sheets 없이도 "ok" 반환
            assert result["status"] in ("stub", "missing", "dry_run", "ok", "fail")


# ---------------------------------------------------------------------------
# 테스트: MarketStatusSummary
# ---------------------------------------------------------------------------

class TestMarketStatusSummary:
    """MarketStatusSummary 단위 테스트."""

    def test_label_returns_korean(self):
        """label() → 한글 마켓명 반환."""
        from src.seller_console.market_status import MarketStatusSummary
        s = MarketStatusSummary(marketplace="coupang")
        assert s.label() == "쿠팡"

    def test_label_unknown_returns_marketplace_key(self):
        """알 수 없는 마켓 → 마켓 코드 반환."""
        from src.seller_console.market_status import MarketStatusSummary
        s = MarketStatusSummary(marketplace="unknown_market")
        assert s.label() == "unknown_market"

    def test_to_dict_has_required_keys(self):
        """to_dict() → 필수 키 존재."""
        from src.seller_console.market_status import MarketStatusSummary
        s = MarketStatusSummary(marketplace="coupang", active=5, out_of_stock=1, error=0, total=6)
        d = s.to_dict()
        for key in ["marketplace", "label", "active", "out_of_stock", "error", "total", "source"]:
            assert key in d, f"to_dict()에 '{key}' 키 없음"
