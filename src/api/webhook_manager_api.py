"""src/api/webhook_manager_api.py — Phase 51: 웹훅 관리 API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

webhook_manager_bp = Blueprint('webhook_manager', __name__, url_prefix='/api/v1/webhooks')


@webhook_manager_bp.get('/status')
def webhook_status():
    return jsonify({'status': 'ok', 'module': 'webhook_manager'})


@webhook_manager_bp.post('')
def register_webhook():
    from ..webhook_manager.webhook_registry import WebhookRegistry
    body = request.get_json(silent=True) or {}
    url = body.get('url', '')
    events = body.get('events', [])
    if not url or not events:
        return jsonify({'error': 'url and events required'}), 400
    try:
        registry = WebhookRegistry()
        wh = registry.register(url, events, secret=body.get('secret', ''))
        return jsonify(wh), 201
    except Exception as exc:
        logger.error("웹훅 등록 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@webhook_manager_bp.get('')
def list_webhooks():
    from ..webhook_manager.webhook_registry import WebhookRegistry
    try:
        registry = WebhookRegistry()
        return jsonify(registry.list_webhooks())
    except Exception as exc:
        logger.error("웹훅 목록 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@webhook_manager_bp.get('/<webhook_id>')
def get_webhook(webhook_id: str):
    from ..webhook_manager.webhook_registry import WebhookRegistry
    try:
        registry = WebhookRegistry()
        wh = registry.get_webhook(webhook_id)
        if wh is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(wh)
    except Exception as exc:
        logger.error("웹훅 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@webhook_manager_bp.put('/<webhook_id>')
def update_webhook(webhook_id: str):
    from ..webhook_manager.webhook_registry import WebhookRegistry
    body = request.get_json(silent=True) or {}
    try:
        registry = WebhookRegistry()
        wh = registry.update_webhook(webhook_id, **body)
        return jsonify(wh)
    except KeyError:
        return jsonify({'error': 'not found'}), 404
    except Exception as exc:
        logger.error("웹훅 수정 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@webhook_manager_bp.delete('/<webhook_id>')
def delete_webhook(webhook_id: str):
    from ..webhook_manager.webhook_registry import WebhookRegistry
    try:
        registry = WebhookRegistry()
        deleted = registry.delete_webhook(webhook_id)
        if not deleted:
            return jsonify({'error': 'not found'}), 404
        return jsonify({'deleted': True})
    except Exception as exc:
        logger.error("웹훅 삭제 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@webhook_manager_bp.post('/<webhook_id>/test')
def test_webhook(webhook_id: str):
    from ..webhook_manager.webhook_registry import WebhookRegistry
    try:
        registry = WebhookRegistry()
        wh = registry.get_webhook(webhook_id)
        if wh is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify({'webhook_id': webhook_id, 'status': 'queued'})
    except Exception as exc:
        logger.error("웹훅 테스트 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@webhook_manager_bp.get('/<webhook_id>/deliveries')
def get_deliveries(webhook_id: str):
    from ..webhook_manager.delivery_log import DeliveryLog
    try:
        log = DeliveryLog()
        return jsonify(log.get_deliveries(webhook_id))
    except Exception as exc:
        logger.error("전달 로그 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
