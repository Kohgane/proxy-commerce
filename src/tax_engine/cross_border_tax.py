"""해외 직구 세금 (관세+부가세+개별소비세 통합)."""
from __future__ import annotations
from .tax_rules import VATRule, CustomsDutyRule, ExciseTaxRule
from .tax_exemption import TaxExemption

class CrossBorderTax:
    def __init__(self) -> None:
        self._vat = VATRule()
        self._customs = CustomsDutyRule()
        self._excise = ExciseTaxRule()
        self._exemption = TaxExemption()

    def calculate(self, amount: float, origin_country: str = "US", category: str = "", apply_excise: bool = False) -> dict:
        if self._exemption.is_exempt(amount, category):
            return {"amount": amount, "total_tax": 0, "exempt": True, "breakdown": []}
        ctx = {"origin_country": origin_country}
        customs = self._customs.calculate(amount, ctx)
        vat = self._vat.calculate(amount + customs["tax"], {})
        breakdown = [customs, vat]
        total = customs["tax"] + vat["tax"]
        if apply_excise:
            excise = self._excise.calculate(amount, {})
            breakdown.append(excise)
            total += excise["tax"]
        return {"amount": amount, "total_tax": round(total, 2), "exempt": False, "breakdown": breakdown}
