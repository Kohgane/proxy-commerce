"""src/api/shipping_api.py — 배송 추적 REST API."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

shipping_api = Blueprint("shipping_api", __name__, url_prefix="/api/v1/shipping")


def _get_tracker():
    from ..shipping.tracker import ShipmentTracker
    return ShipmentTracker()


def _record_to_dict(record) -> dict:
    return {
        "tracking_number": record.tracking_number,
        "carrier": record.carrier,
        "status": record.status.value,
        "updated_at": record.updated_at.isoformat(),
        "order_id": record.order_id,
        "events": [
            {
                "timestamp": e.timestamp.isoformat(),
                "status": e.status.value,
                "location": e.location,
                "description": e.description,
            }
            for e in record.events
        ],
    }


@shipping_api.get("/status_check")
def status_check():
    """모듈 상태 확인."""
    return jsonify({"status": "ok", "module": "shipping_tracking"})


@shipping_api.post("/register")
def register_shipment():
    """운송장 번호 등록."""
    body = request.get_json(silent=True) or {}
    tracking_number = body.get("tracking_number", "").strip()
    carrier = body.get("carrier", "").strip()
    order_id = body.get("order_id")

    if not tracking_number or not carrier:
        return jsonify({"error": "tracking_number and carrier are required"}), 400

    try:
        tracker = _get_tracker()
        record = tracker.register(tracking_number, carrier, order_id=order_id)
        return jsonify(_record_to_dict(record)), 201
    except ValueError:
        return jsonify({"error": f"Unsupported carrier: {carrier}"}), 400
    except Exception as exc:
        logger.error("register_shipment 오류: %s", exc)
        return jsonify({"error": "Internal server error"}), 500


@shipping_api.get("/status/<tracking_number>")
def get_status(tracking_number: str):
    """운송장 번호로 배송 현황 조회."""
    try:
        tracker = _get_tracker()
        # Register on-the-fly if carrier query param provided; otherwise look up.
        carrier = request.args.get("carrier", "").strip()
        if carrier:
            record = tracker.register(tracking_number, carrier)
        else:
            record = tracker.get_status(tracking_number)

        if record is None:
            return jsonify({"error": "Tracking number not found"}), 404
        return jsonify(_record_to_dict(record))
    except ValueError:
        return jsonify({"error": f"Unsupported carrier: {carrier}"}), 400
    except Exception as exc:
        logger.error("get_status 오류: %s", exc)
        return jsonify({"error": "Internal server error"}), 500


@shipping_api.get("/list")
def list_shipments():
    """등록된 모든 배송 목록 조회."""
    try:
        tracker = _get_tracker()
        records = tracker.get_all()
        return jsonify([_record_to_dict(r) for r in records])
    except Exception as exc:
        logger.error("list_shipments 오류: %s", exc)
        return jsonify({"error": "Internal server error"}), 500
