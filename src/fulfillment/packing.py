"""src/fulfillment/packing.py — 포장 서비스 (Phase 103)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PackingType(str, Enum):
    standard = 'standard'
    fragile = 'fragile'
    oversized = 'oversized'
    multi_item = 'multi_item'


@dataclass
class PackingResult:
    packing_id: str
    order_id: str
    packing_type: PackingType
    weight_kg: float
    dimensions_cm: Dict[str, float]  # {'length': x, 'width': y, 'height': z}
    materials_used: List[str] = field(default_factory=list)
    packed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str = ''


class PackingService:
    """주문별 최적 포장 방법 결정 및 포장 서비스."""

    _MATERIAL_MAP = {
        PackingType.standard: ['표준박스', '완충재', '테이프'],
        PackingType.fragile: ['충격방지박스', '에어캡', '완충재', '취급주의 스티커'],
        PackingType.oversized: ['대형박스', '완충재', '테이프', '중량물 스티커'],
        PackingType.multi_item: ['통합박스', '분리완충재', '에어캡', '테이프'],
    }

    def __init__(self):
        self._results: List[PackingResult] = []
        self._consolidated_groups: Dict[str, List[str]] = {}  # recipient_key -> order_ids

    def determine_packing_type(self, items: List[Dict]) -> PackingType:
        """상품 특성에 따라 최적 포장 타입을 결정한다."""
        if len(items) > 1:
            return PackingType.multi_item
        if not items:
            return PackingType.standard
        item = items[0]
        if item.get('fragile'):
            return PackingType.fragile
        weight = item.get('weight_kg', 0)
        if weight > 10 or item.get('oversized'):
            return PackingType.oversized
        return PackingType.standard

    def pack(self, order_id: str, items: List[Dict]) -> PackingResult:
        """포장을 수행하고 결과를 반환한다."""
        packing_id = f'pack_{uuid.uuid4().hex[:8]}'
        packing_type = self.determine_packing_type(items)
        total_weight = sum(item.get('weight_kg', 0.5) for item in items) + 0.3  # +포장재 무게
        dimensions = self._calculate_dimensions(items)
        materials = self._MATERIAL_MAP[packing_type]
        result = PackingResult(
            packing_id=packing_id,
            order_id=order_id,
            packing_type=packing_type,
            weight_kg=round(total_weight, 2),
            dimensions_cm=dimensions,
            materials_used=materials,
        )
        self._results.append(result)
        logger.info("포장 완료: %s, 타입: %s", order_id, packing_type.value)
        return result

    def consolidate_orders(self, recipient_key: str, order_ids: List[str]) -> str:
        """동일 수령인 복수 주문 합포장 그룹을 생성한다."""
        group_id = f'consolidation_{uuid.uuid4().hex[:8]}'
        self._consolidated_groups[group_id] = order_ids
        logger.info("합포장 그룹 생성: %s (%d건)", group_id, len(order_ids))
        return group_id

    def get_results(self, order_id: Optional[str] = None) -> List[PackingResult]:
        if order_id:
            return [r for r in self._results if r.order_id == order_id]
        return list(self._results)

    def _calculate_dimensions(self, items: List[Dict]) -> Dict[str, float]:
        base = {'length': 20.0, 'width': 15.0, 'height': 10.0}
        for item in items:
            dims = item.get('dimensions_cm', {})
            base['length'] = max(base['length'], dims.get('length', 0))
            base['width'] = max(base['width'], dims.get('width', 0))
            base['height'] += dims.get('height', 5.0)
        return {k: round(v, 1) for k, v in base.items()}

    def get_stats(self) -> Dict:
        stats: Dict[str, int] = {t.value: 0 for t in PackingType}
        for r in self._results:
            stats[r.packing_type.value] += 1
        return {'total': len(self._results), 'by_type': stats}
