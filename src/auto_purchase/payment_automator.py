"""src/auto_purchase/payment_automator.py — 자동 결제 관리 (Phase 96)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import Dict, List, Optional

from .purchase_models import PaymentRecord

logger = logging.getLogger(__name__)

# 마켓플레이스별 권장 결제 수단
_PREFERRED_METHODS: Dict[str, List[str]] = {
    'amazon_us': ['credit_card', 'paypal'],
    'amazon_jp': ['credit_card'],
    'taobao': ['alipay', 'credit_card'],
    'alibaba_1688': ['alipay', 'credit_card'],
}


@dataclass
class PaymentMethod:
    """결제 수단 데이터 모델."""
    method_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = 'credit_card'              # credit_card, alipay, paypal
    name: str = ''
    currency: str = 'USD'
    balance: float = 0.0                   # 잔액 (선불형) or 신용 한도
    is_active: bool = True
    daily_limit: float = 5000.0
    monthly_limit: float = 50000.0
    single_limit: float = 1000.0
    supported_marketplaces: List[str] = field(default_factory=list)


@dataclass
class PaymentLimitTracker:
    """결제 한도 추적기."""
    method_id: str = ''
    today: date = field(default_factory=date.today)
    daily_spent: float = 0.0
    monthly_spent: float = 0.0
    current_month: str = field(default_factory=lambda: datetime.now().strftime('%Y-%m'))

    def reset_if_new_day(self) -> None:
        """날짜가 바뀌면 일일 한도를 초기화한다."""
        today = date.today()
        if self.today != today:
            self.today = today
            self.daily_spent = 0.0
        current_month = datetime.now().strftime('%Y-%m')
        if self.current_month != current_month:
            self.current_month = current_month
            self.monthly_spent = 0.0


class PaymentAutomator:
    """자동 결제 관리 시스템.

    - 결제 수단 자동 선택 (마켓플레이스별 최적)
    - 한도 관리 (일일/월간/단건)
    - 결제 내역 기록 + 영수증 보관
    - 환율 자동 적용 (FX 모듈 연동)
    """

    def __init__(self) -> None:
        self._methods: Dict[str, PaymentMethod] = {}
        self._records: List[PaymentRecord] = []
        self._limits: Dict[str, PaymentLimitTracker] = {}
        self._setup_default_methods()

    def _setup_default_methods(self) -> None:
        """기본 결제 수단을 초기화한다."""
        methods = [
            PaymentMethod(
                method_id='pm_card_usd',
                type='credit_card',
                name='USD Credit Card',
                currency='USD',
                balance=10000.0,
                daily_limit=5000.0,
                monthly_limit=50000.0,
                single_limit=2000.0,
                supported_marketplaces=['amazon_us', 'amazon_jp', 'taobao', 'alibaba_1688'],
            ),
            PaymentMethod(
                method_id='pm_alipay',
                type='alipay',
                name='Alipay',
                currency='CNY',
                balance=50000.0,
                daily_limit=20000.0,
                monthly_limit=200000.0,
                single_limit=5000.0,
                supported_marketplaces=['taobao', 'alibaba_1688'],
            ),
            PaymentMethod(
                method_id='pm_paypal',
                type='paypal',
                name='PayPal',
                currency='USD',
                balance=5000.0,
                daily_limit=3000.0,
                monthly_limit=30000.0,
                single_limit=1000.0,
                supported_marketplaces=['amazon_us'],
            ),
        ]
        for m in methods:
            self._methods[m.method_id] = m
            self._limits[m.method_id] = PaymentLimitTracker(method_id=m.method_id)

    def add_payment_method(self, method: PaymentMethod) -> None:
        """결제 수단을 추가한다."""
        self._methods[method.method_id] = method
        self._limits[method.method_id] = PaymentLimitTracker(method_id=method.method_id)
        logger.info('Payment method added: %s (%s)', method.method_id, method.type)

    def select_method(self, marketplace: str, amount: float, currency: str = 'USD') -> Optional[PaymentMethod]:
        """마켓플레이스와 금액에 따라 최적 결제 수단을 선택한다."""
        preferred_types = _PREFERRED_METHODS.get(marketplace, ['credit_card'])

        for ptype in preferred_types:
            for method in self._methods.values():
                if not method.is_active:
                    continue
                if method.type != ptype:
                    continue
                if marketplace and method.supported_marketplaces and marketplace not in method.supported_marketplaces:
                    continue

                # 환율 변환 (간단 mock: USD↔CNY = 7.2)
                amount_in_method_currency = self._convert_currency(amount, currency, method.currency)

                if not self._check_limits(method.method_id, amount_in_method_currency, method):
                    continue

                logger.info(
                    'Payment method selected: %s (%s) for %s %.2f %s',
                    method.method_id, method.type, marketplace, amount, currency,
                )
                return method

        logger.warning('No suitable payment method for %s %.2f %s', marketplace, amount, currency)
        return None

    def _convert_currency(self, amount: float, from_currency: str, to_currency: str) -> float:
        """간단 환율 변환 (mock)."""
        if from_currency == to_currency:
            return amount
        rates = {'USD_CNY': 7.2, 'CNY_USD': 1 / 7.2}
        key = f'{from_currency}_{to_currency}'
        rate = rates.get(key, 1.0)
        try:
            from ..fx.provider import FXProvider
            provider = FXProvider()
            fx_rates = provider.get_rates()
            if from_currency == 'USD' and to_currency == 'CNY':
                usd_krw = float(fx_rates.get('USDKRW', 1350))
                cny_krw = usd_krw / 7.2
                rate = usd_krw / cny_krw
        except Exception:
            pass
        return round(amount * rate, 2)

    def _check_limits(self, method_id: str, amount: float, method: PaymentMethod) -> bool:
        """한도 체크 (일일/월간/단건)."""
        tracker = self._limits.get(method_id)
        if not tracker:
            return True
        tracker.reset_if_new_day()

        if amount > method.single_limit:
            logger.warning(
                'Single limit exceeded: %.2f > %.2f (%s)',
                amount, method.single_limit, method_id,
            )
            return False
        if tracker.daily_spent + amount > method.daily_limit:
            logger.warning(
                'Daily limit exceeded: %.2f + %.2f > %.2f (%s)',
                tracker.daily_spent, amount, method.daily_limit, method_id,
            )
            return False
        if tracker.monthly_spent + amount > method.monthly_limit:
            logger.warning(
                'Monthly limit exceeded: %.2f + %.2f > %.2f (%s)',
                tracker.monthly_spent, amount, method.monthly_limit, method_id,
            )
            return False
        return True

    def process_payment(
        self,
        order_id: str,
        marketplace: str,
        amount: float,
        currency: str = 'USD',
        method_id: str = '',
    ) -> PaymentRecord:
        """결제를 처리하고 내역을 기록한다."""
        if method_id:
            method = self._methods.get(method_id)
        else:
            method = self.select_method(marketplace, amount, currency)

        if not method:
            record = PaymentRecord(
                order_id=order_id,
                amount=amount,
                currency=currency,
                status='failed',
                metadata={'error': 'No suitable payment method'},
            )
            self._records.append(record)
            return record

        amount_in_method_currency = self._convert_currency(amount, currency, method.currency)

        # 한도 차감
        tracker = self._limits[method.method_id]
        tracker.daily_spent += amount_in_method_currency
        tracker.monthly_spent += amount_in_method_currency

        record = PaymentRecord(
            order_id=order_id,
            method_id=method.method_id,
            amount=amount,
            currency=currency,
            status='completed',
            receipt_url=f'https://receipts.example.com/{uuid.uuid4().hex}',
            metadata={'marketplace': marketplace, 'method_type': method.type},
        )
        self._records.append(record)

        logger.info(
            'Payment processed: order=%s, amount=%.2f %s, method=%s',
            order_id, amount, currency, method.method_id,
        )
        return record

    def get_payment_history(self, order_id: str = '') -> List[PaymentRecord]:
        """결제 내역을 조회한다."""
        if order_id:
            return [r for r in self._records if r.order_id == order_id]
        return list(self._records)

    def get_daily_spend(self, method_id: str) -> float:
        """특정 결제 수단의 오늘 지출액을 반환한다."""
        tracker = self._limits.get(method_id)
        if not tracker:
            return 0.0
        tracker.reset_if_new_day()
        return tracker.daily_spent

    def list_methods(self) -> List[Dict]:
        """결제 수단 목록을 반환한다."""
        return [
            {
                'method_id': m.method_id,
                'type': m.type,
                'name': m.name,
                'currency': m.currency,
                'is_active': m.is_active,
                'daily_limit': m.daily_limit,
                'daily_spent': self.get_daily_spend(m.method_id),
            }
            for m in self._methods.values()
        ]
