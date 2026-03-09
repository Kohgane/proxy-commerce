"""src/vendors 패키지 — 소싱 벤더 레지스트리."""

from .base_vendor import BaseVendor, CATALOG_FIELDS
from .porter import PorterVendor
from .memo_paris import MemoPariVendor

# 벤더 이름 → 벤더 클래스 매핑
VENDOR_REGISTRY = {
    'porter': PorterVendor,
    'memo_paris': MemoPariVendor,
}


def get_vendor(vendor_name: str) -> BaseVendor:
    """벤더 이름으로 벤더 인스턴스 반환."""
    cls = VENDOR_REGISTRY.get(vendor_name.lower())
    if cls is None:
        raise ValueError(f"Unknown vendor: {vendor_name}")
    return cls()


__all__ = [
    'BaseVendor',
    'CATALOG_FIELDS',
    'PorterVendor',
    'MemoPariVendor',
    'VENDOR_REGISTRY',
    'get_vendor',
]
