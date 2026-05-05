"""src/seller_console/market_adapters/kohgane_multishop_adapter.py — 코가네멀티샵 어댑터 (Phase 131).

자체몰 어댑터 — ShopCatalog + orders 워크시트 연동.
- fetch_inventory() → ShopCatalog.list_all() → MarketStatusItem 매핑
- upload_product()  → catalog 워크시트에 upsert
- fetch_orders()    → orders 워크시트에서 marketplace=kohganemultishop 필터
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

from src.seller_console.market_status import MarketStatusItem
from .base import MarketAdapter

logger = logging.getLogger(__name__)


class KohganeMultishopAdapter(MarketAdapter):
    """코가네 자체몰 어댑터 (Phase 131 — ShopCatalog 연동)."""

    marketplace = "kohganemultishop"

    def fetch_inventory(self) -> List[MarketStatusItem]:
        """ShopCatalog에서 재고 조회."""
        try:
            from src.shop.catalog import get_catalog
            catalog = get_catalog()
            products = catalog.list_all()
            items = []
            for p in products:
                items.append(MarketStatusItem(
                    marketplace="kohganemultishop",
                    product_id=p.sku or p.slug,
                    state="active",
                    sku=p.sku or None,
                    title=p.title_ko,
                    price_krw=p.sale_price_krw if p.sale_price_krw else p.price_krw,
                ))
            return items
        except Exception as exc:
            logger.warning("코가네멀티샵 fetch_inventory 실패: %s", exc)
            return []

    def upload_product(self, product: dict) -> dict:
        """catalog 워크시트에 상품 upsert.

        product: {slug, title_ko, price_krw, ...}
        """
        if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
            return {"status": "dry_run", "detail": "ADAPTER_DRY_RUN=1 — API 호출 차단"}

        try:
            sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
            if not sheet_id:
                return {"status": "stub", "detail": "GOOGLE_SHEET_ID 미설정"}

            from src.utils.sheets import open_sheet_object
            sh = open_sheet_object(sheet_id)
            try:
                ws = sh.worksheet("catalog")
            except Exception:
                from src.shop.catalog import CATALOG_HEADERS
                ws = sh.add_worksheet(title="catalog", rows=100, cols=len(CATALOG_HEADERS))
                ws.update("A1", [CATALOG_HEADERS])

            from src.shop.catalog import CATALOG_HEADERS
            # 기존 slug 검색
            records = ws.get_all_records()
            slug = product.get("slug", "")
            row_idx = None
            for i, row in enumerate(records, start=2):
                if str(row.get("slug", "")) == slug:
                    row_idx = i
                    break

            row_data = [product.get(h, "") for h in CATALOG_HEADERS]
            if row_idx:
                ws.update(f"A{row_idx}", [row_data])
            else:
                ws.append_row(row_data)

            # 카탈로그 캐시 무효화
            try:
                from src.shop.catalog import get_catalog
                get_catalog().invalidate()
            except Exception:
                pass

            return {"status": "ok", "slug": slug}
        except Exception as exc:
            logger.warning("코가네멀티샵 upload_product 실패: %s", exc)
            return {"status": "error", "detail": str(exc)}

    def fetch_orders_unified(self, since=None, until=None) -> list:
        """orders 워크시트에서 kohganemultishop 주문 조회."""
        try:
            from src.seller_console.orders.sheets_adapter import OrderSheetsAdapter
            sheets = OrderSheetsAdapter()
            rows = sheets.get_all_rows()
            orders = []
            for row in rows:
                if str(row.get("marketplace", "")).strip().lower() == "kohganemultishop":
                    orders.append(row)
            return orders
        except Exception as exc:
            logger.warning("코가네멀티샵 fetch_orders_unified 실패: %s", exc)
            return []

    def update_tracking(self, order_id: str, courier: str = "", tracking_no: str = "") -> bool:
        """자체몰 운송장 등록 — orders 워크시트 갱신."""
        if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
            logger.info("ADAPTER_DRY_RUN=1 — update_tracking 차단")
            return True
        try:
            from src.seller_console.orders.sheets_adapter import OrderSheetsAdapter
            sheets = OrderSheetsAdapter()
            rows = sheets.get_all_rows()
            for row in rows:
                if str(row.get("order_id", "")) == order_id:
                    row["courier"] = courier
                    row["tracking_no"] = tracking_no
                    sheets.upsert_row(row)
                    return True
            logger.warning("코가네멀티샵 update_tracking: 주문 없음 %s", order_id)
            return False
        except Exception as exc:
            logger.warning("코가네멀티샵 update_tracking 실패: %s", exc)
            return False

    def health_check(self) -> dict:
        """자체몰 상태 확인."""
        try:
            from src.shop.catalog import get_catalog
            catalog = get_catalog()
            products = catalog.list_all()
            return {
                "status": "ok",
                "detail": f"ShopCatalog 연결됨 — 상품 {len(products)}개",
            }
        except Exception as exc:
            return {"status": "fail", "detail": str(exc)[:200]}

