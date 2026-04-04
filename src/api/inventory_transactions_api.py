"""src/api/inventory_transactions_api.py — 재고 입출고 이력 API (Phase 85)."""
from __future__ import annotations
import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)
inventory_transactions_bp = Blueprint("inventory_transactions", __name__, url_prefix="/api/v1/inventory-transactions")

def _get_manager():
    from ..inventory_transactions import TransactionManager
    return TransactionManager()

def _get_ledger(manager=None):
    from ..inventory_transactions import StockLedger, TransactionManager
    return StockLedger(manager or TransactionManager())

def _get_report(manager=None):
    from ..inventory_transactions import TransactionReport, TransactionManager
    return TransactionReport(manager or TransactionManager())

def _get_adjuster(manager=None):
    from ..inventory_transactions import StockAdjustment, TransactionManager
    return StockAdjustment(manager or TransactionManager())

@inventory_transactions_bp.post("/")
def create():
    data = request.get_json(silent=True) or {}
    mgr = _get_manager()
    tx = mgr.create(
        sku=data.get("sku", ""),
        tx_type=data.get("type", "inbound"),
        quantity=int(data.get("quantity", 0)),
        reason=data.get("reason", ""),
        user_id=data.get("user_id", ""),
        reference_id=data.get("reference_id", ""),
    )
    return jsonify({"transaction_id": tx.transaction_id, "sku": tx.sku, "type": tx.type, "quantity": tx.quantity}), 201

@inventory_transactions_bp.get("/")
def list_transactions():
    sku = request.args.get("sku")
    mgr = _get_manager()
    txs = mgr.list(sku)
    return jsonify([{"transaction_id": t.transaction_id, "sku": t.sku, "type": t.type, "quantity": t.quantity, "timestamp": t.timestamp} for t in txs])

@inventory_transactions_bp.get("/ledger")
def ledger():
    sku = request.args.get("sku", "")
    mgr = _get_manager()
    ledger_obj = _get_ledger(mgr)
    return jsonify(ledger_obj.snapshot(sku))

@inventory_transactions_bp.get("/report")
def report():
    start = request.args.get("start", "")
    end = request.args.get("end", "9999")
    mgr = _get_manager()
    rep = _get_report(mgr)
    return jsonify(rep.period_summary(start, end))

@inventory_transactions_bp.post("/adjust")
def adjust():
    data = request.get_json(silent=True) or {}
    mgr = _get_manager()
    adj = _get_adjuster(mgr)
    result = adj.adjust(
        sku=data.get("sku", ""),
        actual_qty=int(data.get("actual_qty", 0)),
        reason=data.get("reason", "stocktake"),
        user_id=data.get("user_id", ""),
    )
    return jsonify(result)
