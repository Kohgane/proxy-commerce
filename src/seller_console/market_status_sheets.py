"""src/seller_console/market_status_sheets.py — Google Sheets 기반 마켓 상태 어댑터 (Phase 127).

시트 구조 (워크시트 `catalog`):
| product_id | sku | title | marketplace | state | price_krw | last_synced_at | error_message |

워크시트가 존재하지 않으면 AUTO_BOOTSTRAP_SHEETS=1 환경변수 설정 시 자동 생성 + 헤더 작성.
시트를 열 수 없으면 mock 폴백으로 graceful 처리.
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from .market_status import AllMarketStatus, MarketStatusItem, MarketStatusSummary

logger = logging.getLogger(__name__)

# catalog 워크시트 컬럼 헤더 (순서 고정)
CATALOG_HEADERS = [
    "product_id",
    "sku",
    "title",
    "marketplace",
    "state",
    "price_krw",
    "last_synced_at",
    "error_message",
]

# 상태 정규화 맵 (시트에 다양한 표현이 들어올 수 있음)
_STATE_NORMALIZE: Dict[str, str] = {
    "active": "active",
    "활성": "active",
    "on_sale": "active",
    "out_of_stock": "out_of_stock",
    "품절": "out_of_stock",
    "soldout": "out_of_stock",
    "error": "error",
    "오류": "error",
    "fail": "error",
    "price_anomaly": "price_anomaly",
    "가격이상": "price_anomaly",
    "suspended": "suspended",
    "정지": "suspended",
    "inactive": "suspended",
}


class MarketStatusSheetsAdapter:
    """Google Sheets `proxy_catalog` 시트 기반 마켓 상태 어댑터.

    - 시트에서 catalog 워크시트 읽기 → 마켓별 집계
    - 시트 읽기 실패 시 mock 폴백
    - upsert_item / bulk_upsert로 상태 갱신 지원
    """

    def __init__(self, sheet_id: Optional[str] = None):
        self.sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID", "")

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def fetch_all(self) -> AllMarketStatus:
        """시트의 모든 카탈로그 행 → 집계.

        시트를 열 수 없으면 mock 폴백.
        """
        if not self.sheet_id:
            logger.warning("GOOGLE_SHEET_ID 미설정 — mock 폴백 사용")
            return self._mock_fallback(reason="GOOGLE_SHEET_ID 미설정")

        try:
            from src.utils.sheets import get_or_create_worksheet, open_sheet_object
            sh = open_sheet_object(self.sheet_id)
            ws = get_or_create_worksheet(sh, "catalog", headers=CATALOG_HEADERS)
            rows = ws.get_all_records()
        except Exception as exc:
            logger.warning("Sheets catalog 읽기 실패 (mock 폴백): %s", exc)
            return self._mock_fallback(reason=str(exc))

        items = [self._row_to_item(r) for r in rows if r.get("product_id")]
        if not items:
            # 시트는 열렸지만 데이터 없음 → mock 폴백 (빈 상태 친절히 표시)
            logger.debug("catalog 워크시트 비어있음 — mock 폴백 사용")
            return self._mock_fallback(reason="시트 비어있음")

        summaries = self._summarize(items)
        return AllMarketStatus(
            summaries=summaries,
            items=items,
            source="sheets",
        )

    def upsert_item(self, item: MarketStatusItem) -> bool:
        """단일 상품 상태 갱신 (없으면 추가).

        Returns:
            True: 갱신 성공 / False: 실패
        """
        if not self.sheet_id:
            logger.warning("upsert_item: GOOGLE_SHEET_ID 미설정")
            return False

        try:
            from src.utils.sheets import get_or_create_worksheet, open_sheet_object
            sh = open_sheet_object(self.sheet_id)
            ws = get_or_create_worksheet(sh, "catalog", headers=CATALOG_HEADERS)
            all_rows = ws.get_all_records()

            row_data = self._item_to_row(item)
            # product_id + marketplace 로 기존 행 탐색
            for idx, row in enumerate(all_rows, start=2):  # 헤더가 1행
                if (
                    str(row.get("product_id", "")) == str(item.product_id)
                    and str(row.get("marketplace", "")) == str(item.marketplace)
                ):
                    # 기존 행 덮어쓰기
                    ws.update(f"A{idx}", [row_data])
                    return True

            # 신규 행 추가
            ws.append_row(row_data)
            return True

        except Exception as exc:
            logger.warning("upsert_item 실패: %s", exc)
            return False

    def bulk_upsert(self, items: List[MarketStatusItem]) -> int:
        """일괄 상태 갱신. 변경된 행 수 반환."""
        count = 0
        for item in items:
            if self.upsert_item(item):
                count += 1
        return count

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _row_to_item(self, row: dict) -> MarketStatusItem:
        """시트 행 dict → MarketStatusItem."""
        raw_state = str(row.get("state", "active")).strip().lower()
        state = _STATE_NORMALIZE.get(raw_state, "error")

        last_synced = None
        raw_ts = str(row.get("last_synced_at", "")).strip()
        if raw_ts:
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    last_synced = datetime.strptime(raw_ts, fmt)
                    break
                except ValueError:
                    continue

        price_raw = row.get("price_krw")
        price_krw: Optional[int] = None
        if price_raw not in (None, "", "None"):
            try:
                price_krw = int(float(str(price_raw)))
            except (ValueError, TypeError):
                pass

        return MarketStatusItem(
            marketplace=str(row.get("marketplace", "")).strip(),
            product_id=str(row.get("product_id", "")).strip(),
            state=state,
            sku=str(row.get("sku", "")).strip() or None,
            title=str(row.get("title", "")).strip() or None,
            price_krw=price_krw,
            last_synced_at=last_synced,
            error_message=str(row.get("error_message", "")).strip() or None,
        )

    def _item_to_row(self, item: MarketStatusItem) -> list:
        """MarketStatusItem → 시트 행 리스트 (CATALOG_HEADERS 순서)."""
        return [
            item.product_id,
            item.sku or "",
            item.title or "",
            item.marketplace,
            item.state,
            item.price_krw if item.price_krw is not None else "",
            item.last_synced_at.strftime("%Y-%m-%dT%H:%M:%S") if item.last_synced_at else "",
            item.error_message or "",
        ]

    def _summarize(self, items: List[MarketStatusItem]) -> List[MarketStatusSummary]:
        """마켓별 집계."""
        buckets: Dict[str, MarketStatusSummary] = defaultdict(
            lambda: MarketStatusSummary(marketplace="", source="sheets")
        )

        for item in items:
            mp = item.marketplace
            if mp not in buckets:
                buckets[mp] = MarketStatusSummary(marketplace=mp, source="sheets")

            s = buckets[mp]
            if item.state == "active":
                s.active += 1
            elif item.state == "out_of_stock":
                s.out_of_stock += 1
            elif item.state == "error":
                s.error += 1
            elif item.state == "price_anomaly":
                s.price_anomaly += 1
            elif item.state == "suspended":
                s.suspended += 1
            s.total += 1

            # 최신 동기화 시각
            if item.last_synced_at:
                if s.last_synced_at is None or item.last_synced_at > s.last_synced_at:
                    s.last_synced_at = item.last_synced_at

        return list(buckets.values())

    def _mock_fallback(self, reason: str = "") -> AllMarketStatus:
        """Phase 122 mock 데이터 재사용 (시트 비었거나 권한 깨질 때 폴백)."""
        if reason:
            logger.debug("mock_fallback 사유: %s", reason)
        return AllMarketStatus(
            summaries=[
                MarketStatusSummary(
                    marketplace="coupang",
                    active=45,
                    out_of_stock=3,
                    error=1,
                    total=49,
                    source="mock",
                ),
                MarketStatusSummary(
                    marketplace="smartstore",
                    active=38,
                    out_of_stock=5,
                    error=0,
                    total=43,
                    source="mock",
                ),
                MarketStatusSummary(
                    marketplace="11st",
                    active=22,
                    out_of_stock=2,
                    error=2,
                    total=26,
                    source="mock",
                ),
            ],
            items=[],
            source="mock",
        )
