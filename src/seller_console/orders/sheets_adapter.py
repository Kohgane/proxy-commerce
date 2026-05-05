"""src/seller_console/orders/sheets_adapter.py — Google Sheets 주문 CRUD 어댑터 (Phase 129).

워크시트 `orders` 컬럼:
order_id | marketplace | status | placed_at | paid_at |
buyer_name_masked | buyer_phone_masked | buyer_address_masked |
total_krw | shipping_fee_krw | items_json |
courier | tracking_no | shipped_at |
landed_cost_krw | margin_krw | margin_pct | last_synced_at | notes

GOOGLE_SHEET_ID 미설정 시 graceful 폴백.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from .models import OrderLineItem, OrderStatus, UnifiedOrder

logger = logging.getLogger(__name__)

# 워크시트 컬럼 헤더 (순서 고정)
ORDERS_HEADERS = [
    "order_id",
    "marketplace",
    "status",
    "placed_at",
    "paid_at",
    "buyer_name_masked",
    "buyer_phone_masked",
    "buyer_address_masked",
    "total_krw",
    "shipping_fee_krw",
    "items_json",
    "courier",
    "tracking_no",
    "shipped_at",
    "landed_cost_krw",
    "margin_krw",
    "margin_pct",
    "last_synced_at",
    "notes",
]


def _parse_dt(raw: str) -> Optional[datetime]:
    """ISO 날짜/시각 문자열 → datetime (실패 시 None)."""
    if not raw or str(raw).strip() in ("", "None"):
        return None
    raw = str(raw).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _parse_dec(raw) -> Optional[Decimal]:
    """숫자 문자열 → Decimal (실패 시 None)."""
    if raw in (None, "", "None"):
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


class OrderSheetsAdapter:
    """Google Sheets `orders` 워크시트 CRUD 어댑터."""

    def __init__(self, sheet_id: Optional[str] = None):
        self.sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID", "")

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def bulk_upsert(self, orders: List[UnifiedOrder]) -> int:
        """(order_id, marketplace) 복합 키로 upsert. 처리된 행 수 반환."""
        if not self.sheet_id:
            logger.warning("bulk_upsert: GOOGLE_SHEET_ID 미설정 — 건너뜀")
            return 0

        try:
            from src.utils.sheets import get_or_create_worksheet, open_sheet_object
            sh = open_sheet_object(self.sheet_id)
            ws = get_or_create_worksheet(sh, "orders", headers=ORDERS_HEADERS)
            all_rows = ws.get_all_records()

            # (order_id, marketplace) → 행 인덱스 매핑 (헤더가 1행이므로 +2)
            existing: Dict[tuple, int] = {}
            for idx, row in enumerate(all_rows, start=2):
                key = (str(row.get("order_id", "")), str(row.get("marketplace", "")))
                existing[key] = idx

            count = 0
            for order in orders:
                row_data = self._order_to_row(order)
                key = (order.order_id, order.marketplace)
                if key in existing:
                    ws.update(f"A{existing[key]}", [row_data])
                else:
                    ws.append_row(row_data)
                    # 다음 행 번호 추정 (동시 삽입 시 충돌 가능성 낮음)
                    existing[key] = len(all_rows) + 2 + count
                count += 1
            return count
        except Exception as exc:
            logger.warning("bulk_upsert 실패: %s", exc)
            return 0

    def query(self, filters: dict = None, limit: int = 50, offset: int = 0) -> List[UnifiedOrder]:
        """필터/정렬/페이지네이션으로 주문 조회."""
        if not self.sheet_id:
            logger.warning("query: GOOGLE_SHEET_ID 미설정 — 빈 목록 반환")
            return []

        filters = filters or {}
        try:
            from src.utils.sheets import get_or_create_worksheet, open_sheet_object
            sh = open_sheet_object(self.sheet_id)
            ws = get_or_create_worksheet(sh, "orders", headers=ORDERS_HEADERS)
            rows = ws.get_all_records()
        except Exception as exc:
            logger.warning("query: Sheets 읽기 실패: %s", exc)
            return []

        orders = [self._row_to_order(r) for r in rows if r.get("order_id")]

        # 필터 적용
        if filters.get("marketplace"):
            mp_list = filters["marketplace"] if isinstance(filters["marketplace"], list) else [filters["marketplace"]]
            orders = [o for o in orders if o.marketplace in mp_list]
        if filters.get("status"):
            st_list = filters["status"] if isinstance(filters["status"], list) else [filters["status"]]
            orders = [o for o in orders if (o.status.value if isinstance(o.status, OrderStatus) else o.status) in st_list]
        if filters.get("search"):
            q = filters["search"].lower()
            orders = [o for o in orders if q in o.order_id.lower() or (o.buyer_name_masked or "").lower().find(q) >= 0]
        if filters.get("date_from"):
            dt_from = _parse_dt(str(filters["date_from"]))
            if dt_from:
                orders = [o for o in orders if o.placed_at and o.placed_at >= dt_from]
        if filters.get("date_to"):
            dt_to = _parse_dt(str(filters["date_to"]))
            if dt_to:
                orders = [o for o in orders if o.placed_at and o.placed_at <= dt_to]

        # 최신 주문 먼저 정렬
        orders.sort(key=lambda o: o.placed_at or datetime.min, reverse=True)

        return orders[offset: offset + limit]

    def update_tracking(
        self,
        order_id: str,
        marketplace: str,
        courier: str,
        tracking_no: str,
    ) -> bool:
        """운송장 번호 갱신. 성공 시 True."""
        if not self.sheet_id:
            logger.warning("update_tracking: GOOGLE_SHEET_ID 미설정")
            return False

        try:
            from src.utils.sheets import get_or_create_worksheet, open_sheet_object
            sh = open_sheet_object(self.sheet_id)
            ws = get_or_create_worksheet(sh, "orders", headers=ORDERS_HEADERS)
            rows = ws.get_all_records()

            courier_col = ORDERS_HEADERS.index("courier") + 1   # 1-based
            tracking_col = ORDERS_HEADERS.index("tracking_no") + 1
            status_col = ORDERS_HEADERS.index("status") + 1

            for idx, row in enumerate(rows, start=2):
                if (
                    str(row.get("order_id", "")) == order_id
                    and str(row.get("marketplace", "")) == marketplace
                ):
                    ws.update_cell(idx, courier_col, courier)
                    ws.update_cell(idx, tracking_col, tracking_no)
                    ws.update_cell(idx, status_col, OrderStatus.SHIPPED.value)
                    return True
            logger.warning("update_tracking: 주문 찾을 수 없음 (%s, %s)", order_id, marketplace)
            return False
        except Exception as exc:
            logger.warning("update_tracking 실패: %s", exc)
            return False

    def kpi_summary(self) -> dict:
        """KPI 요약: today_new, pending_ship, shipped, returned_exchanged."""
        fallback = {
            "today_new": 0,
            "pending_ship": 0,
            "shipped": 0,
            "returned_exchanged": 0,
            "source": "fallback",
        }
        if not self.sheet_id:
            logger.warning("kpi_summary: GOOGLE_SHEET_ID 미설정 — mock 반환")
            return {**fallback, "source": "mock"}

        try:
            from src.utils.sheets import get_or_create_worksheet, open_sheet_object
            sh = open_sheet_object(self.sheet_id)
            ws = get_or_create_worksheet(sh, "orders", headers=ORDERS_HEADERS)
            rows = ws.get_all_records()
        except Exception as exc:
            logger.warning("kpi_summary: Sheets 읽기 실패: %s", exc)
            return fallback

        today = date.today().isoformat()
        today_new = 0
        pending_ship = 0
        shipped = 0
        returned_exchanged = 0

        for row in rows:
            if not row.get("order_id"):
                continue
            status = str(row.get("status", "")).strip()
            placed = str(row.get("placed_at", ""))[:10]
            if placed == today and status in (OrderStatus.NEW.value, OrderStatus.PAID.value):
                today_new += 1
            if status in (OrderStatus.PAID.value, OrderStatus.PREPARING.value):
                pending_ship += 1
            if status == OrderStatus.SHIPPED.value:
                shipped += 1
            if status in (OrderStatus.RETURNED.value, OrderStatus.EXCHANGED.value, OrderStatus.REFUND_REQUESTED.value):
                returned_exchanged += 1

        return {
            "today_new": today_new,
            "pending_ship": pending_ship,
            "shipped": shipped,
            "returned_exchanged": returned_exchanged,
            "source": "sheets",
        }

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _order_to_row(self, order: UnifiedOrder) -> list:
        """UnifiedOrder → 시트 행 (ORDERS_HEADERS 순서)."""
        status_val = order.status.value if isinstance(order.status, OrderStatus) else str(order.status)
        items_json = json.dumps(
            [
                {
                    "sku": it.sku,
                    "title": it.title,
                    "qty": it.qty,
                    "unit_price_krw": str(it.unit_price_krw),
                    "options": it.options,
                }
                for it in order.items
            ],
            ensure_ascii=False,
        )
        return [
            order.order_id,
            order.marketplace,
            status_val,
            order.placed_at.strftime("%Y-%m-%dT%H:%M:%S") if order.placed_at else "",
            order.paid_at.strftime("%Y-%m-%dT%H:%M:%S") if order.paid_at else "",
            order.buyer_name_masked or "",
            order.buyer_phone_masked or "",
            order.buyer_address_masked or "",
            str(order.total_krw),
            str(order.shipping_fee_krw),
            items_json,
            order.courier or "",
            order.tracking_no or "",
            order.shipped_at.strftime("%Y-%m-%dT%H:%M:%S") if order.shipped_at else "",
            str(order.landed_cost_krw) if order.landed_cost_krw is not None else "",
            str(order.margin_krw) if order.margin_krw is not None else "",
            str(order.margin_pct) if order.margin_pct is not None else "",
            datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
            order.notes or "",
        ]

    def _row_to_order(self, row: dict) -> UnifiedOrder:
        """시트 행 dict → UnifiedOrder."""
        raw_status = str(row.get("status", "new")).strip().lower()
        try:
            status = OrderStatus(raw_status)
        except ValueError:
            status = OrderStatus.NEW

        # items_json 파싱
        items = []
        raw_items = row.get("items_json", "")
        if raw_items:
            try:
                parsed = json.loads(str(raw_items))
                for it in parsed:
                    items.append(OrderLineItem(
                        sku=str(it.get("sku", "")),
                        title=str(it.get("title", "")),
                        qty=int(it.get("qty", 1)),
                        unit_price_krw=Decimal(str(it.get("unit_price_krw", "0"))),
                        options=it.get("options", {}),
                    ))
            except Exception:
                pass

        return UnifiedOrder(
            order_id=str(row.get("order_id", "")),
            marketplace=str(row.get("marketplace", "")),
            status=status,
            placed_at=_parse_dt(str(row.get("placed_at", ""))) or datetime.utcnow(),
            paid_at=_parse_dt(str(row.get("paid_at", ""))),
            buyer_name_masked=str(row.get("buyer_name_masked", "")) or None,
            buyer_phone_masked=str(row.get("buyer_phone_masked", "")) or None,
            buyer_address_masked=str(row.get("buyer_address_masked", "")) or None,
            total_krw=_parse_dec(row.get("total_krw")) or Decimal(0),
            shipping_fee_krw=_parse_dec(row.get("shipping_fee_krw")) or Decimal(0),
            items=items,
            courier=str(row.get("courier", "")) or None,
            tracking_no=str(row.get("tracking_no", "")) or None,
            shipped_at=_parse_dt(str(row.get("shipped_at", ""))),
            landed_cost_krw=_parse_dec(row.get("landed_cost_krw")),
            margin_krw=_parse_dec(row.get("margin_krw")),
            margin_pct=_parse_dec(row.get("margin_pct")),
            last_synced_at=_parse_dt(str(row.get("last_synced_at", ""))),
            notes=str(row.get("notes", "")),
        )
