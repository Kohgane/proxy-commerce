"""src/subscriptions/billing.py — 청구서 및 결제 처리 (Phase 92).

청구서 생성/조회, mock PG 결제 처리, 결제 실패 시 재시도 로직을 담당한다.

재시도 정책: 최대 3회, 3일 간격
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_RETRY = 3
RETRY_INTERVAL_DAYS = 3


class InvoiceStatus(str, Enum):
    """청구서 상태."""

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    VOID = "void"


class PaymentStatus(str, Enum):
    """결제 상태."""

    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class Invoice:
    """청구서 엔티티."""

    invoice_id: str
    subscription_id: str
    user_id: str
    amount: int  # 원화
    plan_id: str
    billing_cycle: str
    status: InvoiceStatus = InvoiceStatus.PENDING
    retry_count: int = 0
    next_retry_at: Optional[str] = None
    paid_at: Optional[str] = None
    receipt_id: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        """딕셔너리로 변환한다."""
        return {
            "invoice_id": self.invoice_id,
            "subscription_id": self.subscription_id,
            "user_id": self.user_id,
            "amount": self.amount,
            "plan_id": self.plan_id,
            "billing_cycle": self.billing_cycle,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "next_retry_at": self.next_retry_at,
            "paid_at": self.paid_at,
            "receipt_id": self.receipt_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class Receipt:
    """영수증 엔티티."""

    receipt_id: str
    invoice_id: str
    subscription_id: str
    user_id: str
    amount: int
    issued_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        """딕셔너리로 변환한다."""
        return {
            "receipt_id": self.receipt_id,
            "invoice_id": self.invoice_id,
            "subscription_id": self.subscription_id,
            "user_id": self.user_id,
            "amount": self.amount,
            "issued_at": self.issued_at,
        }


class BillingService:
    """청구서 생성 및 결제 처리 서비스 (mock PG 연동)."""

    def __init__(self, plan_manager=None) -> None:
        self._invoices: Dict[str, Invoice] = {}
        self._receipts: Dict[str, Receipt] = {}
        self._plan_manager = plan_manager

    def _get_plan_manager(self):
        if self._plan_manager is None:
            from .plan_manager import PlanManager
            self._plan_manager = PlanManager()
        return self._plan_manager

    # ------------------------------------------------------------------
    # 청구서 생성
    # ------------------------------------------------------------------

    def create_invoice(
        self,
        subscription_id: str,
        user_id: str,
        plan_id: str,
        billing_cycle: str,
    ) -> Invoice:
        """청구서를 생성한다."""
        pm = self._get_plan_manager()
        plan = pm.get_plan(plan_id)
        if plan is None:
            raise ValueError(f"플랜을 찾을 수 없습니다: {plan_id}")

        amount = plan.annual_price if billing_cycle == "annual" else plan.monthly_price
        invoice = Invoice(
            invoice_id=str(uuid.uuid4()),
            subscription_id=subscription_id,
            user_id=user_id,
            amount=amount,
            plan_id=plan_id,
            billing_cycle=billing_cycle,
        )
        self._invoices[invoice.invoice_id] = invoice
        logger.info("청구서 생성: id=%s amount=%d", invoice.invoice_id, amount)
        return invoice

    def get_invoice(self, invoice_id: str) -> Optional[Invoice]:
        """청구서를 조회한다."""
        return self._invoices.get(invoice_id)

    def list_invoices(self, subscription_id: str) -> List[Invoice]:
        """구독에 대한 청구서 목록을 반환한다."""
        return [i for i in self._invoices.values() if i.subscription_id == subscription_id]

    # ------------------------------------------------------------------
    # 결제 처리 (mock)
    # ------------------------------------------------------------------

    def process_payment(self, invoice_id: str, force_fail: bool = False) -> dict:
        """결제를 처리한다 (mock PG 연동).

        Args:
            invoice_id: 청구서 ID
            force_fail: 테스트용 강제 실패 플래그

        Returns:
            {"status": "success"|"failed", "invoice": ..., "receipt": ...}
        """
        invoice = self._invoices.get(invoice_id)
        if invoice is None:
            raise ValueError(f"청구서를 찾을 수 없습니다: {invoice_id}")
        if invoice.status == InvoiceStatus.PAID:
            raise ValueError("이미 결제된 청구서입니다.")
        if invoice.status == InvoiceStatus.VOID:
            raise ValueError("취소된 청구서입니다.")

        now = datetime.now(timezone.utc)
        # mock: 무료 플랜(0원)은 항상 성공, force_fail이면 실패
        success = (invoice.amount == 0 or not force_fail)

        if success:
            receipt = self._issue_receipt(invoice, now)
            invoice.status = InvoiceStatus.PAID
            invoice.paid_at = now.isoformat()
            invoice.receipt_id = receipt.receipt_id
            invoice.updated_at = now.isoformat()
            logger.info("결제 성공: invoice=%s receipt=%s", invoice_id, receipt.receipt_id)
            return {
                "status": PaymentStatus.SUCCESS.value,
                "invoice": invoice.to_dict(),
                "receipt": receipt.to_dict(),
            }
        else:
            return self._handle_failure(invoice, now)

    def _handle_failure(self, invoice: Invoice, now: datetime) -> dict:
        """결제 실패 처리 — 재시도 스케줄링."""
        invoice.retry_count += 1
        if invoice.retry_count >= MAX_RETRY:
            invoice.status = InvoiceStatus.FAILED
            invoice.next_retry_at = None
            logger.warning("결제 최종 실패: invoice=%s retries=%d", invoice.invoice_id, invoice.retry_count)
            status = PaymentStatus.FAILED.value
        else:
            next_retry = now + timedelta(days=RETRY_INTERVAL_DAYS)
            invoice.next_retry_at = next_retry.isoformat()
            logger.warning(
                "결제 실패 (재시도 %d/%d 예정: %s): invoice=%s",
                invoice.retry_count,
                MAX_RETRY,
                invoice.next_retry_at,
                invoice.invoice_id,
            )
            status = PaymentStatus.RETRYING.value
        invoice.updated_at = now.isoformat()
        return {
            "status": status,
            "invoice": invoice.to_dict(),
            "receipt": None,
        }

    # ------------------------------------------------------------------
    # 영수증
    # ------------------------------------------------------------------

    def _issue_receipt(self, invoice: Invoice, now: datetime) -> Receipt:
        """영수증을 발급한다."""
        receipt = Receipt(
            receipt_id=str(uuid.uuid4()),
            invoice_id=invoice.invoice_id,
            subscription_id=invoice.subscription_id,
            user_id=invoice.user_id,
            amount=invoice.amount,
            issued_at=now.isoformat(),
        )
        self._receipts[receipt.receipt_id] = receipt
        return receipt

    def get_receipt(self, receipt_id: str) -> Optional[Receipt]:
        """영수증을 조회한다."""
        return self._receipts.get(receipt_id)
