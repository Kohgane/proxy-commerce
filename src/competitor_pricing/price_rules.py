"""src/competitor_pricing/price_rules.py — 경쟁사 가격 규칙 (Phase 111)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PriceRule:
    rule_id: str
    name: str
    condition: str
    action: str
    priority: int = 5
    is_active: bool = True
    created_at: str = field(
        default_factory=lambda: datetime.now(tz=timezone.utc).isoformat()
    )


class CompetitorPriceRules:
    """경쟁사 가격 규칙 관리."""

    def __init__(self) -> None:
        self._rules: Dict[str, PriceRule] = {}
        self._create_default_rules()

    # ── 기본 규칙 ─────────────────────────────────────────────────────────────

    def _create_default_rules(self) -> None:
        defaults = [
            {
                'name': '비싼_상품_알림',
                'condition': 'my_price > min_competitor_price * 1.2',
                'action': 'suggest_match_average',
                'priority': 8,
            },
            {
                'name': '경쟁사_인하_알림',
                'condition': 'competitor_price_drop > 10%',
                'action': 'alert_and_suggest_adjustment',
                'priority': 9,
            },
            {
                'name': '독점_판매',
                'condition': 'competitor_count == 0',
                'action': 'maintain_price_premium',
                'priority': 7,
            },
            {
                'name': '경쟁사_품절',
                'condition': 'all_competitors_unavailable == true',
                'action': 'suggest_price_increase',
                'priority': 6,
            },
            {
                'name': '마진_안전장치',
                'condition': 'margin_rate < 5%',
                'action': 'block_price_decrease_suggestions',
                'priority': 10,
            },
        ]
        for data in defaults:
            self.add_rule(data)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add_rule(self, rule_data: dict) -> PriceRule:
        """규칙 추가."""
        rule_id = rule_data.get('rule_id') or str(uuid.uuid4())
        rule = PriceRule(
            rule_id=rule_id,
            name=rule_data.get('name', ''),
            condition=rule_data.get('condition', ''),
            action=rule_data.get('action', ''),
            priority=int(rule_data.get('priority', 5)),
            is_active=bool(rule_data.get('is_active', True)),
        )
        self._rules[rule_id] = rule
        logger.info("규칙 추가: %s (%s)", rule_id, rule.name)
        return rule

    def remove_rule(self, rule_id: str) -> bool:
        """규칙 삭제."""
        if rule_id not in self._rules:
            return False
        del self._rules[rule_id]
        logger.info("규칙 삭제: %s", rule_id)
        return True

    def get_rules(self) -> List[PriceRule]:
        """전체 규칙 목록."""
        return sorted(self._rules.values(), key=lambda r: r.priority, reverse=True)

    # ── 규칙 평가 ─────────────────────────────────────────────────────────────

    def evaluate_rules(
        self, my_product_id: str, context: Optional[Dict[str, Any]] = None
    ) -> List[PriceRule]:
        """컨텍스트에 맞는 활성 규칙 목록 반환.

        실제 표현식 평가 대신, context 에 포함된 플래그에 따라 단순 매칭한다.
        """
        ctx = context or {}
        matched: List[PriceRule] = []
        for rule in self.get_rules():
            if not rule.is_active:
                continue
            if self._matches_condition(rule.condition, ctx):
                matched.append(rule)
        return matched

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    @staticmethod
    def _matches_condition(condition: str, ctx: dict) -> bool:
        """조건 문자열을 단순 키워드로 매칭."""
        if 'my_price > min_competitor_price' in condition:
            return ctx.get('my_price_above_min', False)
        if 'competitor_price_drop' in condition:
            return ctx.get('competitor_price_dropped', False)
        if 'competitor_count == 0' in condition:
            return ctx.get('competitor_count', 1) == 0
        if 'all_competitors_unavailable' in condition:
            return ctx.get('all_competitors_unavailable', False)
        if 'margin_rate < 5%' in condition:
            margin = ctx.get('margin_rate', 100.0)
            return isinstance(margin, (int, float)) and margin < 5.0
        # 알 수 없는 조건은 기본 불일치
        return False
