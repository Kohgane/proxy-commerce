"""src/api/order_management_api.py — 주문 분할/병합 API (Phase 84)."""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

order_management_bp = Blueprint("order_management", __name__, url_prefix="/api/v1/order-management")


@order_management_bp.post("/split")
def split():
    """주문을 분할한다."""
    from ..order_management import OrderSplitter
    data = request.get_json(silent=True) or {}
    splitter = OrderSplitter()
    order = data.get('order', data.get('order_id', ''))
    strategy = data.get('strategy', 'supplier')
    result = splitter.split(order, strategy=strategy)
    # Convert SubOrder dataclass instances to dicts
    sub_orders = []
    for so in result.get('sub_orders', []):
        if hasattr(so, '__dataclass_fields__'):
            sub_orders.append({
                'sub_order_id': so.sub_order_id,
                'parent_order_id': so.parent_order_id,
                'items': so.items,
                'status': so.status,
            })
        else:
            sub_orders.append(so)
    return jsonify({'parent_order_id': result['parent_order_id'], 'sub_orders': sub_orders})


@order_management_bp.post("/merge")
def merge():
    """주문을 병합한다."""
    from ..order_management import OrderMerger
    data = request.get_json(silent=True) or {}
    order_ids = data.get('order_ids', [])
    merger = OrderMerger()
    return jsonify(merger.merge(order_ids))


@order_management_bp.get("/sub-orders/<order_id>")
def get_sub_orders(order_id: str):
    """하위 주문 목록을 반환한다."""
    from ..order_management import SplitHistory
    history = SplitHistory()
    return jsonify(history.get_sub_orders(order_id))


@order_management_bp.post("/candidates")
def find_candidates():
    """병합 후보를 탐색한다."""
    from ..order_management import MergeCandidate
    data = request.get_json(silent=True) or {}
    orders = data.get('orders', [])
    mc = MergeCandidate()
    return jsonify(mc.find_candidates(orders))


@order_management_bp.get("/history/<order_id>")
def get_history(order_id: str):
    """분할/병합 이력을 반환한다."""
    from ..order_management import SplitHistory
    history = SplitHistory()
    return jsonify({
        'split_history': history.get_split_history(order_id),
        'merge_history': history.get_merge_history(order_id),
    })
