"""src/api/product_comparison_api.py — 상품 비교 API (Phase 87)."""
from __future__ import annotations
import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)
product_comparison_bp = Blueprint("product_comparison", __name__, url_prefix="/api/v1/product-comparison")

def _get_engine():
    from ..product_comparison import ComparisonEngine
    return ComparisonEngine()

def _get_matrix():
    from ..product_comparison import FeatureMatrix
    return FeatureMatrix()

def _get_score():
    from ..product_comparison import ComparisonScore
    return ComparisonScore()

def _get_history():
    from ..product_comparison import ComparisonHistory
    return ComparisonHistory()

@product_comparison_bp.post("/compare")
def compare():
    data = request.get_json(silent=True) or {}
    products = data.get("products", [])
    user_id = data.get("user_id", "")
    engine = _get_engine()
    return jsonify(engine.compare(products, user_id))

@product_comparison_bp.post("/matrix")
def matrix():
    data = request.get_json(silent=True) or {}
    products = data.get("products", [])
    features = data.get("features")
    fm = _get_matrix()
    return jsonify(fm.build(products, features))

@product_comparison_bp.post("/score")
def score():
    data = request.get_json(silent=True) or {}
    products = data.get("products", [])
    weights = data.get("weights")
    sc = _get_score()
    return jsonify(sc.calculate(products, weights))

@product_comparison_bp.get("/history")
def history():
    user_id = request.args.get("user_id")
    hist = _get_history()
    return jsonify([{"comparison_id": h.comparison_id, "product_ids": h.product_ids} for h in hist.list(user_id)])
