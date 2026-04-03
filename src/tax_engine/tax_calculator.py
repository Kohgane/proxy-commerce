"""세금 계산 통합 엔진."""
from __future__ import annotations
from .tax_rules import TaxRule, VATRule

class TaxCalculator:
    def __init__(self) -> None:
        self._rules: list[TaxRule] = [VATRule()]

    def add_rule(self, rule: TaxRule) -> None:
        self._rules.append(rule)

    def calculate(self, amount: float, context: dict | None = None) -> dict:
        context = context or {}
        results = []
        total_tax = 0.0
        for rule in self._rules:
            r = rule.calculate(amount, context)
            results.append(r)
            total_tax += r["tax"]
        return {
            "amount": amount,
            "total_tax": round(total_tax, 2),
            "tax_inclusive_amount": round(amount + total_tax, 2),
            "breakdown": results,
        }
