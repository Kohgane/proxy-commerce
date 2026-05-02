"""src/forwarding_integration/__init__.py — 배송대행 통합 패키지 (Phase 83)."""
from .models import (
    ConsolidationRequest,
    ForwardingPackage,
    ForwardingStatus,
    InboundRegistration,
    OutboundRequest,
)
from .provider_registry import ProviderRegistry, get_default_registry
from .forwarding_engine import ForwardingEngine
from .providers import ForwardingProvider, MalltailProvider, IHanexProvider, OhMyZipProvider

__all__ = [
    'ForwardingPackage',
    'InboundRegistration',
    'ConsolidationRequest',
    'OutboundRequest',
    'ForwardingStatus',
    'ForwardingProvider',
    'MalltailProvider',
    'IHanexProvider',
    'OhMyZipProvider',
    'ProviderRegistry',
    'get_default_registry',
    'ForwardingEngine',
]
