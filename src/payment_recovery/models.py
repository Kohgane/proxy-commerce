"""src/payment_recovery/models.py — 결제 복구 모델."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FailedPayment:
    """실패한 결제 정보."""

    payment_id: str
    order_id: str
    amount: float
    error_code: str
    attempts: int = 0
    status: str = 'failed'
