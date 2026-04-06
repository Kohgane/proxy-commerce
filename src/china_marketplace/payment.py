"""src/china_marketplace/payment.py — 중국 결제 서비스 mock (Phase 104)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 기본 환율 (CNY → KRW)
DEFAULT_CNY_KRW_RATE = 188.0


@dataclass
class PaymentRecord:
    payment_id: str
    order_id: str
    provider: str  # 'alipay' | 'wechatpay'
    amount_cny: float
    amount_krw: float
    exchange_rate: float
    status: str  # 'pending' | 'completed' | 'failed' | 'refunded'
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    receipt_url: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            'payment_id': self.payment_id,
            'order_id': self.order_id,
            'provider': self.provider,
            'amount_cny': self.amount_cny,
            'amount_krw': self.amount_krw,
            'exchange_rate': self.exchange_rate,
            'status': self.status,
            'created_at': self.created_at,
            'completed_at': self.completed_at,
            'receipt_url': self.receipt_url,
        }


class AlipayProvider:
    """알리페이 결제 mock."""

    MAX_SINGLE_CNY = 50000.0
    DAILY_LIMIT_CNY = 200000.0

    def __init__(self):
        self._daily_used_cny: float = 0.0

    def pay(self, order_id: str, amount_cny: float) -> Dict:
        if amount_cny > self.MAX_SINGLE_CNY:
            return {'success': False, 'error': f'단건 한도 초과: {self.MAX_SINGLE_CNY} CNY'}
        if self._daily_used_cny + amount_cny > self.DAILY_LIMIT_CNY:
            return {'success': False, 'error': '일일 한도 초과'}
        self._daily_used_cny += amount_cny
        payment_id = f'ALI_{uuid.uuid4().hex[:16].upper()}'
        logger.info("알리페이 결제 완료: %s (%.2f CNY)", payment_id, amount_cny)
        return {
            'success': True,
            'payment_id': payment_id,
            'order_id': order_id,
            'amount_cny': amount_cny,
            'transaction_id': f'2024{uuid.uuid4().hex[:20].upper()}',
        }

    def refund(self, payment_id: str, amount_cny: float) -> Dict:
        self._daily_used_cny = max(0, self._daily_used_cny - amount_cny)
        return {
            'success': True,
            'refund_id': f'REF_{uuid.uuid4().hex[:12].upper()}',
            'payment_id': payment_id,
            'amount_cny': amount_cny,
        }

    def reset_daily_limit(self) -> None:
        self._daily_used_cny = 0.0

    def get_limit_status(self) -> Dict:
        return {
            'provider': 'alipay',
            'daily_limit_cny': self.DAILY_LIMIT_CNY,
            'daily_used_cny': self._daily_used_cny,
            'daily_remaining_cny': self.DAILY_LIMIT_CNY - self._daily_used_cny,
            'single_limit_cny': self.MAX_SINGLE_CNY,
        }


class WechatPayProvider:
    """위챗페이 결제 mock."""

    MAX_SINGLE_CNY = 20000.0
    DAILY_LIMIT_CNY = 100000.0

    def __init__(self):
        self._daily_used_cny: float = 0.0

    def pay(self, order_id: str, amount_cny: float) -> Dict:
        if amount_cny > self.MAX_SINGLE_CNY:
            return {'success': False, 'error': f'단건 한도 초과: {self.MAX_SINGLE_CNY} CNY'}
        if self._daily_used_cny + amount_cny > self.DAILY_LIMIT_CNY:
            return {'success': False, 'error': '일일 한도 초과'}
        self._daily_used_cny += amount_cny
        payment_id = f'WX_{uuid.uuid4().hex[:16].upper()}'
        logger.info("위챗페이 결제 완료: %s (%.2f CNY)", payment_id, amount_cny)
        return {
            'success': True,
            'payment_id': payment_id,
            'order_id': order_id,
            'amount_cny': amount_cny,
            'transaction_id': f'4200{uuid.uuid4().hex[:20].upper()}',
        }

    def refund(self, payment_id: str, amount_cny: float) -> Dict:
        self._daily_used_cny = max(0, self._daily_used_cny - amount_cny)
        return {
            'success': True,
            'refund_id': f'REF_{uuid.uuid4().hex[:12].upper()}',
            'payment_id': payment_id,
            'amount_cny': amount_cny,
        }

    def reset_daily_limit(self) -> None:
        self._daily_used_cny = 0.0

    def get_limit_status(self) -> Dict:
        return {
            'provider': 'wechatpay',
            'daily_limit_cny': self.DAILY_LIMIT_CNY,
            'daily_used_cny': self._daily_used_cny,
            'daily_remaining_cny': self.DAILY_LIMIT_CNY - self._daily_used_cny,
            'single_limit_cny': self.MAX_SINGLE_CNY,
        }


class ChinaPaymentService:
    """중국 결제 서비스 (알리페이 + 위챗페이)."""

    def __init__(self, cny_krw_rate: float = DEFAULT_CNY_KRW_RATE):
        self._cny_krw_rate = cny_krw_rate
        self._alipay = AlipayProvider()
        self._wechatpay = WechatPayProvider()
        self._records: Dict[str, PaymentRecord] = {}

    # ── 환율 ─────────────────────────────────────────────────────────────────

    def convert_cny_to_krw(self, amount_cny: float) -> float:
        return round(amount_cny * self._cny_krw_rate, 0)

    def convert_krw_to_cny(self, amount_krw: float) -> float:
        return round(amount_krw / self._cny_krw_rate, 2)

    def update_exchange_rate(self, cny_krw_rate: float) -> None:
        self._cny_krw_rate = cny_krw_rate
        logger.info("환율 업데이트: 1 CNY = %.2f KRW", cny_krw_rate)

    def get_exchange_rate(self) -> Dict:
        return {
            'cny_krw': self._cny_krw_rate,
            'krw_cny': round(1 / self._cny_krw_rate, 6),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }

    # ── 결제 ─────────────────────────────────────────────────────────────────

    def pay(self, order_id: str, amount_cny: float, provider: str = 'alipay') -> PaymentRecord:
        """결제 처리 (알리페이/위챗페이)."""
        amount_krw = self.convert_cny_to_krw(amount_cny)

        if provider == 'alipay':
            result = self._alipay.pay(order_id, amount_cny)
        elif provider == 'wechatpay':
            result = self._wechatpay.pay(order_id, amount_cny)
        else:
            result = {'success': False, 'error': f'지원하지 않는 결제 수단: {provider}'}

        payment_id = result.get('payment_id', f'PAY_{uuid.uuid4().hex[:10].upper()}')
        status = 'completed' if result.get('success') else 'failed'
        completed_at = datetime.now(timezone.utc).isoformat() if status == 'completed' else None
        receipt_url = f'https://receipt.mock/{payment_id}.pdf' if status == 'completed' else None

        record = PaymentRecord(
            payment_id=payment_id,
            order_id=order_id,
            provider=provider,
            amount_cny=amount_cny,
            amount_krw=amount_krw,
            exchange_rate=self._cny_krw_rate,
            status=status,
            completed_at=completed_at,
            receipt_url=receipt_url,
        )
        self._records[payment_id] = record

        if not result.get('success'):
            logger.warning("결제 실패: %s — %s", order_id, result.get('error'))
        return record

    def refund(self, payment_id: str) -> Dict:
        """환불 처리."""
        record = self._records.get(payment_id)
        if not record:
            return {'success': False, 'error': '결제 내역을 찾을 수 없습니다.'}
        if record.status != 'completed':
            return {'success': False, 'error': '완료된 결제만 환불 가능합니다.'}

        if record.provider == 'alipay':
            result = self._alipay.refund(payment_id, record.amount_cny)
        else:
            result = self._wechatpay.refund(payment_id, record.amount_cny)

        if result.get('success'):
            record.status = 'refunded'
        return result

    # ── 조회 ─────────────────────────────────────────────────────────────────

    def get_record(self, payment_id: str) -> Optional[PaymentRecord]:
        return self._records.get(payment_id)

    def list_records(self, order_id: Optional[str] = None) -> List[PaymentRecord]:
        records = list(self._records.values())
        if order_id:
            records = [r for r in records if r.order_id == order_id]
        return records

    def get_limit_status(self) -> Dict:
        return {
            'alipay': self._alipay.get_limit_status(),
            'wechatpay': self._wechatpay.get_limit_status(),
        }

    def get_stats(self) -> Dict:
        records = list(self._records.values())
        total_cny = sum(r.amount_cny for r in records if r.status == 'completed')
        total_krw = sum(r.amount_krw for r in records if r.status == 'completed')
        by_provider: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        for r in records:
            by_provider[r.provider] = by_provider.get(r.provider, 0) + 1
            by_status[r.status] = by_status.get(r.status, 0) + 1
        return {
            'total_records': len(records),
            'total_amount_cny': round(total_cny, 2),
            'total_amount_krw': round(total_krw, 0),
            'by_provider': by_provider,
            'by_status': by_status,
        }
