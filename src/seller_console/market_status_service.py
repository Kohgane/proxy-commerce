"""src/seller_console/market_status_service.py — 마켓 상태 통합 서비스 (Phase 127).

- Sheets 어댑터 우선
- 실시간 어댑터(Phase 130에서 활성화) 조합
- 캐시 5분
- 셀러 콘솔 위젯 및 API에 노출
"""
from __future__ import annotations

import logging
from time import time
from typing import Dict, Optional

from .market_status import AllMarketStatus
from .market_status_sheets import MarketStatusSheetsAdapter

logger = logging.getLogger(__name__)

# 캐시 TTL (초)
_CACHE_TTL = 300


class MarketStatusService:
    """마켓 상태 통합 서비스.

    Sheets 어댑터로 데이터를 가져오고 5분간 캐시한다.
    Phase 130에서 live_adapters를 통해 실시간 마켓 API 연동 예정.
    """

    def __init__(self, sheet_id: Optional[str] = None):
        self.sheets_adapter = MarketStatusSheetsAdapter(sheet_id=sheet_id)
        self.live_adapters: Dict[str, object] = self._build_live_adapters()
        self._cache: Optional[AllMarketStatus] = None
        self._cache_at: float = 0.0

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def get_all(self, force_refresh: bool = False) -> AllMarketStatus:
        """모든 마켓 상태 반환.

        5분 캐시 적용. force_refresh=True 시 강제 갱신.
        """
        if (
            not force_refresh
            and self._cache is not None
            and (time() - self._cache_at) < _CACHE_TTL
        ):
            return self._cache

        result = self.sheets_adapter.fetch_all()
        self._cache = result
        self._cache_at = time()
        return result

    def sync_marketplace(self, marketplace: str) -> int:
        """라이브 어댑터에서 fetch → Sheets에 upsert.

        현재 Phase 127에서는 모든 어댑터가 stub이므로 0 반환.
        Phase 130에서 실 API 연동 후 작동.

        Returns:
            변경된 행 수
        """
        adapter = self.live_adapters.get(marketplace)
        if adapter is None:
            logger.warning("알 수 없는 마켓: %s", marketplace)
            return 0

        try:
            items = adapter.fetch_inventory()  # type: ignore[attr-defined]
        except Exception as exc:
            logger.warning("live_adapter.fetch_inventory 실패 (%s): %s", marketplace, exc)
            items = []

        if items:
            count = self.sheets_adapter.bulk_upsert(items)
            self._cache = None  # 캐시 무효화
            return count

        return 0

    def invalidate_cache(self) -> None:
        """캐시 강제 무효화."""
        self._cache = None
        self._cache_at = 0.0

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    @staticmethod
    def _build_live_adapters() -> Dict[str, object]:
        """라이브 어댑터 인스턴스 딕셔너리 빌드 (graceful import)."""
        adapters: Dict[str, object] = {}
        _adapter_specs = [
            ("coupang", "src.seller_console.market_adapters.coupang_adapter", "CoupangAdapter"),
            ("smartstore", "src.seller_console.market_adapters.smartstore_adapter", "SmartStoreAdapter"),
            ("11st", "src.seller_console.market_adapters.eleven_adapter", "ElevenAdapter"),
            ("kohganemultishop", "src.seller_console.market_adapters.kohgane_multishop_adapter", "KohganeMultishopAdapter"),
        ]
        for key, module_path, class_name in _adapter_specs:
            try:
                import importlib
                mod = importlib.import_module(module_path)
                cls = getattr(mod, class_name)
                adapters[key] = cls()
            except Exception as exc:
                logger.debug("어댑터 로드 실패 (%s): %s", key, exc)
        return adapters
