"""src/api/returns_automation_api.py — Phase 118: 반품/교환 자동 처리 API.

Blueprint: /api/v1/returns-automation

엔드포인트:
  POST /requests                          — 신규 반품/교환 요청
  GET  /requests/<request_id>             — 상세 조회
  GET  /requests                          — 목록 조회 (?status=...&user_id=...)
  POST /requests/<request_id>/classify    — 강제 재분류 (관리자)
  POST /requests/<request_id>/approve     — 수동 승인
  POST /requests/<request_id>/reject      — 수동 거절
  POST /requests/<request_id>/escalate    — 분쟁 에스컬레이션
  POST /requests/<request_id>/pickup      — 회수 픽업 예약
  POST /requests/<request_id>/inspect     — 검수 등록
  POST /requests/<request_id>/refund      — 환불 처리
  POST /requests/<request_id>/exchange    — 교환 처리
  GET  /metrics                           — 자동화 메트릭
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

returns_automation_bp = Blueprint(
    'returns_automation',
    __name__,
    url_prefix='/api/v1/returns-automation',
)

# 싱글톤 매니저 (지연 초기화)
_manager = None


def _get_manager():
    """ReturnsAutomationManager 싱글톤 반환."""
    global _manager
    if _manager is None:
        from ..returns_automation.automation_manager import ReturnsAutomationManager
        _manager = ReturnsAutomationManager()
    return _manager


# ─── 요청 제출 ───────────────────────────────────────────────────────────────

@returns_automation_bp.post('/requests')
def submit_request():
    """POST /api/v1/returns-automation/requests — 신규 반품/교환 요청 접수."""
    data = request.get_json(force=True, silent=True) or {}

    order_id = data.get('order_id', '').strip()
    user_id = data.get('user_id', '').strip()
    items = data.get('items', [])
    reason_code = data.get('reason_code', 'other').strip()

    if not order_id or not user_id:
        return jsonify({'error': 'order_id와 user_id는 필수입니다.'}), 400
    if not items:
        return jsonify({'error': 'items는 1개 이상이어야 합니다.'}), 400

    try:
        mgr = _get_manager()
        req = mgr.submit_request(
            order_id=order_id,
            user_id=user_id,
            items=items,
            reason_code=reason_code,
            reason_text=data.get('reason_text', ''),
            photos=data.get('photos', []),
            order=data.get('order'),
            customer=data.get('customer'),
            request_type=data.get('request_type', 'return'),
            target_sku=data.get('target_sku', ''),
            target_option=data.get('target_option', ''),
        )
        return jsonify(req.to_dict()), 201
    except Exception as exc:
        logger.error("반품 요청 접수 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 상세 조회 ───────────────────────────────────────────────────────────────

@returns_automation_bp.get('/requests/<request_id>')
def get_request(request_id: str):
    """GET /api/v1/returns-automation/requests/<id> — 요청 상세 조회."""
    try:
        mgr = _get_manager()
        data = mgr.get_status(request_id)
        if data is None:
            return jsonify({'error': '요청을 찾을 수 없습니다.'}), 404
        return jsonify(data), 200
    except Exception as exc:
        logger.error("요청 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 목록 조회 ───────────────────────────────────────────────────────────────

@returns_automation_bp.get('/requests')
def list_requests():
    """GET /api/v1/returns-automation/requests — 목록 조회 (status/user_id 필터)."""
    status = request.args.get('status')
    user_id = request.args.get('user_id')
    try:
        mgr = _get_manager()
        items = mgr.list_pending(status=status, user_id=user_id)
        return jsonify({'requests': items, 'total': len(items)}), 200
    except Exception as exc:
        logger.error("요청 목록 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 강제 재분류 ─────────────────────────────────────────────────────────────

@returns_automation_bp.post('/requests/<request_id>/classify')
def reclassify(request_id: str):
    """POST /api/v1/returns-automation/requests/<id>/classify — 강제 재분류 (관리자)."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        mgr = _get_manager()
        req_obj = mgr.get_request_object(request_id)
        if req_obj is None:
            return jsonify({'error': '요청을 찾을 수 없습니다.'}), 404

        order = data.get('order', {})
        customer = data.get('customer', {})
        classification = mgr._classifier.classify(req_obj, order, customer)
        req_obj.classification = classification

        from ..returns_automation.models import ReturnStatus
        req_obj.status = ReturnStatus.classified

        return jsonify({'request_id': request_id, 'classification': classification.value}), 200
    except Exception as exc:
        logger.error("재분류 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 수동 승인 ───────────────────────────────────────────────────────────────

@returns_automation_bp.post('/requests/<request_id>/approve')
def approve_request(request_id: str):
    """POST /api/v1/returns-automation/requests/<id>/approve — 수동 승인."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        mgr = _get_manager()
        req_obj = mgr.approve(
            request_id,
            notes=data.get('notes', '수동 승인'),
            order=data.get('order', {}),
            customer=data.get('customer', {}),
        )
        return jsonify(req_obj.to_dict()), 200
    except KeyError:
        return jsonify({'error': '요청을 찾을 수 없습니다.'}), 404
    except Exception as exc:
        logger.error("수동 승인 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 수동 거절 ───────────────────────────────────────────────────────────────

@returns_automation_bp.post('/requests/<request_id>/reject')
def reject_request(request_id: str):
    """POST /api/v1/returns-automation/requests/<id>/reject — 수동 거절."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        mgr = _get_manager()
        req_obj = mgr.reject(request_id, notes=data.get('notes', '수동 거절'))
        return jsonify(req_obj.to_dict()), 200
    except KeyError:
        return jsonify({'error': '요청을 찾을 수 없습니다.'}), 404
    except Exception as exc:
        logger.error("수동 거절 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 분쟁 에스컬레이션 ────────────────────────────────────────────────────────

@returns_automation_bp.post('/requests/<request_id>/escalate')
def escalate_request(request_id: str):
    """POST /api/v1/returns-automation/requests/<id>/escalate — 분쟁 에스컬레이션."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        mgr = _get_manager()
        req_obj = mgr.escalate(request_id, reason=data.get('reason', ''))
        return jsonify(req_obj.to_dict()), 200
    except KeyError:
        return jsonify({'error': '요청을 찾을 수 없습니다.'}), 404
    except Exception as exc:
        logger.error("에스컬레이션 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 회수 픽업 예약 ──────────────────────────────────────────────────────────

@returns_automation_bp.post('/requests/<request_id>/pickup')
def schedule_pickup(request_id: str):
    """POST /api/v1/returns-automation/requests/<id>/pickup — 회수 픽업 예약."""
    data = request.get_json(force=True, silent=True) or {}
    address = data.get('address', {})
    carrier = data.get('carrier', 'cj')
    if not address:
        return jsonify({'error': '주소(address)는 필수입니다.'}), 400
    try:
        mgr = _get_manager()
        result = mgr.schedule_pickup(request_id, address, carrier)
        return jsonify(result), 200
    except KeyError:
        return jsonify({'error': '요청을 찾을 수 없습니다.'}), 404
    except ValueError as exc:
        logger.warning("픽업 예약 입력 오류: %s", exc)
        return jsonify({'error': '잘못된 요청 데이터입니다.'}), 400
    except Exception as exc:
        logger.error("픽업 예약 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 검수 등록 ───────────────────────────────────────────────────────────────

@returns_automation_bp.post('/requests/<request_id>/inspect')
def inspect_request(request_id: str):
    """POST /api/v1/returns-automation/requests/<id>/inspect — 검수 등록."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        mgr = _get_manager()
        result = mgr.process_inspection(
            request_id,
            condition_score=int(data.get('condition_score', 90)),
            package_intact=bool(data.get('package_intact', True)),
            functional=bool(data.get('functional', True)),
            notes=data.get('notes', ''),
        )
        return jsonify(result), 200
    except KeyError:
        return jsonify({'error': '요청을 찾을 수 없습니다.'}), 404
    except Exception as exc:
        logger.error("검수 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 환불 처리 ───────────────────────────────────────────────────────────────

@returns_automation_bp.post('/requests/<request_id>/refund')
def process_refund(request_id: str):
    """POST /api/v1/returns-automation/requests/<id>/refund — 환불 처리."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        mgr = _get_manager()
        result = mgr.process_refund_for_request(
            request_id,
            order=data.get('order', {}),
        )
        return jsonify(result), 200
    except KeyError:
        return jsonify({'error': '요청을 찾을 수 없습니다.'}), 404
    except Exception as exc:
        logger.error("환불 처리 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 교환 처리 ───────────────────────────────────────────────────────────────

@returns_automation_bp.post('/requests/<request_id>/exchange')
def process_exchange(request_id: str):
    """POST /api/v1/returns-automation/requests/<id>/exchange — 교환 처리."""
    data = request.get_json(force=True, silent=True) or {}
    try:
        mgr = _get_manager()
        result = mgr.process_exchange_for_request(
            request_id,
            order=data.get('order', {}),
        )
        return jsonify(result), 200
    except KeyError:
        return jsonify({'error': '요청을 찾을 수 없습니다.'}), 404
    except Exception as exc:
        logger.error("교환 처리 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


# ─── 메트릭 ─────────────────────────────────────────────────────────────────

@returns_automation_bp.get('/metrics')
def get_metrics():
    """GET /api/v1/returns-automation/metrics — 자동화 메트릭."""
    try:
        mgr = _get_manager()
        return jsonify(mgr.metrics()), 200
    except Exception as exc:
        logger.error("메트릭 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
