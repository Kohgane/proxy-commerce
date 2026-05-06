"""src/pricing/history_store.py — 가격 변동 이력 저장소 (Phase 136).

Sheets ``price_history`` 워크시트에 가격 변동 이력 저장/조회/롤백.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

logger = logging.getLogger(__name__)

_WORKSHEET_NAME = "price_history"
_HEADERS = [
    "id", "sku", "old_price_krw", "new_price_krw",
    "delta_pct", "rules_applied", "applied_at", "applied_by", "rolled_back",
]


def _open_ws():
    """price_history 워크시트 열기 (없으면 생성)."""
    try:
        from src.utils.sheets import open_sheet
        ws = open_sheet(_WORKSHEET_NAME)
        existing = ws.row_values(1)
        if not existing:
            ws.append_row(_HEADERS)
        return ws
    except Exception as exc:
        logger.debug("price_history 워크시트 열기 실패: %s", exc)
        return None


class PriceHistoryStore:
    """가격 변동 이력 관리.

    메서드:
        append: 이력 추가
        list_history: 이력 조회 (필터 지원)
        rollback: 특정 이력 항목으로 롤백
    """

    def __init__(self):
        self._memory: List[dict] = []

    def append(
        self,
        sku: str,
        old_price_krw: int,
        new_price_krw: int,
        rules_applied: List[str],
        applied_by: str = "cron",
    ) -> str:
        """가격 변동 이력 추가.

        Returns:
            생성된 이력 ID
        """
        history_id = str(uuid.uuid4())
        if old_price_krw and old_price_krw != 0:
            delta_pct = round((new_price_krw - old_price_krw) / old_price_krw * 100, 2)
        else:
            delta_pct = 0.0

        row = {
            "id": history_id,
            "sku": sku,
            "old_price_krw": old_price_krw,
            "new_price_krw": new_price_krw,
            "delta_pct": delta_pct,
            "rules_applied": ", ".join(rules_applied),
            "applied_at": datetime.now(tz=timezone.utc).isoformat(),
            "applied_by": applied_by,
            "rolled_back": "False",
        }

        ws = _open_ws()
        if ws is None:
            self._memory.append(row)
        else:
            try:
                ws.append_row([row[h] for h in _HEADERS])
            except Exception as exc:
                logger.warning("price_history append 실패: %s", exc)
                self._memory.append(row)

        return history_id

    def list_history(
        self,
        sku: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """이력 조회.

        Args:
            sku: SKU 필터 (None이면 전체)
            date_from: 시작 날짜 (YYYY-MM-DD)
            date_to: 종료 날짜 (YYYY-MM-DD)
            limit: 최대 반환 건수
        """
        ws = _open_ws()
        if ws is None:
            rows = list(self._memory)
        else:
            try:
                rows = ws.get_all_records()
            except Exception as exc:
                logger.warning("price_history list_history 실패: %s", exc)
                rows = list(self._memory)

        # 필터 적용
        filtered = []
        for row in rows:
            if sku and str(row.get("sku", "")) != sku:
                continue
            applied_at = str(row.get("applied_at", ""))
            if date_from and applied_at[:10] < date_from:
                continue
            if date_to and applied_at[:10] > date_to:
                continue
            filtered.append(row)

        # 최신순 정렬
        filtered.sort(key=lambda r: str(r.get("applied_at", "")), reverse=True)
        return filtered[:limit]

    def get_by_id(self, history_id: str) -> Optional[dict]:
        """ID로 이력 항목 조회."""
        ws = _open_ws()
        rows = []
        if ws:
            try:
                rows = ws.get_all_records()
            except Exception:
                rows = list(self._memory)
        else:
            rows = list(self._memory)

        for row in rows:
            if str(row.get("id", "")) == history_id:
                return row
        return None

    def rollback(self, history_id: str, applied_by: str = "manual") -> Optional[dict]:
        """특정 이력 항목의 이전 가격으로 롤백.

        Returns:
            새로 생성된 이력 항목 dict (성공 시)
        """
        item = self.get_by_id(history_id)
        if not item:
            return None

        sku = str(item.get("sku", ""))
        old_price = int(item.get("old_price_krw", 0))
        current_price = int(item.get("new_price_krw", 0))

        if not sku or not old_price:
            return None

        # 마켓별 가격 복원
        try:
            from src.pricing.engine import PricingEngine
            engine = PricingEngine()
            adapters = engine._get_market_adapters()
            for name, adapter in adapters.items():
                try:
                    adapter.update_price(sku, old_price)
                except Exception as exc:
                    logger.warning("롤백 마켓 업데이트 실패 (%s, %s): %s", name, sku, exc)
        except Exception as exc:
            logger.warning("롤백 엔진 로드 실패: %s", exc)

        # 롤백 이력 기록
        new_id = self.append(
            sku=sku,
            old_price_krw=current_price,
            new_price_krw=old_price,
            rules_applied=["rollback"],
            applied_by=applied_by,
        )

        # 원본 항목에 rolled_back 표시
        self._mark_rolled_back(history_id)

        return self.get_by_id(new_id)

    def _mark_rolled_back(self, history_id: str):
        """rolled_back 컬럼을 True로 표시."""
        ws = _open_ws()
        if ws is None:
            for row in self._memory:
                if row.get("id") == history_id:
                    row["rolled_back"] = "True"
            return
        try:
            rows = ws.get_all_records()
            headers = ws.row_values(1)
            rolled_back_col = headers.index("rolled_back") + 1 if "rolled_back" in headers else None
            for i, row in enumerate(rows):
                if str(row.get("id", "")) == history_id and rolled_back_col:
                    ws.update_cell(i + 2, rolled_back_col, "True")
                    break
        except Exception as exc:
            logger.warning("rolled_back 표시 실패: %s", exc)
