"""src/ai/budget.py — AI 사용량 예산 가드 (Phase 134).

월 예산(AI_MONTHLY_BUDGET_USD) 초과 시 OpenAI 호출 차단 + 텔레그램 알림.
80% 소진 시 경고 알림.
비용 이력: Google Sheets `ai_spend` 워크시트에 기록.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


class BudgetExceededError(Exception):
    """월 예산 초과 시 발생."""

    def __init__(self, summary: dict) -> None:
        self.summary = summary
        limit = summary.get("limit_usd", "?")
        used = summary.get("used_usd", "?")
        super().__init__(
            f"AI 월 예산 초과: {used}/{limit} USD"
        )


class AISpendSheets:
    """Google Sheets ai_spend 워크시트 I/O."""

    WORKSHEET_NAME = "ai_spend"
    HEADERS = ["date", "cost_usd", "provider", "tokens", "note"]

    def __init__(self) -> None:
        self._ws = None

    def _get_ws(self):
        if self._ws is not None:
            return self._ws
        try:
            from src.utils.sheets import get_worksheet
            ws = get_worksheet(self.WORKSHEET_NAME, headers=self.HEADERS)
            self._ws = ws
            return ws
        except Exception as exc:
            logger.debug("ai_spend 워크시트 접근 불가: %s", exc)
            return None

    def month_to_date(self) -> Decimal:
        """이번 달 누적 비용(USD) 반환."""
        ws = self._get_ws()
        if ws is None:
            return Decimal("0")
        try:
            rows = ws.get_all_records()
            today = date.today()
            month_prefix = today.strftime("%Y-%m")
            total = Decimal("0")
            for row in rows:
                row_date = str(row.get("date", ""))
                if row_date.startswith(month_prefix):
                    try:
                        total += Decimal(str(row.get("cost_usd", "0")))
                    except Exception:
                        pass
            return total
        except Exception as exc:
            logger.warning("ai_spend 조회 오류: %s", exc)
            return Decimal("0")

    def append(self, record: dict) -> None:
        """비용 레코드 추가."""
        ws = self._get_ws()
        if ws is None:
            logger.debug("ai_spend 미연결 — 레코드 건너뜀: %s", record)
            return
        try:
            row = [
                str(record.get("date", date.today())),
                str(record.get("cost_usd", "0")),
                str(record.get("provider", "")),
                str(record.get("tokens", "0")),
                str(record.get("note", "")),
            ]
            ws.append_row(row)
        except Exception as exc:
            logger.warning("ai_spend 기록 오류: %s", exc)

    def recent(self, n: int = 10) -> list:
        """최근 N건 조회."""
        ws = self._get_ws()
        if ws is None:
            return []
        try:
            rows = ws.get_all_records()
            return rows[-n:] if len(rows) > n else rows
        except Exception as exc:
            logger.warning("ai_spend 최근 조회 오류: %s", exc)
            return []


class BudgetGuard:
    """AI 사용량 예산 가드."""

    def __init__(self) -> None:
        self.monthly_limit_usd = Decimal(
            os.getenv("AI_MONTHLY_BUDGET_USD", "100")
        )
        self.warn_threshold = Decimal("0.8")  # 80% 경고
        self.sheets = AISpendSheets()
        self._warned_this_session = False

    def can_spend(self, estimated_cost_usd: Decimal = Decimal("0.05")) -> bool:
        """예산 여유 여부 확인.

        Args:
            estimated_cost_usd: 예상 비용(USD)

        Returns:
            True: 지출 가능, False: 예산 초과 차단
        """
        if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
            logger.debug("ADAPTER_DRY_RUN=1 — 예산 검사 건너뜀")
            return True

        used = self.sheets.month_to_date()
        if used + estimated_cost_usd > self.monthly_limit_usd:
            logger.warning(
                "AI 월 예산 초과: used=%.4f limit=%.4f", used, self.monthly_limit_usd
            )
            self._send_exceeded_alert(used)
            return False

        ratio = used / self.monthly_limit_usd if self.monthly_limit_usd > 0 else Decimal("0")
        if ratio >= self.warn_threshold and not self._warned_this_session:
            self._send_warning(used)
            self._warned_this_session = True

        return True

    def record(self, cost_usd: Decimal, provider: str = "", tokens: int = 0, note: str = "") -> None:
        """비용 기록."""
        self.sheets.append({
            "date": date.today(),
            "cost_usd": cost_usd,
            "provider": provider,
            "tokens": tokens,
            "note": note,
        })

    def summary(self) -> dict:
        """예산 현황 요약."""
        used = self.sheets.month_to_date()
        remaining = self.monthly_limit_usd - used
        pct = float(used / self.monthly_limit_usd * 100) if self.monthly_limit_usd > 0 else 0.0
        return {
            "limit_usd": float(self.monthly_limit_usd),
            "used_usd": float(used),
            "remaining_usd": float(remaining),
            "pct": round(pct, 1),
            "status": "ok" if pct < 80 else ("warning" if pct < 100 else "exceeded"),
        }

    def _send_warning(self, used: Decimal) -> None:
        """80% 소진 경고 알림."""
        try:
            from src.notifications.telegram import send_telegram
            pct = float(used / self.monthly_limit_usd * 100)
            send_telegram(
                f"⚠️ AI 예산 경고: {pct:.1f}% 소진 "
                f"(${float(used):.2f} / ${float(self.monthly_limit_usd):.2f})",
                urgency="warning",
            )
        except Exception as exc:
            logger.warning("예산 경고 알림 실패: %s", exc)

    def _send_exceeded_alert(self, used: Decimal) -> None:
        """예산 초과 알림."""
        try:
            from src.notifications.telegram import send_telegram
            send_telegram(
                f"🚨 AI 예산 초과! ${float(used):.2f} / ${float(self.monthly_limit_usd):.2f} "
                f"— OpenAI 호출 차단됨. AI_MONTHLY_BUDGET_USD 상향 또는 내달 초까지 대기.",
                urgency="critical",
            )
        except Exception as exc:
            logger.warning("예산 초과 알림 실패: %s", exc)
