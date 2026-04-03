"""src/api/warehouse_api.py — 창고 관리 API (Phase 89)."""
from __future__ import annotations
import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)
warehouse_bp = Blueprint("warehouse", __name__, url_prefix="/api/v1/warehouses")

def _get_manager():
    from ..warehouse import WarehouseManager
    return WarehouseManager()

def _get_picking():
    from ..warehouse import PickingOrder
    return PickingOrder()

def _get_transfer():
    from ..warehouse import WarehouseTransfer
    return WarehouseTransfer()

def _get_report():
    from ..warehouse import WarehouseReport
    return WarehouseReport()

@warehouse_bp.get("/")
def list_warehouses():
    mgr = _get_manager()
    whs = mgr.list()
    return jsonify([{"warehouse_id": w.warehouse_id, "name": w.name, "capacity": w.capacity, "is_active": w.is_active} for w in whs])

@warehouse_bp.post("/")
def create_warehouse():
    data = request.get_json(silent=True) or {}
    mgr = _get_manager()
    wh = mgr.create(name=data.get("name", ""), address=data.get("address", ""), capacity=int(data.get("capacity", 0)))
    return jsonify({"warehouse_id": wh.warehouse_id, "name": wh.name}), 201

@warehouse_bp.get("/<warehouse_id>")
def get_warehouse(warehouse_id: str):
    mgr = _get_manager()
    wh = mgr.get(warehouse_id)
    if not wh:
        return jsonify({"error": "not found"}), 404
    report = _get_report()
    return jsonify(report.status(wh))

@warehouse_bp.post("/<warehouse_id>/zones")
def add_zone(warehouse_id: str):
    data = request.get_json(silent=True) or {}
    mgr = _get_manager()
    zone = mgr.add_zone(warehouse_id, name=data.get("name", ""), zone_type=data.get("zone_type", "general"))
    if not zone:
        return jsonify({"error": "not found"}), 404
    return jsonify({"zone_id": zone.zone_id, "name": zone.name}), 201

@warehouse_bp.post("/picking")
def create_picking():
    data = request.get_json(silent=True) or {}
    picking = _get_picking()
    order = picking.create(order_id=data.get("order_id", ""), items=data.get("items", []))
    return jsonify(order), 201

@warehouse_bp.post("/transfer")
def create_transfer():
    data = request.get_json(silent=True) or {}
    transfer = _get_transfer()
    result = transfer.create(
        from_warehouse_id=data.get("from_warehouse_id", ""),
        to_warehouse_id=data.get("to_warehouse_id", ""),
        items=data.get("items", []),
    )
    return jsonify(result), 201

@warehouse_bp.get("/report")
def report():
    mgr = _get_manager()
    rep = _get_report()
    return jsonify(rep.all_status(mgr.list()))
