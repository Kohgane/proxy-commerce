"""src/api/tax_engine_api.py — 세금 계산 엔진 API (Phase 90)."""
from __future__ import annotations
import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)
tax_engine_bp = Blueprint("tax_engine", __name__, url_prefix="/api/v1/tax")

def _get_calculator():
    from ..tax_engine import TaxCalculator
    return TaxCalculator()

def _get_cross_border():
    from ..tax_engine import CrossBorderTax
    return CrossBorderTax()

def _get_report():
    from ..tax_engine import TaxReport
    return TaxReport()

def _get_invoice():
    from ..tax_engine import TaxInvoice
    return TaxInvoice()

def _get_exemption():
    from ..tax_engine import TaxExemption
    return TaxExemption()

@tax_engine_bp.post("/calculate")
def calculate():
    data = request.get_json(silent=True) or {}
    calc = _get_calculator()
    result = calc.calculate(float(data.get("amount", 0)), context=data.get("context", {}))
    return jsonify(result)

@tax_engine_bp.get("/rates")
def rates():
    from ..tax_engine import VATRule, CustomsDutyRule
    vat = VATRule()
    customs = CustomsDutyRule()
    return jsonify({
        "VAT": {"Korea": VATRule.DEFAULT_RATE},
        "customs_duty": customs.RATES,
    })

@tax_engine_bp.post("/cross-border")
def cross_border():
    data = request.get_json(silent=True) or {}
    cb = _get_cross_border()
    result = cb.calculate(
        amount=float(data.get("amount", 0)),
        origin_country=data.get("origin_country", "US"),
        category=data.get("category", ""),
        apply_excise=bool(data.get("apply_excise", False)),
    )
    return jsonify(result)

@tax_engine_bp.post("/report")
def report():
    data = request.get_json(silent=True) or {}
    rep = _get_report()
    return jsonify(rep.period_summary(data.get("start", ""), data.get("end", "9999")))

@tax_engine_bp.post("/invoice")
def invoice():
    data = request.get_json(silent=True) or {}
    inv = _get_invoice()
    result = inv.create(
        supplier=data.get("supplier", {}),
        buyer=data.get("buyer", {}),
        items=data.get("items", []),
    )
    return jsonify(result)

@tax_engine_bp.post("/exemptions/check")
def check_exemption():
    data = request.get_json(silent=True) or {}
    exemption = _get_exemption()
    is_exempt = exemption.is_exempt(float(data.get("amount", 0)), data.get("category", ""))
    return jsonify({"exempt": is_exempt})
