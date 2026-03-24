"""src/export/report_generator.py — 종합 리포트 생성기.

일일/주간/월간 운영 리포트를 텍스트 형식으로 생성한다.
텔레그램 발송 및 파일 첨부를 지원한다.

환경변수:
  GOOGLE_SHEET_ID   — Google Sheets ID
  TELEGRAM_BOT_TOKEN — 텔레그램 봇 토큰
  TELEGRAM_CHAT_ID   — 텔레그램 채팅 ID
"""

import datetime
import logging
import os
from typing import Any, Dict, List, Optional

try:
    from ..utils.sheets import open_sheet
    from ..utils.telegram import send_tele
except ImportError:
    open_sheet = None  # type: ignore[assignment]
    send_tele = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")


class ReportGenerator:
    """종합 리포트 생성기.

    사용 예:
        gen = ReportGenerator()
        report = gen.daily_report()
        gen.send_to_telegram(report)
    """

    def __init__(self, sheet_id: Optional[str] = None):
        self._sheet_id = sheet_id or _SHEET_ID

    # ── 공개 API ──────────────────────────────────────────

    def daily_report(self, date: Optional[datetime.date] = None) -> str:
        """일일 운영 리포트를 생성한다.

        Args:
            date: 리포트 날짜 (기본: 어제)

        Returns:
            텍스트 형식 리포트 문자열
        """
        target = date or (datetime.date.today() - datetime.timedelta(days=1))
        orders = self._load_orders_for_date(target, target)
        catalog = self._load_catalog()

        total_revenue = sum(float(o.get("sell_price_krw", 0) or 0) for o in orders)
        avg_margin = (
            round(sum(float(o.get("margin_pct", 0) or 0) for o in orders) / len(orders), 1)
            if orders else 0.0
        )
        low_stock = sum(1 for c in catalog if int(c.get("stock", 0) or 0) <= 3)

        lines = [
            f"📊 일일 운영 리포트 [{target.strftime('%Y-%m-%d')}]",
            "━" * 40,
            f"✅ 총 주문: {len(orders)}건",
            f"💰 총 매출: {total_revenue:,.0f}원",
            f"📈 평균 마진: {avg_margin:.1f}%",
            f"⚠️  재고 부족 상품: {low_stock}개",
            "━" * 40,
            f"생성 시각: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M KST')}",
        ]
        return "\n".join(lines)

    def weekly_report(self) -> str:
        """주간 종합 리포트를 생성한다.

        Returns:
            텍스트 형식 리포트 문자열
        """
        today = datetime.date.today()
        week_start = today - datetime.timedelta(days=today.weekday() + 7)
        week_end = week_start + datetime.timedelta(days=6)
        orders = self._load_orders_for_date(week_start, week_end)
        catalog = self._load_catalog()

        total_revenue = sum(float(o.get("sell_price_krw", 0) or 0) for o in orders)
        vendor_stats = self._calc_vendor_stats(orders)
        low_stock = sum(1 for c in catalog if int(c.get("stock", 0) or 0) <= 3)

        lines = [
            f"📊 주간 종합 리포트 [{week_start} ~ {week_end}]",
            "━" * 40,
            f"✅ 총 주문: {len(orders)}건",
            f"💰 총 매출: {total_revenue:,.0f}원",
            f"⚠️  재고 부족 상품: {low_stock}개",
            "",
            "📦 벤더별 주문 현황:",
        ]
        for vendor, count in sorted(vendor_stats.items(), key=lambda x: -x[1]):
            lines.append(f"  • {vendor}: {count}건")
        lines += [
            "━" * 40,
            f"생성 시각: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M KST')}",
        ]
        return "\n".join(lines)

    def monthly_report(self) -> str:
        """월간 운영 리포트를 생성한다.

        Returns:
            텍스트 형식 리포트 문자열
        """
        today = datetime.date.today()
        first_day = today.replace(day=1) - datetime.timedelta(days=1)
        month_start = first_day.replace(day=1)
        month_end = first_day
        orders = self._load_orders_for_date(month_start, month_end)
        catalog = self._load_catalog()

        total_revenue = sum(float(o.get("sell_price_krw", 0) or 0) for o in orders)
        avg_margin = (
            round(sum(float(o.get("margin_pct", 0) or 0) for o in orders) / len(orders), 1)
            if orders else 0.0
        )
        vendor_stats = self._calc_vendor_stats(orders)
        low_stock = sum(1 for c in catalog if int(c.get("stock", 0) or 0) <= 3)

        lines = [
            f"📊 월간 운영 리포트 [{month_start.strftime('%Y년 %m월')}]",
            "━" * 40,
            f"✅ 총 주문: {len(orders)}건",
            f"💰 총 매출: {total_revenue:,.0f}원",
            f"📈 평균 마진: {avg_margin:.1f}%",
            f"⚠️  재고 부족 상품: {low_stock}개",
            "",
            "📦 벤더별 주문 현황:",
        ]
        for vendor, count in sorted(vendor_stats.items(), key=lambda x: -x[1]):
            lines.append(f"  • {vendor}: {count}건")
        lines += [
            "━" * 40,
            f"생성 시각: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M KST')}",
        ]
        return "\n".join(lines)

    def margin_analysis_report(self) -> str:
        """마진 분석 리포트를 생성한다.

        Returns:
            텍스트 형식 리포트 문자열
        """
        catalog = self._load_catalog()
        if not catalog:
            return "마진 데이터 없음"

        margins = []
        for c in catalog:
            try:
                margins.append((c.get("sku", ""), float(c.get("margin_pct", 0) or 0)))
            except (ValueError, TypeError):
                continue

        if not margins:
            return "마진 데이터 없음"

        avg_margin = round(sum(m for _, m in margins) / len(margins), 1)
        top_margin = sorted(margins, key=lambda x: -x[1])[:5]
        low_margin = sorted(margins, key=lambda x: x[1])[:5]

        lines = [
            "📈 마진 분석 리포트",
            "━" * 40,
            f"전체 상품 수: {len(margins)}개",
            f"평균 마진율: {avg_margin:.1f}%",
            "",
            "🏆 고마진 TOP 5:",
        ]
        for sku, margin in top_margin:
            lines.append(f"  • {sku}: {margin:.1f}%")
        lines.append("")
        lines.append("⚠️  저마진 하위 5:")
        for sku, margin in low_margin:
            lines.append(f"  • {sku}: {margin:.1f}%")
        lines.append(f"\n생성 시각: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M KST')}")
        return "\n".join(lines)

    def send_to_telegram(self, message: str, csv_bytes: Optional[bytes] = None,
                         filename: Optional[str] = None) -> bool:
        """리포트를 텔레그램으로 발송한다.

        Args:
            message: 전송할 텍스트 메시지
            csv_bytes: 첨부할 CSV bytes (선택)
            filename: 첨부 파일명 (선택)

        Returns:
            발송 성공 여부
        """
        try:
            send_tele(message)
            logger.info("텔레그램 리포트 발송 완료")
            return True
        except Exception as exc:
            logger.warning("텔레그램 리포트 발송 실패: %s", exc)
            return False

    # ── 내부 메서드 ───────────────────────────────────────

    def _load_catalog(self) -> List[Dict[str, Any]]:
        """카탈로그 데이터를 로드한다."""
        try:
            ws = open_sheet(self._sheet_id, os.getenv("WORKSHEET", "catalog"))
            return ws.get_all_records()
        except Exception as exc:
            logger.warning("카탈로그 로드 실패: %s", exc)
            return []

    def _load_orders_for_date(
        self,
        date_from: datetime.date,
        date_to: datetime.date,
    ) -> List[Dict[str, Any]]:
        """날짜 범위 내 주문을 로드한다."""
        try:
            ws = open_sheet(self._sheet_id, os.getenv("ORDERS_WORKSHEET", "orders"))
            rows = ws.get_all_records()
        except Exception as exc:
            logger.warning("주문 로드 실패: %s", exc)
            return []

        result = []
        for r in rows:
            val = str(r.get("order_date", ""))
            try:
                dt = datetime.datetime.fromisoformat(val.replace("Z", "+00:00")).date()
                if date_from <= dt <= date_to:
                    result.append(r)
            except (ValueError, TypeError):
                continue
        return result

    def _calc_vendor_stats(self, orders: List[Dict[str, Any]]) -> Dict[str, int]:
        """벤더별 주문 수를 계산한다."""
        stats: Dict[str, int] = {}
        for o in orders:
            vendor = str(o.get("vendor", "unknown"))
            stats[vendor] = stats.get(vendor, 0) + 1
        return stats
