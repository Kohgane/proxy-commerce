"""src/inventory/auto_reorder.py — Phase 142 자동 리오더 엔진.

BI 분석(Phase 141)에서 추출한 "재고 임박" SKU 기반으로 권장 발주량을 계산하고
소싱처별 발주서를 자동 생성한다.

환경변수:
  AUTO_REORDER_ENABLED=1          활성화 (기본: 0)
  AUTO_REORDER_AUTO_PLACE=0       자동 발주 (기본: 0, 1시 승인 없이 발주)
  AUTO_REORDER_DAILY_BUDGET_KRW   일일 발주 예산 (기본: 500000원)
  AUTO_REORDER_SAFETY_DAYS        안전 재고 일수 (기본: 14일)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("AUTO_REORDER_ENABLED", "0") == "1"
_AUTO_PLACE = os.getenv("AUTO_REORDER_AUTO_PLACE", "0") == "1"
_DAILY_BUDGET_KRW = int(os.getenv("AUTO_REORDER_DAILY_BUDGET_KRW", "500000"))
_SAFETY_DAYS = int(os.getenv("AUTO_REORDER_SAFETY_DAYS", "14"))


@dataclass
class ReorderItem:
    """권장 발주 항목."""

    sku: str
    title: str
    vendor: str
    current_stock: int
    sales_velocity_daily: float  # 하루 평균 판매량
    lead_time_days: int = 7      # 리드타임(일)
    unit_cost_krw: int = 0
    recommended_qty: int = 0
    status: str = "pending"      # pending / approved / placed / rejected
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "sku": self.sku,
            "title": self.title,
            "vendor": self.vendor,
            "current_stock": self.current_stock,
            "sales_velocity_daily": self.sales_velocity_daily,
            "lead_time_days": self.lead_time_days,
            "unit_cost_krw": self.unit_cost_krw,
            "recommended_qty": self.recommended_qty,
            "estimated_cost_krw": self.unit_cost_krw * self.recommended_qty,
            "status": self.status,
            "created_at": self.created_at,
        }


def _calc_recommended_qty(item: ReorderItem) -> int:
    """권장 발주량 계산.

    공식: (리드타임 + 안전재고일수) × 일평균 판매량 - 현재 재고
    최소 1개, 음수면 0.
    """
    required = (item.lead_time_days + _SAFETY_DAYS) * item.sales_velocity_daily
    qty = max(0, int(required - item.current_stock) + 1)
    return qty


class AutoReorderEngine:
    """Phase 142 자동 리오더 엔진.

    BI 분석 결과를 바탕으로 재고 임박 SKU를 감지하고 권장 발주량을 계산한다.
    """

    def __init__(self, enabled: bool | None = None, daily_budget_krw: int | None = None):
        self._enabled = _ENABLED if enabled is None else enabled
        self._budget = _DAILY_BUDGET_KRW if daily_budget_krw is None else daily_budget_krw
        self._last_checked_at: datetime | None = None

    def summary(self) -> dict:
        """진단 대시보드용 요약 정보."""
        items = self._get_pending_items()
        total_cost = sum(i.unit_cost_krw * i.recommended_qty for i in items)
        last_ago = "알 수 없음"
        if self._last_checked_at:
            delta = datetime.now(timezone.utc) - self._last_checked_at
            minutes = int(delta.total_seconds() / 60)
            last_ago = f"{minutes}분 전" if minutes < 60 else f"{minutes // 60}시간 전"
        return {
            "enabled": self._enabled,
            "pending_count": len(items),
            "estimated_cost_krw": total_cost,
            "last_checked_ago": last_ago,
        }

    def get_recommendations(self) -> list[dict]:
        """권장 발주 목록 반환."""
        items = self._detect_low_stock()
        self._last_checked_at = datetime.now(timezone.utc)
        result = []
        for item in items:
            item.recommended_qty = _calc_recommended_qty(item)
            result.append(item.to_dict())
        return result

    def approve_and_place(self, skus: list[str]) -> dict:
        """지정 SKU 발주 승인 및 처리.

        AUTO_REORDER_AUTO_PLACE=0 (기본) 시 수동 승인 필요.
        예산 초과 시 발주 거부.
        """
        items = [i for i in self._detect_low_stock() if i.sku in skus]
        total_cost = sum(i.unit_cost_krw * max(1, _calc_recommended_qty(i)) for i in items)

        if total_cost > self._budget:
            return {
                "ok": False,
                "error": f"예산 초과: 예상 ₩{total_cost:,} > 일일 예산 ₩{self._budget:,}",
                "placed": [],
            }

        placed = []
        for item in items:
            item.recommended_qty = _calc_recommended_qty(item)
            item.status = "placed"
            self._record_order(item)
            placed.append(item.to_dict())
            logger.info("발주 처리: %s × %d (₩%d)", item.sku, item.recommended_qty, item.unit_cost_krw * item.recommended_qty)

        return {"ok": True, "placed": placed, "total_cost_krw": total_cost}

    def _get_pending_items(self) -> list[ReorderItem]:
        """승인 대기 중인 항목 반환 (빠른 summary용, 예외 무시)."""
        try:
            return [i for i in self._detect_low_stock() if i.status == "pending"]
        except Exception:
            return []

    def _detect_low_stock(self) -> list[ReorderItem]:
        """재고 임박 SKU 감지."""
        items: list[ReorderItem] = []
        try:
            # Phase 141 BI 엔진 연동 시도
            from src.analytics.reorder_alert import ReorderAlertEngine
            alert_engine = ReorderAlertEngine()
            alerts = alert_engine.get_reorder_alerts() if hasattr(alert_engine, "get_reorder_alerts") else []
            for alert in alerts:
                sku = str(alert.get("sku") or alert.get("SKU") or "")
                if not sku:
                    continue
                items.append(ReorderItem(
                    sku=sku,
                    title=str(alert.get("title") or alert.get("name") or sku),
                    vendor=str(alert.get("vendor") or ""),
                    current_stock=int(alert.get("stock") or alert.get("current_stock") or 0),
                    sales_velocity_daily=float(alert.get("sales_velocity") or alert.get("velocity_daily") or 0.1),
                    lead_time_days=int(alert.get("lead_time_days") or 7),
                    unit_cost_krw=int(alert.get("unit_cost_krw") or alert.get("buy_price_krw") or 0),
                ))
        except Exception as exc:
            logger.debug("BI 재고 감지 실패 (inventory_sync 폴백): %s", exc)

        if not items:
            # 폴백: 직접 재고 조회
            try:
                from src.inventory.inventory_sync import InventorySync
                sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
                sync = InventorySync(sheet_id=sheet_id)
                rows = sync._get_active_rows() if hasattr(sync, "_get_active_rows") else []
                threshold = _SAFETY_DAYS * 0.5  # 반 안전재고 이하이면 재발주 필요
                for row in rows:
                    stock = int(row.get("stock") or row.get("quantity") or 0)
                    velocity = float(row.get("sales_velocity") or 0.1)
                    days_left = stock / velocity if velocity > 0 else 999
                    if days_left < _SAFETY_DAYS:
                        items.append(ReorderItem(
                            sku=str(row.get("sku") or ""),
                            title=str(row.get("title") or row.get("name") or ""),
                            vendor=str(row.get("vendor") or ""),
                            current_stock=stock,
                            sales_velocity_daily=velocity,
                            unit_cost_krw=int(row.get("buy_price_krw") or row.get("cost_krw") or 0),
                        ))
            except Exception as exc2:
                logger.debug("inventory_sync 폴백 실패: %s", exc2)

        return items

    def _record_order(self, item: ReorderItem) -> None:
        """발주 기록 저장 (Sheets 또는 로컬 파일)."""
        try:
            from src.utils.sheets import open_sheet
            sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
            if sheet_id:
                ws = open_sheet(sheet_id, "auto_reorder_log")
                ws.append_row([
                    datetime.now(timezone.utc).isoformat(),
                    item.sku,
                    item.title,
                    item.vendor,
                    item.recommended_qty,
                    item.unit_cost_krw,
                    item.unit_cost_krw * item.recommended_qty,
                    item.status,
                ])
        except Exception as exc:
            logger.debug("발주 기록 저장 실패: %s", exc)


def get_reorder_recommendations() -> list[dict]:
    """권장 발주 목록 반환 (뷰에서 사용)."""
    engine = AutoReorderEngine()
    return engine.get_recommendations()
