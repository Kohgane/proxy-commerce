"""src/channel_sync/product_mapper.py — 소싱처 상품 → 판매채널 상품 데이터 변환 (Phase 109).

ProductMapper: 소싱처 원본 데이터를 판매채널별 형식으로 변환
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# 마진율 기본값 (채널별)
DEFAULT_MARGIN_RATES: Dict[str, float] = {
    'coupang': 0.30,
    'naver': 0.25,
    'internal': 0.35,
}

# 환율 기본값 (통화 → KRW)
DEFAULT_FX_RATES: Dict[str, float] = {
    'KRW': 1.0,
    'CNY': 190.0,
    'USD': 1350.0,
    'JPY': 9.0,
    'EUR': 1480.0,
}

# 카테고리 매핑 (소싱처 → 표준)
CATEGORY_NORMALIZE_MAP: Dict[str, str] = {
    '전자제품': 'electronics',
    '전자': 'electronics',
    'electronics': 'electronics',
    '패션': 'fashion',
    'fashion': 'fashion',
    '뷰티': 'beauty',
    'beauty': 'beauty',
    '생활': 'home',
    '홈': 'home',
    'home': 'home',
    '식품': 'food',
    'food': 'food',
    '스포츠': 'sports',
    'sports': 'sports',
    '완구': 'toys',
    'toys': 'toys',
    '도서': 'books',
    'books': 'books',
}


class ProductMapper:
    """소싱처 상품 데이터 → 판매채널 상품 데이터 변환기."""

    def __init__(
        self,
        margin_rates: Optional[Dict[str, float]] = None,
        fx_rates: Optional[Dict[str, float]] = None,
    ):
        self._margin_rates: Dict[str, float] = margin_rates or dict(DEFAULT_MARGIN_RATES)
        self._fx_rates: Dict[str, float] = fx_rates or dict(DEFAULT_FX_RATES)

    # ── 메인 변환 메서드 ──────────────────────────────────────────────────────

    def map_product(self, source_product: dict, target_channel: str) -> dict:
        """소싱처 상품 → 채널별 상품 데이터 변환."""
        channel = target_channel.lower()

        krw_price = self._convert_price_to_krw(
            source_product.get('price', 0),
            source_product.get('currency', 'KRW'),
        )
        sale_price = self._apply_margin(krw_price, channel)
        category = self._map_category(source_product.get('category', ''))
        title = self._transform_title(source_product.get('title', ''), channel)
        description = self._transform_description(source_product.get('description', ''), channel)
        images = self._transform_images(source_product.get('images', []))
        options = self._map_options(source_product.get('options', []), channel)

        return {
            'product_id': source_product.get('product_id', ''),
            'title': title,
            'description': description,
            'price': sale_price,
            'original_price': krw_price,
            'currency': 'KRW',
            'category': category,
            'images': images,
            'stock': source_product.get('stock', 0),
            'options': options,
            'tags': source_product.get('tags', []),
            'channel': channel,
            'source_product_id': source_product.get('source_product_id', ''),
        }

    # ── 가격 변환 ─────────────────────────────────────────────────────────────

    def _convert_price_to_krw(self, price: float, currency: str) -> float:
        """원가를 KRW으로 환산."""
        rate = self._fx_rates.get(currency.upper(), 1.0)
        return round(price * rate)

    def _apply_margin(self, krw_price: float, channel: str) -> float:
        """마진 적용 판매가 계산."""
        margin_rate = self._margin_rates.get(channel, 0.30)
        if krw_price <= 0:
            return 0.0
        return round(krw_price * (1 + margin_rate))

    def update_margin_rate(self, channel: str, rate: float) -> None:
        """채널별 마진율 업데이트."""
        self._margin_rates[channel] = rate

    def update_fx_rate(self, currency: str, rate: float) -> None:
        """환율 업데이트."""
        self._fx_rates[currency.upper()] = rate

    # ── 카테고리 매핑 ─────────────────────────────────────────────────────────

    def _map_category(self, source_category: str) -> str:
        """소싱처 카테고리 → 표준 카테고리."""
        if not source_category:
            return 'default'
        normalized = CATEGORY_NORMALIZE_MAP.get(source_category)
        if normalized:
            return normalized
        # 부분 매칭 시도
        lower = source_category.lower()
        for key, value in CATEGORY_NORMALIZE_MAP.items():
            if key.lower() in lower:
                return value
        return 'default'

    # ── 제목 변환 ─────────────────────────────────────────────────────────────

    def _transform_title(self, title: str, channel: str) -> str:
        """소싱처 제목 → 채널별 판매 제목 변환."""
        if not title:
            return ''
        # 채널별 최대 길이 제한
        max_lengths = {'coupang': 100, 'naver': 100, 'internal': 200}
        max_len = max_lengths.get(channel, 100)
        transformed = title.strip()
        if len(transformed) > max_len:
            transformed = transformed[:max_len]
        return transformed

    # ── 설명 변환 ─────────────────────────────────────────────────────────────

    def _transform_description(self, description: str, channel: str) -> str:
        """소싱처 설명 → 판매용 상세 설명 변환."""
        if not description:
            return ''
        return description.strip()

    # ── 이미지 변환 ───────────────────────────────────────────────────────────

    def _transform_images(self, images: list) -> List[str]:
        """소싱처 이미지 URL → CDN URL (mock: 그대로 반환)."""
        if not images:
            return []
        return [str(img) for img in images if img]

    # ── 옵션/속성 매핑 ────────────────────────────────────────────────────────

    def _map_options(self, options: list, channel: str) -> List[dict]:
        """소싱처 옵션 → 판매채널 옵션 체계 변환."""
        if not options:
            return []
        mapped = []
        for opt in options:
            if isinstance(opt, dict):
                mapped.append({
                    'name': opt.get('name', ''),
                    'values': opt.get('values', []),
                    'channel': channel,
                })
            elif isinstance(opt, str):
                mapped.append({'name': opt, 'values': [], 'channel': channel})
        return mapped
