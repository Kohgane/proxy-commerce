"""src/api/notifications_api.py — Phase 35: 알림 관리 REST API Blueprint."""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

notifications_bp = Blueprint('notifications', __name__, url_prefix='/api/notifications')


@notifications_bp.get('/status')
def notifications_status():
    """GET /api/notifications/status — 알림 모듈 상태."""
    return jsonify({'status': 'ok', 'module': 'notifications'})


@notifications_bp.post('/dispatch')
def dispatch_notification():
    """POST /api/notifications/dispatch — 알림 발송."""
    from ..notifications.notification_hub import NotificationHub
    body = request.get_json(silent=True) or {}
    event_type = body.get('event_type', '')
    recipient = body.get('recipient', '')
    message = body.get('message', '')
    template_data = body.get('template_data')
    if not event_type or not message:
        return jsonify({'error': 'event_type and message are required'}), 400
    try:
        hub = NotificationHub()
        results = hub.dispatch(event_type, recipient, message, template_data)
        return jsonify({'dispatched': True, 'results': results})
    except Exception as exc:
        logger.error("알림 발송 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@notifications_bp.get('/preferences/<user_id>')
def get_preferences(user_id: str):
    """GET /api/notifications/preferences/<user_id> — 알림 설정 조회."""
    from ..notifications.preferences import NotificationPreference
    try:
        prefs = NotificationPreference()
        return jsonify(prefs.get_all(user_id))
    except Exception as exc:
        logger.error("알림 설정 조회 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500


@notifications_bp.post('/preferences/<user_id>')
def set_preference(user_id: str):
    """POST /api/notifications/preferences/<user_id> — 알림 설정 저장."""
    from ..notifications.preferences import NotificationPreference
    body = request.get_json(silent=True) or {}
    event_type = body.get('event_type', '')
    channel = body.get('channel', '')
    enabled = body.get('enabled', True)
    if not event_type or not channel:
        return jsonify({'error': 'event_type and channel are required'}), 400
    try:
        prefs = NotificationPreference()
        prefs.set(user_id, event_type, channel, enabled)
        return jsonify({'status': 'ok'})
    except Exception as exc:
        logger.error("알림 설정 저장 오류: %s", exc)
        return jsonify({'error': str(exc)}), 500
