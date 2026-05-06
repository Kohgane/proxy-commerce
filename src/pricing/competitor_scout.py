"""src/pricing/competitor_scout.py — 경쟁사 가격 모니터링 (Phase 136, Optional P3).

네이버 검색 API로 동일/유사 상품의 경쟁사 최저가를 수집하여
Sheets ``competitor_prices`` 워크시트에 저장.

키 미설정 시 graceful 비활성.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

logger = logging.getLogger(__name__)

_WORKSHEET_NAME = "competitor_prices"
_HEADERS = ["sku", "query", "competitor_name", "competitor_price_krw", "link", "collected_at"]


def _api_active() -> bool:
    return bool(os.getenv("NAVER_COMMERCE_CLIENT_ID") or os.getenv("NAVER_SEARCH_CLIENT_ID"))


def _open_ws():
    try:
        from src.utils.sheets import open_sheet
        ws = open_sheet(_WORKSHEET_NAME)
        existing = ws.row_values(1)
        if not existing:
            ws.append_row(_HEADERS)
        return ws
    except Exception as exc:
        logger.debug("competitor_prices 워크시트 열기 실패: %s", exc)
        return None


class CompetitorScout:
    """경쟁사 가격 수집기.

    네이버 쇼핑 검색 API로 같은 상품명/브랜드 검색 → 최저가 수집.
    """

    def collect_for_sku(self, sku: str, query: str, limit: int = 5) -> List[dict]:
        """단일 SKU에 대해 경쟁사 가격 수집.

        Args:
            sku: 상품 SKU
            query: 네이버 쇼핑 검색 쿼리 (상품명 + 브랜드)
            limit: 최대 수집 건수

        Returns:
            경쟁사 가격 목록 [{"competitor_name": ..., "price": ..., "link": ...}, ...]
        """
        if not _api_active():
            logger.debug("네이버 API 미설정 — competitor_scout 비활성")
            return []

        if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
            return []

        client_id = os.getenv("NAVER_COMMERCE_CLIENT_ID") or os.getenv("NAVER_SEARCH_CLIENT_ID", "")
        client_secret = (
            os.getenv("NAVER_COMMERCE_CLIENT_SECRET")
            or os.getenv("NAVER_SEARCH_CLIENT_SECRET", "")
        )

        try:
            import requests
            resp = requests.get(
                "https://openapi.naver.com/v1/search/shop.json",
                params={"query": query, "display": limit, "sort": "price"},
                headers={
                    "X-Naver-Client-Id": client_id,
                    "X-Naver-Client-Secret": client_secret,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                logger.warning("네이버 쇼핑 검색 실패 HTTP %s", resp.status_code)
                return []

            items = resp.json().get("items", [])
            results = []
            for item in items[:limit]:
                price_str = item.get("lprice") or item.get("price", "0")
                try:
                    price = int(price_str)
                except (ValueError, TypeError):
                    continue
                results.append({
                    "sku": sku,
                    "query": query,
                    "competitor_name": item.get("mallName", "네이버쇼핑"),
                    "competitor_price_krw": price,
                    "link": item.get("link", ""),
                    "collected_at": datetime.now(tz=timezone.utc).isoformat(),
                })
            return results

        except Exception as exc:
            logger.warning("경쟁사 가격 수집 오류 (%s): %s", sku, exc)
            return []

    def save(self, items: List[dict]):
        """수집 결과를 Sheets에 저장 (이전 동일 SKU 데이터 덮어쓰기)."""
        ws = _open_ws()
        if ws is None:
            return

        # 기존 행에서 같은 SKU 삭제 후 재삽입
        skus_to_update = {item["sku"] for item in items}
        try:
            existing = ws.get_all_records()
            # 역순으로 삭제 (행 번호 밀림 방지)
            for i in range(len(existing) - 1, -1, -1):
                if existing[i].get("sku") in skus_to_update:
                    ws.delete_rows(i + 2)
        except Exception as exc:
            logger.warning("경쟁사 기존 데이터 삭제 실패: %s", exc)

        for item in items:
            try:
                ws.append_row([item.get(h, "") for h in _HEADERS])
            except Exception as exc:
                logger.warning("경쟁사 가격 저장 실패: %s", exc)

    def run_all(self) -> dict:
        """카탈로그 전체 SKU에 대해 경쟁사 가격 수집."""
        if not _api_active():
            return {"status": "disabled", "reason": "NAVER API 미설정"}

        try:
            from src.utils.sheets import open_sheet
            ws = open_sheet("catalog")
            rows = ws.get_all_records()
            active = [r for r in rows if str(r.get("status", "")).strip().lower() == "active"]
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

        all_items = []
        collected = 0
        for row in active:
            sku = str(row.get("sku", "")).strip()
            title = str(row.get("title_ko") or row.get("title_en") or "").strip()
            if not sku or not title:
                continue
            items = self.collect_for_sku(sku, title)
            all_items.extend(items)
            if items:
                collected += 1

        self.save(all_items)
        return {"status": "ok", "skus_collected": collected, "items": len(all_items)}
