"""src/pricing/engine.py — 자동 가격 조정 엔진 (Phase 136).

PricingEngine: 활성 룰을 우선순위 순으로 평가하여 가격 조정.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PricingEngine:
    """가격 정책 룰 평가 엔진.

    1) 활성 룰을 우선순위 순으로 정렬
    2) SKU별로 매칭 룰 적용 (누적)
    3) floor/ceiling 가드 적용
    4) dry_run=False 시 마켓별 실제 가격 업데이트
    """

    def __init__(self):
        pass

    # ── 공개 API ────────────────────────────────────────────────────────────

    def evaluate(self, dry_run: Optional[bool] = None) -> dict:
        """모든 활성 룰을 평가하여 가격 조정.

        Args:
            dry_run: None이면 PRICING_DRY_RUN 환경변수 우선 (기본 True).

        Returns:
            {"evaluated": N, "changed": N, "skipped": N, "errors": [], "details": [...]}
        """
        effective_dry_run = dry_run if dry_run is not None else self._env_dry_run()

        results: dict = {
            "evaluated": 0,
            "changed": 0,
            "skipped": 0,
            "errors": [],
            "details": [],
            "dry_run": effective_dry_run,
            "run_at": datetime.now(tz=timezone.utc).isoformat(),
        }

        try:
            from src.pricing.rule import PricingRuleStore
            rule_store = PricingRuleStore()
            active_rules = rule_store.active_sorted()
        except Exception as exc:
            logger.warning("룰 로드 실패: %s", exc)
            results["errors"].append(f"룰 로드 실패: {exc}")
            return results

        if not active_rules:
            logger.info("활성 룰 없음 — 평가 스킵")
            return results

        catalog_rows = self._get_catalog_rows()
        fx_rates = self._get_fx_rates()

        for sku_row in catalog_rows:
            try:
                sku = str(sku_row.get("sku", "")).strip()
                if not sku:
                    continue

                current_price = self._parse_price(sku_row.get("sell_price_krw"))
                if current_price is None or current_price <= 0:
                    results["skipped"] += 1
                    continue

                new_price = current_price
                applied_rules: List[str] = []
                last_rule = None

                for rule in active_rules:
                    if not self._scope_matches(rule, sku_row):
                        continue
                    if not self._triggers_pass(rule, sku_row, fx_rates):
                        continue

                    new_price = self._apply_action(rule, sku_row, new_price, fx_rates)
                    applied_rules.append(rule.name)
                    last_rule = rule

                results["evaluated"] += 1

                if new_price != current_price:
                    # floor/ceiling 가드 적용 (마지막으로 매칭된 룰의 가드 사용)
                    if last_rule:
                        new_price = self._clamp(
                            new_price,
                            last_rule.action_floor_krw,
                            last_rule.action_ceiling_krw,
                        )

                    delta_pct = float(
                        (new_price - current_price) / current_price * 100
                    )
                    detail = {
                        "sku": sku,
                        "old": int(current_price),
                        "new": int(new_price),
                        "delta_pct": round(delta_pct, 2),
                        "rules": applied_rules,
                    }
                    results["details"].append(detail)
                    results["changed"] += 1

                    if not effective_dry_run:
                        self._apply_to_markets(sku, int(new_price), sku_row)
                        self._append_history(
                            sku,
                            int(current_price),
                            int(new_price),
                            applied_rules,
                        )
                        if last_rule:
                            self._notify_if_threshold(
                                sku,
                                current_price,
                                new_price,
                                last_rule.notify_threshold_pct,
                            )

            except Exception as exc:
                logger.warning("SKU 평가 오류 (%s): %s", sku_row.get("sku"), exc)
                results["errors"].append(f"SKU {sku_row.get('sku')}: {exc}")

        # 룰별 통계 업데이트
        if not effective_dry_run:
            self._update_rule_stats(active_rules, results)

        return results

    # ── 내부 헬퍼 ──────────────────────────────────────────────────────────

    def _env_dry_run(self) -> bool:
        return os.getenv("PRICING_DRY_RUN", "1") == "1"

    def _get_catalog_rows(self) -> List[dict]:
        """Sheets catalog 워크시트에서 active 상품 조회."""
        try:
            from src.utils.sheets import open_sheet
            ws = open_sheet("catalog")
            rows = ws.get_all_records()
            return [r for r in rows if str(r.get("status", "")).strip().lower() == "active"]
        except Exception as exc:
            logger.warning("카탈로그 로드 실패: %s", exc)
            return []

    def _get_fx_rates(self) -> dict:
        """현재 환율 조회."""
        try:
            from src.utils.exchange_rate import get_exchange_rates
            return get_exchange_rates()
        except Exception:
            pass
        try:
            from src.fx.updater import FXUpdater
            return FXUpdater().get_current_rates()
        except Exception as exc:
            logger.warning("환율 조회 실패: %s", exc)
            return {"USDKRW": Decimal("1350"), "JPYKRW": Decimal("9.2"), "EURKRW": Decimal("1500")}

    def _parse_price(self, val) -> Optional[Decimal]:
        if val is None or val == "":
            return None
        try:
            return Decimal(str(val))
        except Exception:
            return None

    def _scope_matches(self, rule, sku_row: dict) -> bool:
        """룰 적용 범위가 이 SKU에 해당하는지 확인."""
        from src.pricing.rule import PricingRule
        scope = rule.scope_type
        if scope == "all":
            return True
        elif scope == "domain":
            src_url = str(sku_row.get("src_url", ""))
            return rule.scope_value.lower() in src_url.lower()
        elif scope == "category":
            category = str(sku_row.get("category", ""))
            return rule.scope_value.lower() == category.lower()
        elif scope == "sku_list":
            sku_list = [s.strip() for s in rule.scope_value.split(",")]
            return sku_row.get("sku", "") in sku_list
        return True

    def _triggers_pass(self, rule, sku_row: dict, fx_rates: dict) -> bool:
        """룰의 모든 트리거 조건이 충족되는지 확인 (AND 결합)."""
        for trigger in rule.triggers:
            if not self._eval_trigger(trigger, sku_row, fx_rates):
                return False
        return True

    def _eval_trigger(self, trigger: dict, sku_row: dict, fx_rates: dict) -> bool:
        """단일 트리거 평가."""
        kind = trigger.get("kind", "")

        if kind == "min_margin_pct":
            margin_pct = self._parse_price(sku_row.get("margin_pct"))
            if margin_pct is None:
                return False
            return self._compare(margin_pct, trigger)

        elif kind == "fx_change_pct":
            currency = trigger.get("currency", "USD")
            rate_key = f"{currency}KRW"
            current_rate = fx_rates.get(rate_key) or fx_rates.get(currency)
            if not current_rate:
                return False
            # 7일 전 환율 비교 (없으면 트리거 스킵)
            base_rate = self._get_base_fx_rate(currency)
            if not base_rate or base_rate == 0:
                return False
            change_pct = abs((Decimal(str(current_rate)) - base_rate) / base_rate * 100)
            return self._compare(change_pct, trigger)

        elif kind == "stock_qty":
            stock = self._parse_price(sku_row.get("stock") or sku_row.get("stock_qty"))
            if stock is None:
                return False
            return self._compare(stock, trigger)

        elif kind == "weekday":
            from datetime import datetime
            weekday_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            today = weekday_names[datetime.now().weekday()]
            in_list = [w.lower() for w in trigger.get("in", [])]
            return today in in_list

        elif kind == "season":
            from datetime import datetime
            month = datetime.now().month
            season_map = {
                "spring": [3, 4, 5],
                "summer": [6, 7, 8],
                "fall": [9, 10, 11],
                "winter": [12, 1, 2],
            }
            target_season = trigger.get("value", "").lower()
            return month in season_map.get(target_season, [])

        elif kind == "date_range":
            from datetime import date
            today = date.today().isoformat()
            start = trigger.get("start", "")
            end = trigger.get("end", "")
            return (not start or today >= start) and (not end or today <= end)

        elif kind == "competitor_min_lt_self":
            # 경쟁사 최저가 < 자사가 데이터 (competitor_prices 시트)
            competitor_price = self._get_competitor_min_price(sku_row.get("sku", ""))
            if competitor_price is None:
                return False
            self_price = self._parse_price(sku_row.get("sell_price_krw"))
            if self_price is None:
                return False
            margin_pct = Decimal(str(trigger.get("margin_pct", "0")))
            threshold = self_price * (1 - margin_pct / 100)
            return competitor_price < threshold

        elif kind == "days_since_listing":
            listed_at = sku_row.get("listed_at") or sku_row.get("created_at")
            if not listed_at:
                return False
            from datetime import datetime
            try:
                listed_dt = datetime.fromisoformat(str(listed_at)[:10])
                days = (datetime.now() - listed_dt).days
                return self._compare(Decimal(str(days)), trigger)
            except Exception:
                return False

        logger.debug("알 수 없는 트리거 종류: %s", kind)
        return False

    def _compare(self, val: Decimal, trigger: dict) -> bool:
        """op 연산자로 비교."""
        op = trigger.get("op", "<")
        threshold = Decimal(str(trigger.get("value", "0")))
        if op == "<":
            return val < threshold
        elif op == "<=":
            return val <= threshold
        elif op == ">":
            return val > threshold
        elif op == ">=":
            return val >= threshold
        elif op == "==":
            return val == threshold
        elif op == "!=":
            return val != threshold
        return False

    def _apply_action(self, rule, sku_row: dict, current_price: Decimal, fx_rates: dict) -> Decimal:
        """액션 적용하여 새 가격 반환."""
        action = rule.action_kind
        val = rule.action_value

        if action == "set_margin":
            # 마진율 N%로 재산정
            cost_krw = self._calc_cost_krw(sku_row, fx_rates)
            if cost_krw and cost_krw > 0:
                margin_rate = val / 100
                if margin_rate >= 1:
                    return current_price
                new_price = cost_krw / (1 - margin_rate)
                return new_price.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        elif action == "multiply":
            return (current_price * val).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        elif action == "add":
            return (current_price + val).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        elif action == "match_competitor":
            competitor_price = self._get_competitor_min_price(sku_row.get("sku", ""))
            if competitor_price:
                new_price = competitor_price + val
                return max(new_price, Decimal("1")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        elif action == "notify_only":
            return current_price  # 가격 변경 없음

        return current_price

    def _clamp(self, price: Decimal, floor_krw: Optional[int], ceiling_krw: Optional[int]) -> Decimal:
        """floor/ceiling 가드 클램핑."""
        if floor_krw and price < Decimal(str(floor_krw)):
            price = Decimal(str(floor_krw))
        if ceiling_krw and price > Decimal(str(ceiling_krw)):
            price = Decimal(str(ceiling_krw))
        return price

    def _calc_cost_krw(self, sku_row: dict, fx_rates: dict) -> Optional[Decimal]:
        """SKU의 원가 KRW 환산."""
        try:
            buy_price = Decimal(str(sku_row.get("buy_price", 0)))
            currency = str(sku_row.get("buy_currency", "KRW")).upper()
            if currency == "KRW":
                return buy_price
            rate_key = f"{currency}KRW"
            rate = fx_rates.get(rate_key)
            if rate:
                return (buy_price * Decimal(str(rate))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        except Exception:
            pass
        return None

    def _get_base_fx_rate(self, currency: str) -> Optional[Decimal]:
        """7일 전 기준 환율 (FX 히스토리에서 조회)."""
        try:
            from src.fx.history import FXHistory
            history = FXHistory()
            rate = history.get_rate_n_days_ago(currency, days=7)
            if rate:
                return Decimal(str(rate))
        except Exception:
            pass
        return None

    def _get_competitor_min_price(self, sku: str) -> Optional[Decimal]:
        """경쟁사 최저가 조회 (competitor_prices 시트)."""
        try:
            from src.utils.sheets import open_sheet
            ws = open_sheet("competitor_prices")
            rows = ws.get_all_records()
            prices = []
            for row in rows:
                if str(row.get("sku", "")) == sku:
                    p = row.get("competitor_price_krw")
                    if p:
                        prices.append(Decimal(str(p)))
            if prices:
                return min(prices)
        except Exception:
            pass
        return None

    def _apply_to_markets(self, sku: str, new_price_krw: int, sku_row: dict):
        """4개 마켓 어댑터에 가격 업데이트."""
        adapters = self._get_market_adapters()
        for name, adapter in adapters.items():
            try:
                result = adapter.update_price(sku, new_price_krw)
                if result.get("updated"):
                    logger.info("마켓 가격 업데이트 성공: %s %s → %d원", name, sku, new_price_krw)
                else:
                    logger.debug("마켓 가격 업데이트 스킵: %s %s — %s", name, sku, result.get("reason"))
            except Exception as exc:
                logger.warning("마켓 가격 업데이트 오류 (%s, %s): %s", name, sku, exc)

    def _get_market_adapters(self) -> dict:
        """4개 마켓 어댑터 인스턴스 반환."""
        adapters = {}
        try:
            from src.seller_console.market_adapters.coupang_adapter import CoupangAdapter
            adapters["coupang"] = CoupangAdapter()
        except Exception:
            pass
        try:
            from src.seller_console.market_adapters.smartstore_adapter import SmartstoreAdapter
            adapters["smartstore"] = SmartstoreAdapter()
        except Exception:
            pass
        try:
            from src.seller_console.market_adapters.eleven_adapter import ElevenAdapter
            adapters["11st"] = ElevenAdapter()
        except Exception:
            pass
        try:
            from src.seller_console.market_adapters.woocommerce_adapter import WooCommerceAdapter
            adapters["woocommerce"] = WooCommerceAdapter()
        except Exception:
            pass
        return adapters

    def _append_history(self, sku: str, old_price: int, new_price: int, rules: List[str]):
        """가격 변경 이력 기록."""
        try:
            from src.pricing.history_store import PriceHistoryStore
            PriceHistoryStore().append(sku, old_price, new_price, rules)
        except Exception as exc:
            logger.warning("가격 이력 기록 실패: %s", exc)

    def _notify_if_threshold(
        self,
        sku: str,
        old_price: Decimal,
        new_price: Decimal,
        threshold_pct: Decimal,
    ):
        """변동폭이 임계값 이상이면 텔레그램 알림."""
        if old_price == 0:
            return
        change_pct = abs((new_price - old_price) / old_price * 100)
        if change_pct >= threshold_pct:
            try:
                from src.notifications.telegram import send_telegram
                direction = "인상" if new_price > old_price else "인하"
                msg = (
                    f"⚠️ 가격 {direction} 알림\n"
                    f"SKU: {sku}\n"
                    f"변동: {int(old_price):,}원 → {int(new_price):,}원 "
                    f"({'+' if new_price > old_price else ''}{float(change_pct):.1f}%)"
                )
                send_telegram(msg, urgency="warning")
            except Exception as exc:
                logger.warning("임계값 알림 전송 실패: %s", exc)

    def _update_rule_stats(self, rules, results: dict):
        """룰 실행 통계 업데이트."""
        try:
            from src.pricing.rule import PricingRuleStore
            store = PricingRuleStore()
            run_at = results.get("run_at", "")
            for rule in rules:
                # 해당 룰로 변경된 SKU 수 집계
                changed = sum(
                    1 for d in results.get("details", [])
                    if rule.name in d.get("rules", [])
                )
                if changed:
                    store.update_stats(rule.rule_id, run_at, changed)
        except Exception as exc:
            logger.warning("룰 통계 업데이트 실패: %s", exc)
