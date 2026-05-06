"""src/collectors/adapters — 브랜드별 수집 어댑터 패키지 (Phase 135)."""
from .base_adapter import BrandAdapter, ScrapedProduct
from .alo_adapter import AloAdapter
from .lululemon_adapter import LululemonAdapter
from .marketstudio_adapter import MarketStudioAdapter
from .pleasures_adapter import PleasuresAdapter
from .yoshida_kaban_adapter import YoshidaKabanAdapter

__all__ = [
    "BrandAdapter",
    "ScrapedProduct",
    "AloAdapter",
    "LululemonAdapter",
    "MarketStudioAdapter",
    "PleasuresAdapter",
    "YoshidaKabanAdapter",
]
