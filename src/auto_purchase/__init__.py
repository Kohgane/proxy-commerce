"""src/auto_purchase/ — 자동 구매 엔진 패키지 (Phase 96)."""

from .purchase_models import (
    PurchaseOrder,
    PurchaseStatus,
    SourceOption,
    PurchaseResult,
    PurchaseMetrics,
)
from .purchase_engine import AutoPurchaseEngine
from .source_selector import SourceSelector, SelectionStrategy
from .marketplace_buyer import MarketplaceBuyer, AmazonBuyer, TaobaoBuyer, AlibabaBuyer
from .payment_automator import PaymentAutomator, PaymentMethod
from .purchase_monitor import PurchaseMonitor
from .purchase_rules import PurchaseRuleEngine

__all__ = [
    'PurchaseOrder',
    'PurchaseStatus',
    'SourceOption',
    'PurchaseResult',
    'PurchaseMetrics',
    'AutoPurchaseEngine',
    'SourceSelector',
    'SelectionStrategy',
    'MarketplaceBuyer',
    'AmazonBuyer',
    'TaobaoBuyer',
    'AlibabaBuyer',
    'PaymentAutomator',
    'PaymentMethod',
    'PurchaseMonitor',
    'PurchaseRuleEngine',
]
