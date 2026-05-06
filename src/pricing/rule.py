"""src/pricing/rule.py — 가격 정책 룰 모델 + 저장소 (Phase 136).

PricingRule: 단일 가격 정책 룰 dataclass
PricingRuleStore: Sheets 기반 룰 CRUD
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

logger = logging.getLogger(__name__)

_WORKSHEET_NAME = "pricing_rules"
_HEADERS = [
    "rule_id", "name", "enabled", "priority",
    "scope_type", "scope_value",
    "triggers_json",
    "action_kind", "action_value", "action_floor_krw", "action_ceiling_krw",
    "dry_run", "notify_threshold_pct",
    "last_run_at", "last_changed_count",
]


@dataclass
class PricingRule:
    """단일 가격 정책 룰.

    Attributes:
        rule_id: 고유 식별자 (UUID)
        name: 룰 이름 (한국어 가능)
        enabled: 활성 여부
        priority: 평가 순서 (낮을수록 먼저)
        scope_type: 적용 범위 타입 (all / domain / category / sku_list)
        scope_value: 범위 값 (domain 또는 category 문자열, sku_list는 콤마 구분)
        triggers: 트리거 조건 list (AND 결합)
        action_kind: 액션 종류 (set_margin / multiply / add / match_competitor / notify_only)
        action_value: 액션 파라미터
        action_floor_krw: 최저가 가드 (원)
        action_ceiling_krw: 최고가 가드 (원)
        dry_run: True이면 시뮬레이션만 (실제 가격 변경 없음)
        notify_threshold_pct: 이 % 이상 변동 시 텔레그램 알림
        last_run_at: 마지막 실행 시각 (ISO 8601)
        last_changed_count: 마지막 실행 시 변경된 SKU 수
    """

    rule_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    enabled: bool = True
    priority: int = 100

    scope_type: str = "all"
    scope_value: str = ""

    triggers: List[dict] = field(default_factory=list)
    # 트리거 예시:
    #   {"kind": "min_margin_pct", "op": "<", "value": 15}
    #   {"kind": "fx_change_pct", "currency": "USD", "op": ">=", "value": 3}
    #   {"kind": "stock_qty", "op": "<=", "value": 5}
    #   {"kind": "weekday", "in": ["sat", "sun"]}
    #   {"kind": "competitor_min_lt_self", "margin_pct": 5}
    #   {"kind": "days_since_listing", "op": ">=", "value": 30}

    action_kind: str = "notify_only"
    action_value: Decimal = field(default_factory=lambda: Decimal("0"))
    action_floor_krw: Optional[int] = None
    action_ceiling_krw: Optional[int] = None

    dry_run: bool = True
    notify_threshold_pct: Decimal = field(default_factory=lambda: Decimal("10"))
    last_run_at: Optional[str] = None
    last_changed_count: int = 0

    def to_dict(self) -> dict:
        """직렬화 (JSON/Sheets 저장용)."""
        import json
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "enabled": self.enabled,
            "priority": self.priority,
            "scope_type": self.scope_type,
            "scope_value": self.scope_value,
            "triggers": self.triggers,
            "action_kind": self.action_kind,
            "action_value": str(self.action_value),
            "action_floor_krw": self.action_floor_krw,
            "action_ceiling_krw": self.action_ceiling_krw,
            "dry_run": self.dry_run,
            "notify_threshold_pct": str(self.notify_threshold_pct),
            "last_run_at": self.last_run_at,
            "last_changed_count": self.last_changed_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PricingRule":
        """역직렬화."""
        import json

        def _bool(v) -> bool:
            if isinstance(v, bool):
                return v
            return str(v).strip().lower() in ("1", "true", "yes")

        def _int_or_none(v) -> Optional[int]:
            if v is None or v == "":
                return None
            try:
                return int(v)
            except (ValueError, TypeError):
                return None

        triggers_raw = d.get("triggers", [])
        if isinstance(triggers_raw, str):
            try:
                triggers_raw = json.loads(triggers_raw)
            except Exception:
                triggers_raw = []

        return cls(
            rule_id=d.get("rule_id") or str(uuid.uuid4()),
            name=d.get("name", ""),
            enabled=_bool(d.get("enabled", True)),
            priority=int(d.get("priority", 100)),
            scope_type=d.get("scope_type", "all"),
            scope_value=d.get("scope_value", ""),
            triggers=triggers_raw,
            action_kind=d.get("action_kind", "notify_only"),
            action_value=Decimal(str(d.get("action_value", "0"))),
            action_floor_krw=_int_or_none(d.get("action_floor_krw")),
            action_ceiling_krw=_int_or_none(d.get("action_ceiling_krw")),
            dry_run=_bool(d.get("dry_run", True)),
            notify_threshold_pct=Decimal(str(d.get("notify_threshold_pct", "10"))),
            last_run_at=d.get("last_run_at") or None,
            last_changed_count=int(d.get("last_changed_count", 0)),
        )


class PricingRuleStore:
    """가격 룰 Sheets 저장소.

    Sheets 워크시트 ``pricing_rules`` 에 룰을 저장/조회/수정/삭제.
    키 미설정 시 메모리 폴백.
    """

    def __init__(self):
        self._memory: List[PricingRule] = []

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────

    def _open_ws(self):
        """Sheets 워크시트 열기 (없으면 생성)."""
        try:
            from src.utils.sheets import open_sheet
            ws = open_sheet(_WORKSHEET_NAME)
            # 헤더 없으면 초기화
            existing = ws.row_values(1)
            if not existing:
                ws.append_row(_HEADERS)
            return ws
        except Exception as exc:
            logger.debug("pricing_rules Sheets 열기 실패: %s", exc)
            return None

    def _row_to_rule(self, row: dict) -> PricingRule:
        """Sheets 행 dict → PricingRule."""
        return PricingRule.from_dict(row)

    def _rule_to_row(self, rule: PricingRule) -> list:
        """PricingRule → Sheets 행 list (헤더 순서대로)."""
        import json
        d = rule.to_dict()
        return [
            d["rule_id"],
            d["name"],
            str(d["enabled"]),
            str(d["priority"]),
            d["scope_type"],
            d["scope_value"],
            json.dumps(d["triggers"], ensure_ascii=False),
            d["action_kind"],
            d["action_value"],
            str(d["action_floor_krw"] or ""),
            str(d["action_ceiling_krw"] or ""),
            str(d["dry_run"]),
            d["notify_threshold_pct"],
            d["last_run_at"] or "",
            str(d["last_changed_count"]),
        ]

    # ── 공개 API ──────────────────────────────────────────────────────────

    def list_all(self) -> List[PricingRule]:
        """모든 룰 조회 (우선순위 오름차순)."""
        ws = self._open_ws()
        if ws is None:
            return sorted(self._memory, key=lambda r: r.priority)
        try:
            rows = ws.get_all_records()
            rules = []
            for row in rows:
                try:
                    rules.append(self._row_to_rule(row))
                except Exception as exc:
                    logger.warning("룰 파싱 실패: %s — %s", row, exc)
            return sorted(rules, key=lambda r: r.priority)
        except Exception as exc:
            logger.warning("pricing_rules list_all 실패: %s", exc)
            return sorted(self._memory, key=lambda r: r.priority)

    def active_sorted(self) -> List[PricingRule]:
        """활성 룰만, 우선순위 오름차순."""
        return [r for r in self.list_all() if r.enabled]

    def get(self, rule_id: str) -> Optional[PricingRule]:
        """ID로 룰 조회."""
        for rule in self.list_all():
            if rule.rule_id == rule_id:
                return rule
        return None

    def create(self, rule: PricingRule) -> PricingRule:
        """룰 생성."""
        ws = self._open_ws()
        if ws is None:
            self._memory.append(rule)
            return rule
        try:
            ws.append_row(self._rule_to_row(rule))
            logger.info("룰 생성: %s (%s)", rule.name, rule.rule_id)
        except Exception as exc:
            logger.warning("룰 생성 실패 (Sheets): %s", exc)
            self._memory.append(rule)
        return rule

    def update(self, rule: PricingRule) -> bool:
        """룰 업데이트 (rule_id로 행 찾아 덮어쓰기)."""
        ws = self._open_ws()
        if ws is None:
            for i, r in enumerate(self._memory):
                if r.rule_id == rule.rule_id:
                    self._memory[i] = rule
                    return True
            return False
        try:
            rows = ws.get_all_records()
            for i, row in enumerate(rows):
                if row.get("rule_id") == rule.rule_id:
                    row_num = i + 2  # 헤더 포함 1-indexed
                    new_row = self._rule_to_row(rule)
                    for col_idx, val in enumerate(new_row, start=1):
                        ws.update_cell(row_num, col_idx, val)
                    logger.info("룰 업데이트: %s", rule.rule_id)
                    return True
        except Exception as exc:
            logger.warning("룰 업데이트 실패: %s", exc)
        return False

    def delete(self, rule_id: str) -> bool:
        """룰 삭제."""
        ws = self._open_ws()
        if ws is None:
            before = len(self._memory)
            self._memory = [r for r in self._memory if r.rule_id != rule_id]
            return len(self._memory) < before
        try:
            rows = ws.get_all_records()
            for i, row in enumerate(rows):
                if row.get("rule_id") == rule_id:
                    ws.delete_rows(i + 2)
                    logger.info("룰 삭제: %s", rule_id)
                    return True
        except Exception as exc:
            logger.warning("룰 삭제 실패: %s", exc)
        return False

    def reorder(self, ordered_ids: List[str]) -> bool:
        """priority를 ordered_ids 순서대로 재설정."""
        all_rules = {r.rule_id: r for r in self.list_all()}
        for idx, rule_id in enumerate(ordered_ids):
            rule = all_rules.get(rule_id)
            if rule:
                rule.priority = (idx + 1) * 10
                self.update(rule)
        return True

    def toggle(self, rule_id: str) -> Optional[bool]:
        """룰 활성/비활성 토글. 새 상태 반환."""
        rule = self.get(rule_id)
        if not rule:
            return None
        rule.enabled = not rule.enabled
        self.update(rule)
        return rule.enabled

    def update_stats(self, rule_id: str, run_at: str, changed_count: int):
        """실행 통계 업데이트."""
        rule = self.get(rule_id)
        if rule:
            rule.last_run_at = run_at
            rule.last_changed_count = changed_count
            self.update(rule)
