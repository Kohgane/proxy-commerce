"""환율 인메모리 캐시 + Google Sheets 영속화."""

import logging
import os
import time
from decimal import Decimal

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 3600  # 1시간


class FXCache:
    """환율 인메모리 캐시 + Google Sheets 영속화.

    캐시 순서:
      1) 인메모리 (TTL 내)
      2) Google Sheets 'fx_rates' 시트 (영속화)
    """

    def __init__(self, ttl_seconds: int = None):
        """
        ttl_seconds: 캐시 유효 시간 (None이면 FX_CACHE_TTL 환경변수 또는 3600초)
        """
        self._ttl = ttl_seconds if ttl_seconds is not None else int(
            os.getenv('FX_CACHE_TTL', str(_DEFAULT_TTL))
        )
        self._data: dict | None = None
        self._stored_at: float = 0.0

    # ── public API ───────────────────────────────────────────

    def get(self) -> dict | None:
        """캐시된 환율 반환. 만료 시 None."""
        if self._data and self.is_valid():
            return dict(self._data)
        # 인메모리 만료 → Sheets에서 시도
        return self._load_from_sheets()

    def set(self, rates: dict):
        """환율 캐시 저장 (메모리 + Sheets 'fx_rates' 시트)."""
        self._data = dict(rates)
        self._stored_at = time.monotonic()
        self._save_to_sheets(rates)

    def is_valid(self) -> bool:
        """인메모리 캐시 유효 여부."""
        if not self._data:
            return False
        return (time.monotonic() - self._stored_at) < self._ttl

    def invalidate(self):
        """캐시 무효화 (인메모리만, Sheets는 유지)."""
        self._data = None
        self._stored_at = 0.0

    # ── Sheets persistence ───────────────────────────────────

    def _save_to_sheets(self, rates: dict):
        """Google Sheets 'fx_rates' 시트에 현재 환율 저장."""
        sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
        worksheet = os.getenv('FX_RATES_WORKSHEET', 'fx_rates')
        if not sheet_id:
            logger.debug("GOOGLE_SHEET_ID not set — skipping FXCache Sheets persistence")
            return
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(sheet_id, worksheet)
            headers = ['key', 'value', 'fetched_at', 'provider']
            existing = ws.get_all_values()
            if not existing or existing[0] != headers:
                ws.clear()
                ws.append_row(headers)

            provider = str(rates.get('provider', ''))
            fetched_at = str(rates.get('fetched_at', ''))
            from ..fx.provider import FXProvider
            for pair in FXProvider.SUPPORTED_PAIRS:
                val = rates.get(pair)
                if val is not None:
                    ws.append_row([pair, str(val), fetched_at, provider])
            logger.debug("FXCache saved to Sheets worksheet '%s'", worksheet)
        except Exception as exc:
            logger.warning("FXCache Sheets save failed: %s", exc)

    def _load_from_sheets(self) -> dict | None:
        """Google Sheets 'fx_rates' 시트에서 최신 환율 로드."""
        sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
        worksheet = os.getenv('FX_RATES_WORKSHEET', 'fx_rates')
        if not sheet_id:
            return None
        try:
            from ..utils.sheets import open_sheet
            ws = open_sheet(sheet_id, worksheet)
            records = ws.get_all_records()
            if not records:
                return None

            # 가장 최근 행들 (fetched_at 기준 최신)
            latest: dict = {}
            fetched_at = ''
            provider = ''
            for row in records:
                key = str(row.get('key', ''))
                val = str(row.get('value', ''))
                if key in ('USDKRW', 'JPYKRW', 'EURKRW'):
                    try:
                        latest[key] = Decimal(val)
                        fetched_at = str(row.get('fetched_at', ''))
                        provider = str(row.get('provider', ''))
                    except Exception:
                        pass

            if len(latest) == 3:
                latest['fetched_at'] = fetched_at
                latest['provider'] = provider
                # 인메모리 캐시에도 올려두기 (이미 TTL 소비됐으므로 남은 시간은 없지만 set하면 갱신됨)
                self._data = latest
                self._stored_at = time.monotonic()
                logger.debug("FXCache loaded from Sheets")
                return dict(latest)
        except Exception as exc:
            logger.warning("FXCache Sheets load failed: %s", exc)
        return None
