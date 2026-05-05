"""src/seller_console/orders/sync_service.py — 주문 동기화 서비스 (Phase 129)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class OrderSyncService:
    """모든 마켓 주문 동기화 + Sheets CRUD 통합 서비스."""

    def __init__(self):
        from .sheets_adapter import OrderSheetsAdapter
        from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
        from src.seller_console.market_adapters.smartstore_adapter import SmartStoreAdapter
        from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
        from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter

        self.sheets = OrderSheetsAdapter()
        self.adapters = {
            "coupang": CoupangAdapter(),
            "smartstore": SmartStoreAdapter(),
            "11st": ElevenAdapter(),
            # Phase 132: kohganemultishop → woocommerce (kohganemultishop.org 실연동)
            "woocommerce": WooCommerceAdapter(),
        }

    def sync_all(self, since: datetime = None) -> dict:
        """모든 마켓 주문 동기화."""
        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        results = {}
        for name, adapter in self.adapters.items():
            try:
                orders = adapter.fetch_orders_unified(since=since)
                upserted = self.sheets.bulk_upsert(orders)
                results[name] = {"fetched": len(orders), "upserted": upserted, "status": "ok"}
                logger.info("동기화 완료 [%s]: %d건", name, len(orders))
            except Exception as exc:
                logger.warning("동기화 실패 [%s]: %s", name, exc)
                results[name] = {"error": str(exc), "status": "fail"}

        return results

    def sync_one(self, marketplace: str, since: datetime = None) -> dict:
        """특정 마켓 주문 동기화."""
        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        adapter = self.adapters.get(marketplace)
        if adapter is None:
            return {"status": "fail", "error": f"알 수 없는 마켓: {marketplace}"}

        try:
            orders = adapter.fetch_orders_unified(since=since)
            upserted = self.sheets.bulk_upsert(orders)
            logger.info("단일 마켓 동기화 완료 [%s]: %d건", marketplace, len(orders))
            return {"fetched": len(orders), "upserted": upserted, "status": "ok"}
        except Exception as exc:
            logger.warning("단일 마켓 동기화 실패 [%s]: %s", marketplace, exc)
            return {"error": str(exc), "status": "fail"}

    def update_tracking(
        self,
        order_id: str,
        marketplace: str,
        courier: str,
        tracking_no: str,
    ) -> bool:
        """운송장 업데이트: 마켓 API + Sheets 동시 갱신."""
        import os

        dry_run = os.getenv("ADAPTER_DRY_RUN", "0") == "1"
        if dry_run:
            logger.info("ADAPTER_DRY_RUN=1 — update_tracking 차단됨 (%s, %s)", marketplace, order_id)
            return True

        # 마켓 API 갱신 시도 (실패해도 Sheets는 갱신)
        adapter = self.adapters.get(marketplace)
        api_ok = False
        if adapter and hasattr(adapter, "update_tracking"):
            try:
                api_ok = adapter.update_tracking(order_id, courier=courier, tracking_no=tracking_no)
            except Exception as exc:
                logger.warning("마켓 API 운송장 등록 실패 [%s]: %s", marketplace, exc)

        # Sheets 갱신
        sheets_ok = self.sheets.update_tracking(order_id, marketplace, courier, tracking_no)

        if not api_ok and not sheets_ok:
            logger.warning("운송장 갱신 모두 실패: %s/%s", marketplace, order_id)
        return sheets_ok or api_ok

    def list_orders(self, filters: dict = None, limit: int = 50, offset: int = 0):
        """Sheets에서 통합 주문 조회."""
        try:
            return self.sheets.query(filters=filters or {}, limit=limit, offset=offset)
        except Exception as exc:
            logger.warning("list_orders 실패: %s", exc)
            return []

    def kpi_summary(self) -> dict:
        """KPI 요약."""
        try:
            return self.sheets.kpi_summary()
        except Exception as exc:
            logger.warning("kpi_summary 실패: %s", exc)
            return {
                "today_new": 0,
                "pending_ship": 0,
                "shipped": 0,
                "returned_exchanged": 0,
                "source": "error",
            }
