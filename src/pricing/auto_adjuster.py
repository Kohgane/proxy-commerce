"""src/pricing/auto_adjuster.py — Phase 140 자동 가격 조정기."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from src.pricing.margin_guard import MarginGuard

logger = logging.getLogger(__name__)


class PricingAutoAdjuster:
    def __init__(self):
        self.margin_guard = MarginGuard()
        self.auto_apply = os.getenv("PRICING_AUTO_APPLY", "0") == "1"
        self.auto_apply_threshold_pct = Decimal(os.getenv("PRICING_AUTO_APPLY_THRESHOLD_PCT", "5"))

    def evaluate(self, dry_run: bool = True, product_filter: Optional[set] = None) -> dict:
        from src.pricing.rule import PricingRuleStore

        store = PricingRuleStore()
        rules = store.active_sorted()
        rows = self._get_catalog_rows()

        details = []
        changed = 0
        applied = 0

        for row in rows:
            sku = str(row.get("sku") or "").strip()
            if not sku:
                continue
            if product_filter and sku not in product_filter:
                continue

            current_price = self._as_decimal(row.get("sell_price_krw"))
            if current_price <= 0:
                continue

            matched = False
            for rule in rules:
                candidate = self._candidate_price(rule, row, current_price)
                if candidate is None or candidate == current_price:
                    continue

                matched = True
                candidate = self._clamp(candidate, rule)
                guard = self.margin_guard.evaluate(row, candidate)
                delta_pct = Decimal("0") if current_price == 0 else ((candidate - current_price) / current_price * Decimal("100"))

                should_apply = (
                    not dry_run
                    and self.auto_apply
                    and abs(delta_pct) <= self.auto_apply_threshold_pct
                    and guard.get("allowed", False)
                )

                detail = {
                    "sku": sku,
                    "rule_id": rule.rule_id,
                    "rule_name": rule.name,
                    "old": int(current_price),
                    "new": int(candidate),
                    "delta_pct": float(delta_pct.quantize(Decimal("0.01"))),
                    "guard_allowed": guard.get("allowed", False),
                    "guard_reason": guard.get("reason", ""),
                    "auto_applied": should_apply,
                }
                details.append(detail)
                if candidate != current_price:
                    changed += 1
                if should_apply:
                    applied += 1
                    self._append_history(sku, int(current_price), int(candidate), [rule.name])
                break

            if not matched:
                continue

        return {
            "ok": True,
            "run_at": datetime.now(tz=timezone.utc).isoformat(),
            "dry_run": dry_run,
            "auto_apply": self.auto_apply,
            "auto_apply_threshold_pct": float(self.auto_apply_threshold_pct),
            "evaluated": len(rows),
            "changed": changed,
            "applied": applied,
            "details": details,
        }

    def _candidate_price(self, rule, row: dict, current_price: Decimal) -> Optional[Decimal]:
        action_kind = str(rule.action_kind or "").strip().lower()
        action_value = self._as_decimal(rule.action_value)

        if action_kind == "match_lowest":
            from src.pricing.competitor_monitor import CompetitorMonitor

            lowest = CompetitorMonitor().get_lowest_price(str(row.get("sku") or ""))
            if lowest is None or lowest <= 0:
                return None
            return (lowest * (Decimal("1") + action_value / Decimal("100"))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        if action_kind == "target_margin":
            return self.margin_guard.required_price_for_margin(row, action_value)

        if action_kind == "fx_compensation":
            from src.pricing.fx_impact import FXImpactAnalyzer

            currency = str(row.get("buy_currency") or "KRW").upper()
            if currency not in {"USD", "JPY", "CNY"}:
                return None
            changes = FXImpactAnalyzer().daily_changes()
            change_pct = Decimal(str(changes.get(currency, Decimal("0"))))
            if change_pct == 0:
                return None
            return (current_price * (Decimal("1") + change_pct / Decimal("100"))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        if action_kind == "inventory_pressure":
            stock = int(float(row.get("stock") or row.get("stock_qty") or 0))
            low_threshold = int(float(os.getenv("PRICING_LOW_STOCK_THRESHOLD", "5")))
            high_threshold = int(float(os.getenv("PRICING_HIGH_STOCK_THRESHOLD", "50")))
            pct = abs(action_value) if action_value != 0 else Decimal("5")
            if stock <= low_threshold:
                return (current_price * (Decimal("1") + pct / Decimal("100"))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            if stock >= high_threshold:
                return (current_price * (Decimal("1") - pct / Decimal("100"))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            return None

        # 하위 호환: 기존 엔진 multiply/add 지원
        if action_kind == "multiply":
            return (current_price * action_value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if action_kind == "add":
            return (current_price + action_value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        return None

    @staticmethod
    def _clamp(price: Decimal, rule) -> Decimal:
        floor_krw = rule.action_floor_krw
        ceiling_krw = rule.action_ceiling_krw
        if floor_krw is not None and price < Decimal(str(floor_krw)):
            price = Decimal(str(floor_krw))
        if ceiling_krw is not None and price > Decimal(str(ceiling_krw)):
            price = Decimal(str(ceiling_krw))
        return price

    @staticmethod
    def _as_decimal(v) -> Decimal:
        try:
            return Decimal(str(v))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _get_catalog_rows() -> list:
        try:
            from src.utils.sheets import get_worksheet

            ws = get_worksheet("catalog")
            if ws is None:
                return []
            rows = ws.get_all_records()
            return [r for r in rows if str(r.get("status", "active")).strip().lower() in {"", "active"}]
        except Exception:
            return []

    @staticmethod
    def _append_history(sku: str, old_price: int, new_price: int, rules: list[str]) -> None:
        try:
            from src.pricing.history_store import PriceHistoryStore

            PriceHistoryStore().append(sku=sku, old_price_krw=old_price, new_price_krw=new_price, rules_applied=rules, applied_by="phase140")
        except Exception as exc:
            logger.debug("가격 이력 저장 실패: %s", exc)
