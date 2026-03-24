"""src/export/csv_exporter.py — CSV 내보내기.

주문, 재고, 매출, 감사 로그를 CSV 파일로 내보낸다.
BOM 포함 UTF-8 (utf-8-sig) 인코딩으로 한국어/일본어를 지원한다.

환경변수:
  GOOGLE_SHEET_ID  — Google Sheets ID
  EXPORT_ENCODING  — CSV 인코딩 (기본 "utf-8-sig")
"""

import csv
import datetime
import io
import logging
import os
from typing import Any, Dict, List, Optional

try:
    from ..utils.sheets import open_sheet
except ImportError:
    open_sheet = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
_ENCODING = os.getenv("EXPORT_ENCODING", "utf-8-sig")

# 주문 CSV 열 순서
ORDER_COLUMNS = [
    "order_id", "order_number", "customer_name", "customer_email",
    "order_date", "sku", "vendor", "buy_price", "buy_currency",
    "sell_price_krw", "sell_price_usd", "margin_pct", "status",
    "status_updated_at", "shipping_country",
]

# 재고 CSV 열 순서
INVENTORY_COLUMNS = [
    "sku", "title_ko", "title_en", "vendor", "buy_currency", "buy_price",
    "sell_price_krw", "margin_pct", "stock", "stock_status", "status", "source_country",
]

# 매출 CSV 열 순서
REVENUE_COLUMNS = [
    "order_id", "order_date", "sku", "vendor", "sell_price_krw",
    "sell_price_usd", "margin_pct", "status",
]

# 감사 로그 CSV 열 순서
AUDIT_COLUMNS = [
    "timestamp", "event_type", "actor", "resource", "details", "ip_address",
]


class CsvExporter:
    """CSV 내보내기 클래스.

    사용 예:
        exporter = CsvExporter()
        csv_bytes = exporter.export_orders()
        with open("orders.csv", "wb") as f:
            f.write(csv_bytes)
    """

    def __init__(self, sheet_id: Optional[str] = None, encoding: str = _ENCODING):
        self._sheet_id = sheet_id or _SHEET_ID
        self._encoding = encoding

    # ── 공개 API ──────────────────────────────────────────

    def export_orders(
        self,
        date_from: Optional[datetime.date] = None,
        date_to: Optional[datetime.date] = None,
        status: Optional[str] = None,
    ) -> bytes:
        """주문 데이터를 CSV로 내보낸다.

        Args:
            date_from: 시작 날짜 필터 (포함)
            date_to: 종료 날짜 필터 (포함)
            status: 주문 상태 필터

        Returns:
            BOM 포함 CSV bytes
        """
        rows = self._load_sheet(os.getenv("ORDERS_WORKSHEET", "orders"))
        rows = self._filter_by_date(rows, "order_date", date_from, date_to)
        if status:
            rows = [r for r in rows if str(r.get("status", "")).lower() == status.lower()]
        return self._to_csv(rows, ORDER_COLUMNS)

    def export_inventory(self, low_stock_only: bool = False) -> bytes:
        """재고 현황을 CSV로 내보낸다.

        Args:
            low_stock_only: True면 재고 부족 항목만 내보냄

        Returns:
            BOM 포함 CSV bytes
        """
        rows = self._load_sheet(os.getenv("WORKSHEET", "catalog"))
        if low_stock_only:
            threshold = int(os.getenv("LOW_STOCK_THRESHOLD", "3"))
            rows = [r for r in rows if int(r.get("stock", 0) or 0) <= threshold]
        return self._to_csv(rows, INVENTORY_COLUMNS)

    def export_revenue(
        self,
        date_from: Optional[datetime.date] = None,
        date_to: Optional[datetime.date] = None,
    ) -> bytes:
        """매출 리포트를 CSV로 내보낸다.

        Args:
            date_from: 시작 날짜 필터 (포함)
            date_to: 종료 날짜 필터 (포함)

        Returns:
            BOM 포함 CSV bytes
        """
        rows = self._load_sheet(os.getenv("ORDERS_WORKSHEET", "orders"))
        rows = self._filter_by_date(rows, "order_date", date_from, date_to)
        rows = [r for r in rows if str(r.get("status", "")).lower() not in ("cancelled", "refunded")]
        return self._to_csv(rows, REVENUE_COLUMNS)

    def export_audit(self, days: int = 30) -> bytes:
        """감사 로그를 CSV로 내보낸다.

        Args:
            days: 최근 N일 감사 로그 내보내기

        Returns:
            BOM 포함 CSV bytes
        """
        rows = self._load_sheet(os.getenv("AUDIT_WORKSHEET", "audit_log"))
        cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(days=days)
        filtered = []
        for r in rows:
            ts_str = str(r.get("timestamp", ""))
            try:
                ts = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts >= cutoff:
                    filtered.append(r)
            except (ValueError, TypeError):
                filtered.append(r)
        return self._to_csv(filtered, AUDIT_COLUMNS)

    # ── 내부 메서드 ───────────────────────────────────────

    def _load_sheet(self, worksheet: str) -> List[Dict[str, Any]]:
        """Google Sheets 워크시트에서 데이터를 로드한다."""
        try:
            ws = open_sheet(self._sheet_id, worksheet)
            return ws.get_all_records()
        except Exception as exc:
            logger.warning("시트 데이터 로드 실패 (%s): %s", worksheet, exc)
            return []

    def _filter_by_date(
        self,
        rows: List[Dict[str, Any]],
        date_field: str,
        date_from: Optional[datetime.date],
        date_to: Optional[datetime.date],
    ) -> List[Dict[str, Any]]:
        """날짜 필드를 기준으로 행을 필터링한다."""
        if not date_from and not date_to:
            return rows
        result = []
        for r in rows:
            val = str(r.get(date_field, ""))
            try:
                dt = datetime.datetime.fromisoformat(val.replace("Z", "+00:00")).date()
                if date_from and dt < date_from:
                    continue
                if date_to and dt > date_to:
                    continue
                result.append(r)
            except (ValueError, TypeError):
                result.append(r)
        return result

    def _to_csv(self, rows: List[Dict[str, Any]], columns: List[str]) -> bytes:
        """행 데이터를 BOM 포함 CSV bytes로 변환한다.

        Args:
            rows: 딕셔너리 행 목록
            columns: 출력할 열 순서 목록

        Returns:
            BOM 포함 CSV bytes (utf-8-sig)
        """
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=columns,
            extrasaction="ignore",
            lineterminator="\r\n",
        )
        writer.writeheader()
        for row in rows:
            safe_row = {k: ("" if v is None else str(v)) for k, v in row.items()}
            writer.writerow(safe_row)
        return buf.getvalue().encode(self._encoding)
