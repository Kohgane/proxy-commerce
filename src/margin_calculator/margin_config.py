"""src/margin_calculator/margin_config.py — 마진 계산 설정 관리 (Phase 110).

MarginConfig: 전역/카테고리별/상품별 마진 설정 관리
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 기본 설정값
_DEFAULT_CONFIG: Dict[str, Any] = {
    'default_target_margin': 15.0,       # 기본 목표 마진율 (%)
    'critical_margin_threshold': 0.0,    # 적자 임계값 (%)
    'warning_margin_threshold': 5.0,     # 저마진 임계값 (%)
    'exchange_spread_rate': 1.5,         # 환율 스프레드 (%)
    'return_reserve_rate': 2.0,          # 반품 충당금 비율 (%)
    'default_packaging_cost': 1000.0,    # 기본 포장비 (원)
    'default_labeling_cost': 500.0,      # 기본 라벨링비 (원)
    'vat_rate': 10.0,                    # 부가세율 (%)
}


class MarginConfig:
    """마진 계산 설정 관리."""

    def __init__(self) -> None:
        self._global: Dict[str, Any] = dict(_DEFAULT_CONFIG)
        self._by_category: Dict[str, Dict[str, Any]] = {}
        self._by_product: Dict[str, Dict[str, Any]] = {}

    # ── 조회 ──────────────────────────────────────────────────────────────────

    def get_config(
        self,
        product_id: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """적용될 설정 반환 (상품별 > 카테고리별 > 전역 순).

        Returns:
            merged config dict
        """
        merged = dict(self._global)
        if category and category in self._by_category:
            merged.update(self._by_category[category])
        if product_id and product_id in self._by_product:
            merged.update(self._by_product[product_id])
        return merged

    def get_global_config(self) -> Dict[str, Any]:
        """전역 설정 반환."""
        return dict(self._global)

    def get_category_config(self, category: str) -> Dict[str, Any]:
        """카테고리별 설정 반환."""
        return dict(self._by_category.get(category, {}))

    def get_product_config(self, product_id: str) -> Dict[str, Any]:
        """상품별 설정 반환."""
        return dict(self._by_product.get(product_id, {}))

    # ── 업데이트 ──────────────────────────────────────────────────────────────

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """전역 설정 업데이트."""
        allowed_keys = set(_DEFAULT_CONFIG.keys())
        for key, value in updates.items():
            if key in allowed_keys:
                self._global[key] = value
            else:
                logger.warning("알 수 없는 설정 키: %s", key)
        return dict(self._global)

    def set_category_config(self, category: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """카테고리별 설정 오버라이드."""
        if category not in self._by_category:
            self._by_category[category] = {}
        self._by_category[category].update(updates)
        return dict(self._by_category[category])

    def set_product_config(self, product_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """상품별 설정 오버라이드."""
        if product_id not in self._by_product:
            self._by_product[product_id] = {}
        self._by_product[product_id].update(updates)
        return dict(self._by_product[product_id])

    def reset_to_defaults(self) -> Dict[str, Any]:
        """전역 설정을 기본값으로 초기화."""
        self._global = dict(_DEFAULT_CONFIG)
        return dict(self._global)
