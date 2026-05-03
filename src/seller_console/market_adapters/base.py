"""src/seller_console/market_adapters/base.py — 마켓 어댑터 기본 인터페이스 (Phase 127).

실제 마켓 API에서 상품 상태를 가져오는 어댑터 인터페이스.
각 마켓별 구현은 서브클래스로.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from src.seller_console.market_status import MarketStatusItem


class MarketAdapter(ABC):
    """마켓 어댑터 추상 기반 클래스."""

    marketplace: str = ""

    @abstractmethod
    def fetch_inventory(self) -> List[MarketStatusItem]:
        """API에서 재고/상품 상태 fetch.

        Returns:
            MarketStatusItem 리스트 (빈 리스트 = 미구현 또는 연동 실패)
        """
        ...

    @abstractmethod
    def health_check(self) -> dict:
        """API 인증/할당량 상태 확인.

        Returns:
            {"status": "ok"|"fail", "detail": str}
        """
        ...
