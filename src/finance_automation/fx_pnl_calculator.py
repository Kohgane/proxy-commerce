"""src/finance_automation/fx_pnl_calculator.py — Phase 119: 외환 손익 계산기."""
from __future__ import annotations

import logging
import os
from decimal import Decimal

from .models import FxPnL

logger = logging.getLogger(__name__)

_FX_DISABLE_NETWORK = os.environ.get('FX_DISABLE_NETWORK', '').lower() in ('1', 'true', 'yes')

try:
    if _FX_DISABLE_NETWORK:
        raise ImportError('FX_DISABLE_NETWORK 설정으로 FXProvider 비활성화')
    from ..fx.provider import FXProvider as _FXProvider  # type: ignore
    _HAS_FX = True
except ImportError:
    _HAS_FX = False

# 통화별 기본 환율 (KRW 기준)
_DEFAULT_RATES: dict = {
    'USD': Decimal('1350'),
    'EUR': Decimal('1480'),
    'JPY': Decimal('9'),
    'CNY': Decimal('185'),
    'KRW': Decimal('1'),
}


class FxPnLCalculator:
    """외환 손익 계산.

    매입 시 환율과 정산 시 환율의 차이로 실현 손익을 산출한다.
    FXProvider를 사용하거나 기본 환율로 fallback한다.
    """

    def calculate(
        self,
        purchase_id: str,
        amount_foreign: Decimal,
        currency: str,
        fx_at_purchase: Decimal,
    ) -> FxPnL:
        """외환 손익 계산.

        Args:
            purchase_id: 매입 ID
            amount_foreign: 외화 금액
            currency: 통화 코드
            fx_at_purchase: 매입 시 환율 (KRW/외화)

        Returns:
            FxPnL 레코드
        """
        fx_at_settlement = self._get_current_rate(currency)
        realized_pnl = (fx_at_settlement - fx_at_purchase) * amount_foreign

        pnl = FxPnL(
            purchase_id=purchase_id,
            fx_at_purchase=fx_at_purchase,
            fx_at_settlement=fx_at_settlement,
            realized_pnl_krw=realized_pnl,
        )
        logger.info(
            "[FX손익] %s: 매입환율=%s 정산환율=%s 실현손익=%s KRW",
            purchase_id, fx_at_purchase, fx_at_settlement, realized_pnl,
        )
        return pnl

    def _get_current_rate(self, currency: str) -> Decimal:
        """현재 환율 조회.

        FXProvider 사용 가능 시 실시간 환율, 아니면 기본값.

        Args:
            currency: 통화 코드 (USD, EUR 등)
        """
        if _HAS_FX:
            try:
                provider = _FXProvider()
                rate = provider.get_rate(currency, 'KRW')
                if rate:
                    return Decimal(str(rate))
            except Exception as exc:
                logger.warning("[FX손익] FXProvider 오류, 기본 환율 사용: %s", exc)
        return _DEFAULT_RATES.get(currency.upper(), Decimal('1350'))
