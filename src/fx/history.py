"""Google Sheets 기반 환율 이력 관리."""

import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD_PCT = 3.0


class FXHistory:
    """Google Sheets 기반 환율 이력 관리.

    시트 열: date, USDKRW, JPYKRW, EURKRW, provider, fetched_at
    """

    def __init__(self, sheet_id: str = None, worksheet: str = None):
        self._sheet_id = sheet_id or os.getenv('GOOGLE_SHEET_ID', '')
        self._worksheet = worksheet or os.getenv('FX_HISTORY_WORKSHEET', 'fx_history')

    # ── public API ───────────────────────────────────────────

    def record(self, rates: dict):
        """현재 환율을 이력에 기록.

        시트 열: date, USDKRW, JPYKRW, EURKRW, provider, fetched_at
        """
        if not self._sheet_id:
            logger.debug("GOOGLE_SHEET_ID not set — skipping FXHistory record")
            return
        try:
            ws = self._get_worksheet()
            from .provider import FXProvider
            row = [
                datetime.now(tz=timezone.utc).strftime('%Y-%m-%d'),
                str(rates.get('USDKRW', '')),
                str(rates.get('JPYKRW', '')),
                str(rates.get('EURKRW', '')),
                str(rates.get('provider', '')),
                str(rates.get('fetched_at', '')),
            ]
            ws.append_row(row)
            logger.info("FXHistory recorded: %s", row)
        except Exception as exc:
            logger.warning("FXHistory record failed: %s", exc)

    def get_history(self, days: int = 30) -> list:
        """최근 N일간 환율 이력 조회."""
        records = self._get_all_records()
        if not records:
            return []

        cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime('%Y-%m-%d')
        result = []
        for row in records:
            date_str = str(row.get('date', ''))
            if date_str >= cutoff:
                result.append({
                    'date': date_str,
                    'USDKRW': _safe_decimal(row.get('USDKRW')),
                    'JPYKRW': _safe_decimal(row.get('JPYKRW')),
                    'EURKRW': _safe_decimal(row.get('EURKRW')),
                    'provider': str(row.get('provider', '')),
                    'fetched_at': str(row.get('fetched_at', '')),
                })
        return result

    def get_change_pct(self, pair: str, days: int = 1) -> Decimal:
        """특정 통화쌍의 N일 변동률(%) 계산.

        Returns: 변동률(%). 이력 없으면 Decimal('0').
        """
        history = self.get_history(days=days + 1)
        if len(history) < 2:
            return Decimal('0')

        # 가장 최근 항목과 days일 전 항목 비교
        history_sorted = sorted(history, key=lambda r: r['date'])
        recent = history_sorted[-1].get(pair)
        old = history_sorted[0].get(pair)

        if recent is None or old is None or old == 0:
            return Decimal('0')
        try:
            return (recent - old) / old * Decimal('100')
        except Exception:
            return Decimal('0')

    def get_average(self, pair: str, days: int = 7) -> Decimal:
        """특정 통화쌍의 N일 평균 환율."""
        history = self.get_history(days=days)
        values = [row[pair] for row in history if row.get(pair) is not None]
        if not values:
            return Decimal('0')
        return sum(values, Decimal('0')) / Decimal(str(len(values)))

    def detect_significant_changes(self, threshold_pct: float = None) -> list:
        """급변 감지 (기본 3%).

        Returns:
            [{'pair': 'JPYKRW', 'previous': '9.2', 'current': '8.8', 'change_pct': '-4.35%'}, ...]
        """
        if threshold_pct is None:
            threshold_pct = float(os.getenv('FX_CHANGE_ALERT_PCT', str(_DEFAULT_THRESHOLD_PCT)))

        history = self.get_history(days=2)
        if len(history) < 2:
            return []

        history_sorted = sorted(history, key=lambda r: r['date'])
        recent = history_sorted[-1]
        previous = history_sorted[-2]

        from .provider import FXProvider
        alerts = []
        for pair in FXProvider.SUPPORTED_PAIRS:
            cur = recent.get(pair)
            prev = previous.get(pair)
            if cur is None or prev is None or prev == 0:
                continue
            try:
                change_pct = (cur - prev) / prev * Decimal('100')
                if abs(change_pct) >= Decimal(str(threshold_pct)):
                    alerts.append({
                        'pair': pair,
                        'previous': str(prev),
                        'current': str(cur),
                        'change_pct': f'{change_pct:+.2f}%',
                    })
            except Exception:
                pass
        return alerts

    # ── helpers ──────────────────────────────────────────────

    def _get_worksheet(self):
        """이력 시트를 열고 (없으면 헤더를 초기화)."""
        from ..utils.sheets import open_sheet
        ws = open_sheet(self._sheet_id, self._worksheet)
        existing = ws.get_all_values()
        expected_header = ['date', 'USDKRW', 'JPYKRW', 'EURKRW', 'provider', 'fetched_at']
        if not existing or existing[0] != expected_header:
            ws.clear()
            ws.append_row(expected_header)
        return ws

    def _get_all_records(self) -> list:
        """이력 시트 전체 레코드 조회."""
        if not self._sheet_id:
            return []
        try:
            ws = self._get_worksheet()
            return ws.get_all_records()
        except Exception as exc:
            logger.warning("FXHistory get_all_records failed: %s", exc)
            return []


def _safe_decimal(value) -> Decimal | None:
    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None
