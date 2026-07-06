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
from datetime import datetime, date, timezone
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

from .models import OrderLineItem, OrderStatus, UnifiedOrder

logger = logging.getLogger(__name__)


def _pg_orders():
    """Postgres 백엔드 활성 시 orders_pg 반환(스키마 1회), 아니면 None(인메모리)."""
    try:
        from src.db import pg as _pgmod
        if _pgmod.pg_enabled():
            _pgmod.init_schema()
            from src.db import orders_pg as _op
            return _op
    except Exception as exc:
        logger.warning("PG 주문 백엔드 확인 실패 — 인메모리 폴백: %s", exc)
    return None


class _InMemoryOrders:
    """PG 미설정(개발/테스트) 전용 인메모리 주문 저장소 — orders_pg와 동일 행-dict API."""

    def __init__(self):
        self.rows: list[dict] = []   # ORDERS_HEADERS 키 dict

    def _find(self, order_id, marketplace):
        for r in self.rows:
            if str(r.get("order_id", "")) == str(order_id) and str(r.get("marketplace", "")) == str(marketplace):
                return r
        return None

    def upsert_rows(self, rows: list) -> int:
        n = 0
        for r in rows or []:
            ex = self._find(r.get("order_id"), r.get("marketplace"))
            if ex is not None:
                ex.update(r)
            else:
                self.rows.append(dict(r))
            n += 1
        return n

    def all_row_dicts(self) -> list:
        return [dict(r) for r in self.rows]

    def update_tracking(self, order_id, marketplace, courier, tracking_no, shipped_status) -> bool:
        r = self._find(order_id, marketplace)
        if r is None:
            return False
        r.update({"courier": courier, "tracking_no": tracking_no, "status": shipped_status})
        return True

    def update_status(self, order_id, marketplace, status, note, last_synced_at) -> bool:
        r = self._find(order_id, marketplace)
        if r is None:
            return False
        r["status"] = status
        if note:
            prev = str(r.get("notes", "") or "")
            r["notes"] = (f"{prev} | {note}" if prev.strip() else note)[-2000:]
        r["last_synced_at"] = last_synced_at
        return True


_MEM = _InMemoryOrders()


def _order_backend():
    """PG면 orders_pg, 아니면 인메모리(개발/테스트). Sheets 폴백은 제거됨(PG-only 전환)."""
    return _pg_orders() or _MEM

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


def _fallback_placed_at(order_id: str) -> datetime:
    """placed_at 파싱 실패 시 경고 후 현재 UTC 시각 반환."""
    logger.warning("placed_at 파싱 실패 — order_id=%s, utcnow() 사용", order_id)
    return datetime.utcnow()


class OrderSheetsAdapter:
    """Google Sheets `orders` 워크시트 CRUD 어댑터."""

    def __init__(self, sheet_id: Optional[str] = None):
        self.sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID", "")

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def bulk_upsert(self, orders: List[UnifiedOrder]) -> int:
        """(order_id, marketplace) 복합 키로 upsert. 처리된 행 수 반환."""
        _b = _order_backend()
        rows = [dict(zip(ORDERS_HEADERS, self._order_to_row(o))) for o in (orders or [])]
        return _b.upsert_rows(rows)

    def query(self, filters: dict = None, limit: int = 50, offset: int = 0) -> List[UnifiedOrder]:
        """필터/정렬/페이지네이션으로 주문 조회."""
        filters = filters or {}
        rows = _order_backend().all_row_dicts()
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
        ok = _order_backend().update_tracking(order_id, marketplace, courier, tracking_no, OrderStatus.SHIPPED.value)
        if not ok:
            logger.warning("update_tracking: 주문 찾을 수 없음 (%s, %s)", order_id, marketplace)
        return ok

    def update_status(
        self,
        order_id: str,
        marketplace: str,
        status: str,
        note: str = "",
    ) -> bool:
        """주문 상태/메모 갱신. 성공 시 True."""
        status = str(status or "").strip().lower()
        if not status:
            return False
        updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        ok = _order_backend().update_status(order_id, marketplace, status, note, updated_at)
        if not ok:
            logger.warning("update_status: 주문 찾을 수 없음 (%s, %s)", order_id, marketplace)
        return ok

    def kpi_summary(self) -> dict:
        """KPI 요약: today_new, pending_ship, shipped, returned_exchanged."""
        rows = _order_backend().all_row_dicts()

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
            "source": "backend",
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
            placed_at=_parse_dt(str(row.get("placed_at", ""))) or _fallback_placed_at(row.get("order_id", "")),
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

    # ------------------------------------------------------------------
    # 자체몰 체크아웃 전용 raw dict 인터페이스 (Phase 131)
    # ------------------------------------------------------------------

    def get_all_rows(self) -> list:
        """orders의 모든 행을 raw dict(ORDERS_HEADERS 키) 목록으로 반환. (PG면 PG, 아니면 인메모리.)"""
        return _order_backend().all_row_dicts()

    def upsert_row(self, row: dict) -> bool:
        """raw dict로 orders 행 upsert (order_id 기준). 자체몰 체크아웃 주문 생성/갱신용.

        (order_id만 주어져도 marketplace 공란으로 upsert — 기존 자체몰 계약 유지.)
        """
        norm = {h: str(row.get(h, "")) for h in ORDERS_HEADERS}
        return _order_backend().upsert_rows([norm]) > 0
