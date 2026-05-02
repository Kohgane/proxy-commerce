"""src/finance_automation/period_closer.py — Phase 119: 기간 마감 처리."""
from __future__ import annotations

import calendar
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, Optional

from .ledger import Ledger
from .models import AccountCode, PeriodClose

if TYPE_CHECKING:
    from .anomaly_detector import FinanceAnomalyDetector
    from .revenue_recognizer import RevenueRecognizer

logger = logging.getLogger(__name__)


class PeriodCloser:
    """일/주/월 회계 기간 마감 처리.

    마감 시 이상 감지 → 원장 잠금 → 집계 저장을 수행한다.
    """

    def __init__(
        self,
        ledger: Ledger,
        anomaly_detector: 'FinanceAnomalyDetector',
        recognizer: 'RevenueRecognizer',
    ) -> None:
        self._ledger = ledger
        self._anomaly_det = anomaly_detector
        self._recognizer = recognizer
        self._closes: Dict[str, PeriodClose] = {}

    def close_daily(self, date_str: str) -> PeriodClose:
        """일 마감.

        Args:
            date_str: 마감 일자 (YYYY-MM-DD)

        Returns:
            PeriodClose 레코드
        """
        key = f'daily:{date_str}'
        if key in self._closes and self._closes[key].status == 'closed':
            return self._closes[key]

        anomalies = self._anomaly_det.run_all({'period': date_str})
        trial = self._ledger.trial_balance(date_str)
        self._ledger.lock_period(date_str)

        close = PeriodClose(
            period=date_str,
            type='daily',
            status='closed',
            closed_at=datetime.now(timezone.utc).isoformat(),
            totals=self._summarize_trial(trial),
        )
        self._closes[key] = close
        logger.info("[기간마감] 일 마감 완료: %s (이상=%d건)", date_str, len(anomalies))
        self._notify_close(close)
        return close

    def close_weekly(self, week_str: str) -> PeriodClose:
        """주 마감.

        Args:
            week_str: ISO 주 (예: '2026-W18')

        Returns:
            PeriodClose 레코드
        """
        key = f'weekly:{week_str}'
        if key in self._closes and self._closes[key].status == 'closed':
            return self._closes[key]

        anomalies = self._anomaly_det.run_all({'period': week_str})
        year_week = week_str  # 원장 조회에 주 접두어 사용
        trial = self._ledger.trial_balance()

        close = PeriodClose(
            period=week_str,
            type='weekly',
            status='closed',
            closed_at=datetime.now(timezone.utc).isoformat(),
            totals=self._summarize_trial(trial),
        )
        self._closes[key] = close
        logger.info("[기간마감] 주 마감 완료: %s (이상=%d건)", week_str, len(anomalies))
        self._notify_close(close)
        return close

    def close_monthly(self, month_str: str) -> PeriodClose:
        """월 마감.

        Args:
            month_str: YYYY-MM 형식의 월 문자열 (예: '2026-05')

        Returns:
            PeriodClose 레코드
        """
        key = f'monthly:{month_str}'
        if key in self._closes and self._closes[key].status == 'closed':
            return self._closes[key]

        anomalies = self._anomaly_det.run_all({'period': month_str})
        trial = self._ledger.trial_balance(month_str)
        # 월의 실제 마지막 날로 원장 잠금
        year, month = int(month_str[:4]), int(month_str[5:7])
        last_day = calendar.monthrange(year, month)[1]
        lock_date = f'{month_str}-{last_day:02d}'
        self._ledger.lock_period(lock_date)

        close = PeriodClose(
            period=month_str,
            type='monthly',
            status='closed',
            closed_at=datetime.now(timezone.utc).isoformat(),
            totals=self._summarize_trial(trial),
        )
        self._closes[key] = close
        logger.info("[기간마감] 월 마감 완료: %s (이상=%d건)", month_str, len(anomalies))
        self._notify_close(close)
        return close

    def get_close(self, period_type: str, key: str) -> Optional[PeriodClose]:
        """마감 레코드 조회.

        Args:
            period_type: daily|weekly|monthly
            key: 기간 키 (날짜, 주, 월)
        """
        return self._closes.get(f'{period_type}:{key}')

    def _summarize_trial(self, trial: dict) -> dict:
        """시산표를 요약 dict로 변환."""
        return {
            acc: {
                'debit': str(v['debit']),
                'credit': str(v['credit']),
                'net': str(v['net']),
            }
            for acc, v in trial.items()
        }

    def _notify_close(self, close: PeriodClose) -> None:
        """마감 완료 알림 (목업)."""
        logger.info("[기간마감] 알림: %s %s 마감 완료", close.type, close.period)
