"""src/exception_handler/__init__.py — 예외 처리 패키지 (Phase 105)."""
from .engine import ExceptionEngine, ExceptionCase, ExceptionType, ExceptionSeverity, ExceptionStatus
from .damage_handler import DamageHandler, DamageReport, DamageType, DamageGrade
from .price_detector import PriceChangeDetector, PriceAlert, PriceAlertType
from .retry_manager import RetryManager, RetryPolicy, BackoffStrategy, RetryRecord, RetryStatus
from .auto_recovery import (
    AutoRecoveryService,
    RecoveryAction,
    ReorderAction,
    RefundAction,
    RerouteAction,
    EscalateAction,
    CompensateAction,
    RecoveryAttempt,
)
from .delay_handler import DeliveryDelayHandler, DelayRecord, DelayStage, DelayAction
from .payment_failure import PaymentFailureHandler, PaymentFailureRecord, PaymentFailureReason, PaymentFailureStatus
from .dashboard import ExceptionDashboard

__all__ = [
    # engine
    'ExceptionEngine', 'ExceptionCase', 'ExceptionType', 'ExceptionSeverity', 'ExceptionStatus',
    # damage
    'DamageHandler', 'DamageReport', 'DamageType', 'DamageGrade',
    # price
    'PriceChangeDetector', 'PriceAlert', 'PriceAlertType',
    # retry
    'RetryManager', 'RetryPolicy', 'BackoffStrategy', 'RetryRecord', 'RetryStatus',
    # recovery
    'AutoRecoveryService', 'RecoveryAction',
    'ReorderAction', 'RefundAction', 'RerouteAction', 'EscalateAction', 'CompensateAction',
    'RecoveryAttempt',
    # delay
    'DeliveryDelayHandler', 'DelayRecord', 'DelayStage', 'DelayAction',
    # payment failure
    'PaymentFailureHandler', 'PaymentFailureRecord', 'PaymentFailureReason', 'PaymentFailureStatus',
    # dashboard
    'ExceptionDashboard',
]
