"""src/reporting/report_builder.py — 리포트 빌더.

Google Sheets 데이터를 기반으로 다양한 리포트를 생성한다.

환경변수:
  REPORTING_ENABLED  — 리포팅 활성화 여부 (기본 "0")
  GOOGLE_SHEET_ID    — Google Sheets ID
"""

import datetime
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_ENABLED = os.getenv("REPORTING_ENABLED", "0") == "1"
_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")

try:
    from ..utils.sheets import open_sheet
except ImportError:
    open_sheet = None  # type: ignore


class ReportBuilder:
    """다양한 리포트를 생성하는 빌더 클래스."""

    def __init__(self, sheet_id: str = ""):
        self._sheet_id = sheet_id or _SHEET_ID

    def is_enabled(self) -> bool:
        """리포팅 활성화 여부를 반환한다."""
        return os.getenv("REPORTING_ENABLED", "0") == "1"

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------

    def _load_worksheet(self, worksheet_name: str):
        """워크시트 레코드를 로드한다."""
        if open_sheet is None:
            return []
        try:
            ws = open_sheet(self._sheet_id, worksheet_name)
            return [dict(r) for r in ws.get_all_records()]
        except Exception as exc:
            logger.warning("워크시트 '%s' 로드 실패: %s", worksheet_name, exc)
            return []

    def _in_range(self, date_str: str, start: Optional[str], end: Optional[str]) -> bool:
        """날짜 문자열이 범위 내에 있는지 확인한다."""
        if not date_str:
            return True
        date_part = str(date_str)[:10]
        if start and date_part < start:
            return False
        if end and date_part > end:
            return False
        return True

    # ------------------------------------------------------------------
    # 개별 리포트 빌더
    # ------------------------------------------------------------------

    def _build_sales_report(self, start: Optional[str], end: Optional[str]) -> Dict[str, Any]:
        """매출 리포트를 생성한다."""
        orders = self._load_worksheet("orders")
        filtered = [o for o in orders if self._in_range(str(o.get("created_at", "")), start, end)]

        total_revenue = 0.0
        by_channel: Dict[str, int] = {}
        for o in filtered:
            try:
                total_revenue += float(o.get("total_price_krw", 0) or 0)
            except (ValueError, TypeError):
                pass
            channel = str(o.get("channel", "unknown"))
            by_channel[channel] = by_channel.get(channel, 0) + 1

        total_orders = len(filtered)
        avg_order = total_revenue / total_orders if total_orders > 0 else 0.0

        return {
            "report_type": "sales",
            "period": {"start": start, "end": end},
            "total_orders": total_orders,
            "total_revenue_krw": total_revenue,
            "avg_order_krw": avg_order,
            "by_channel": by_channel,
            "generated_at": datetime.datetime.utcnow().isoformat(),
        }

    def _build_inventory_report(self, start: Optional[str], end: Optional[str]) -> Dict[str, Any]:
        """재고 리포트를 생성한다."""
        products = self._load_worksheet("catalog") or self._load_worksheet("products")

        total_skus = len(products)
        in_stock = out_of_stock = low_stock = dead_stock = 0

        for p in products:
            try:
                qty = int(float(p.get("stock_qty", p.get("quantity", 0)) or 0))
            except (ValueError, TypeError):
                qty = 0

            if qty <= 0:
                out_of_stock += 1
            elif qty <= 5:
                low_stock += 1
            elif qty >= 100:
                dead_stock += 1
            else:
                in_stock += 1

        return {
            "report_type": "inventory",
            "total_skus": total_skus,
            "in_stock": in_stock,
            "out_of_stock": out_of_stock,
            "low_stock": low_stock,
            "dead_stock": dead_stock,
            "generated_at": datetime.datetime.utcnow().isoformat(),
        }

    def _build_customer_report(self, start: Optional[str], end: Optional[str]) -> Dict[str, Any]:
        """고객 리포트를 생성한다."""
        customers = self._load_worksheet("customers")
        filtered = [c for c in customers if self._in_range(str(c.get("first_order_date", "")), start, end)]

        by_segment: Dict[str, int] = {}
        for c in customers:
            seg = str(c.get("segment", "UNKNOWN"))
            by_segment[seg] = by_segment.get(seg, 0) + 1

        return {
            "report_type": "customers",
            "total_customers": len(customers),
            "new_customers": len(filtered),
            "by_segment": by_segment,
            "generated_at": datetime.datetime.utcnow().isoformat(),
        }

    def _build_marketing_report(self, start: Optional[str], end: Optional[str]) -> Dict[str, Any]:
        """마케팅 리포트를 생성한다."""
        campaigns = self._load_worksheet("campaigns")

        total_campaigns = len(campaigns)
        active_campaigns = sum(1 for c in campaigns if c.get("status") == "active")
        total_budget = 0.0
        total_spent = 0.0

        for c in campaigns:
            try:
                total_budget += float(c.get("budget_krw", 0) or 0)
                total_spent += float(c.get("spent_krw", 0) or 0)
            except (ValueError, TypeError):
                pass

        roi = (total_spent / total_budget * 100) if total_budget > 0 else 0.0

        return {
            "report_type": "marketing",
            "total_campaigns": total_campaigns,
            "active_campaigns": active_campaigns,
            "total_budget_krw": total_budget,
            "total_spent_krw": total_spent,
            "roi": roi,
            "generated_at": datetime.datetime.utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------

    def generate_report(
        self,
        report_type: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """지정된 타입의 리포트를 생성한다.

        Args:
            report_type: "sales" | "inventory" | "customers" | "marketing"
            start_date: 시작일 "YYYY-MM-DD" 또는 None (전체 기간).
            end_date: 종료일 "YYYY-MM-DD" 또는 None (전체 기간).

        Returns:
            리포트 딕셔너리.
        """
        builders = {
            "sales": self._build_sales_report,
            "inventory": self._build_inventory_report,
            "customers": self._build_customer_report,
            "marketing": self._build_marketing_report,
        }

        builder = builders.get(report_type)
        if builder is None:
            return {
                "error": f"알 수 없는 리포트 타입: {report_type}",
                "valid_types": list(builders.keys()),
            }

        try:
            return builder(start_date, end_date)
        except Exception as exc:
            logger.error("리포트 생성 실패 (%s): %s", report_type, exc)
            return {"error": str(exc), "report_type": report_type}
