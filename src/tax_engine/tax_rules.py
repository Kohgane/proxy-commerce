"""세금 규칙 ABC 및 구현체."""
from __future__ import annotations
from abc import ABC, abstractmethod

class TaxRule(ABC):
    @abstractmethod
    def calculate(self, amount: float, context: dict) -> dict: ...
    @abstractmethod
    def rule_name(self) -> str: ...

class VATRule(TaxRule):
    """부가가치세 (한국 10%)."""
    DEFAULT_RATE = 0.10

    def rule_name(self) -> str:
        return "VAT"

    def calculate(self, amount: float, context: dict) -> dict:
        rate = context.get("vat_rate", self.DEFAULT_RATE)
        tax = round(amount * rate, 2)
        return {"rule": "VAT", "amount": amount, "tax": tax, "rate": rate}

class CustomsDutyRule(TaxRule):
    """관세 계산."""
    RATES = {"US": 0.08, "JP": 0.05, "CN": 0.15}

    def rule_name(self) -> str:
        return "customs_duty"

    def calculate(self, amount: float, context: dict) -> dict:
        origin = context.get("origin_country", "US")
        rate = self.RATES.get(origin, 0.08)
        tax = round(amount * rate, 2)
        return {"rule": "customs_duty", "amount": amount, "tax": tax, "rate": rate, "origin": origin}

class ExciseTaxRule(TaxRule):
    """개별소비세."""
    DEFAULT_RATE = 0.05

    def rule_name(self) -> str:
        return "excise_tax"

    def calculate(self, amount: float, context: dict) -> dict:
        rate = context.get("excise_rate", self.DEFAULT_RATE)
        tax = round(amount * rate, 2)
        return {"rule": "excise_tax", "amount": amount, "tax": tax, "rate": rate}
