"""src/api/delivery_notifications_api.py — Phase 117: 배송 추적 기반 고객 알림 자동화 API.

Blueprint: /api/v1/delivery-notifications

엔드포인트:
  POST /watch                  — 배송 추적 등록
  GET  /watch/<tracking_no>    — 추적 상태/이력 조회
  POST /preferences            — 고객 알림 설정 저장
  GET  /preferences/<user_id>  — 고객 알림 설정 조회
  POST /poll                   — 수동 폴링 트리거 (관리자)
  GET  /history                — 알림 발송 이력 (order_id 필터)
  GET  /anomalies              — 감지된 지연/예외 목록
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

delivery_notifications_api = Blueprint(
    'delivery_notifications_api',
    __name__,
    url_prefix='/api/v1/delivery-notifications',
)

# 모듈 레벨 싱글턴 (지연 초기화)
_watcher = None
_dispatcher = None
_pref_mgr = None
_delay_detector = None


def _get_watcher():
    global _watcher
    if _watcher is None:
        from ..delivery_notifications.status_watcher import DeliveryStatusWatcher
        from ..delivery_notifications.notification_dispatcher import DeliveryNotificationDispatcher
        from ..delivery_notifications.delay_detector import DeliveryDelayDetector
        from ..delivery_notifications.exception_handler import DeliveryExceptionHandler
        from ..delivery_notifications.customer_preferences import CustomerPreferenceManager
        _watcher = DeliveryStatusWatcher(
            dispatcher=_get_dispatcher(),
            delay_detector=_get_delay_detector(),
            preference_manager=_get_pref_mgr(),
        )
    return _watcher


def _get_dispatcher():
    global _dispatcher
    if _dispatcher is None:
        from ..delivery_notifications.notification_dispatcher import DeliveryNotificationDispatcher
        _dispatcher = DeliveryNotificationDispatcher()
    return _dispatcher


def _get_pref_mgr():
    global _pref_mgr
    if _pref_mgr is None:
        from ..delivery_notifications.customer_preferences import CustomerPreferenceManager
        _pref_mgr = CustomerPreferenceManager()
    return _pref_mgr


def _get_delay_detector():
    global _delay_detector
    if _delay_detector is None:
        from ..delivery_notifications.delay_detector import DeliveryDelayDetector
        _delay_detector = DeliveryDelayDetector()
    return _delay_detector


# ---------------------------------------------------------------------------
# POST /watch
# ---------------------------------------------------------------------------

@delivery_notifications_api.post('/watch')
def register_watch():
    """POST /api/v1/delivery-notifications/watch — 배송 추적 등록."""
    body = request.get_json(force=True, silent=True) or {}
    order_id = body.get('order_id', '')
    tracking_no = body.get('tracking_no', '')
    carrier = body.get('carrier', '')
    user_id = body.get('user_id', '')

    if not tracking_no or not carrier:
        return jsonify({'error': 'tracking_no, carrier 필수'}), 400

    try:
        watcher = _get_watcher()
        entry = watcher.register(tracking_no, carrier, order_id, user_id)
        return jsonify({
            'tracking_no': entry.tracking_no,
            'carrier': entry.carrier,
            'order_id': entry.order_id,
            'user_id': entry.user_id,
            'status': '등록됨',
        }), 201
    except Exception as exc:
        logger.error('배송 추적 등록 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /watch/<tracking_no>
# ---------------------------------------------------------------------------

@delivery_notifications_api.get('/watch/<tracking_no>')
def get_watch(tracking_no: str):
    """GET /api/v1/delivery-notifications/watch/<tracking_no> — 추적 상태/이력 조회."""
    try:
        watcher = _get_watcher()
        entry = watcher.get_entry(tracking_no)
        if entry is None:
            return jsonify({'error': f'등록되지 않은 운송장: {tracking_no}'}), 404

        dispatcher = _get_dispatcher()
        history = dispatcher.get_history(entry.order_id)

        return jsonify({
            'tracking_no': entry.tracking_no,
            'carrier': entry.carrier,
            'order_id': entry.order_id,
            'user_id': entry.user_id,
            'last_status': entry.last_status,
            'notification_count': len(history),
        })
    except Exception as exc:
        logger.error('추적 조회 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# POST /preferences
# ---------------------------------------------------------------------------

@delivery_notifications_api.post('/preferences')
def save_preferences():
    """POST /api/v1/delivery-notifications/preferences — 고객 알림 설정 저장."""
    body = request.get_json(force=True, silent=True) or {}
    user_id = body.get('user_id', '')
    if not user_id:
        return jsonify({'error': 'user_id 필수'}), 400

    try:
        from ..delivery_notifications.models import NotificationPreference
        mgr = _get_pref_mgr()
        pref = NotificationPreference(
            user_id=user_id,
            channels=body.get('channels', ['telegram']),
            language=body.get('language', 'ko'),
            quiet_hours_start=int(body.get('quiet_hours_start', 22)),
            quiet_hours_end=int(body.get('quiet_hours_end', 8)),
            frequency=body.get('frequency', 'all'),
        )
        mgr.set(pref)
        return jsonify({
            'user_id': pref.user_id,
            'channels': pref.channels,
            'language': pref.language,
            'quiet_hours_start': pref.quiet_hours_start,
            'quiet_hours_end': pref.quiet_hours_end,
            'frequency': pref.frequency,
        }), 201
    except Exception as exc:
        logger.error('알림 설정 저장 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /preferences/<user_id>
# ---------------------------------------------------------------------------

@delivery_notifications_api.get('/preferences/<user_id>')
def get_preferences(user_id: str):
    """GET /api/v1/delivery-notifications/preferences/<user_id> — 고객 알림 설정 조회."""
    try:
        mgr = _get_pref_mgr()
        pref = mgr.get(user_id)
        return jsonify({
            'user_id': pref.user_id,
            'channels': pref.channels,
            'language': pref.language,
            'quiet_hours_start': pref.quiet_hours_start,
            'quiet_hours_end': pref.quiet_hours_end,
            'frequency': pref.frequency,
        })
    except Exception as exc:
        logger.error('알림 설정 조회 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# POST /poll
# ---------------------------------------------------------------------------

@delivery_notifications_api.post('/poll')
def manual_poll():
    """POST /api/v1/delivery-notifications/poll — 수동 폴링 트리거 (관리자)."""
    try:
        watcher = _get_watcher()
        events = watcher.poll_once()
        return jsonify({
            'polled': len(watcher.list_entries()),
            'events_detected': len(events),
            'events': [
                {
                    'tracking_no': e.tracking_no,
                    'status': e.status,
                    'location': e.location,
                    'timestamp': e.timestamp,
                }
                for e in events
            ],
        })
    except Exception as exc:
        logger.error('수동 폴링 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /history
# ---------------------------------------------------------------------------

@delivery_notifications_api.get('/history')
def get_history():
    """GET /api/v1/delivery-notifications/history — 알림 발송 이력."""
    order_id = request.args.get('order_id', '')
    try:
        dispatcher = _get_dispatcher()
        history = dispatcher.get_history(order_id)
        return jsonify({
            'count': len(history),
            'history': [
                {
                    'id': n.id,
                    'order_id': n.order_id,
                    'tracking_no': n.tracking_no,
                    'status_to': n.status_to,
                    'channel': n.channel,
                    'sent_at': n.sent_at,
                    'success': n.success,
                }
                for n in history
            ],
        })
    except Exception as exc:
        logger.error('이력 조회 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /anomalies
# ---------------------------------------------------------------------------

@delivery_notifications_api.get('/anomalies')
def get_anomalies():
    """GET /api/v1/delivery-notifications/anomalies — 감지된 지연/예외 목록."""
    try:
        detector = _get_delay_detector()
        anomalies = detector.get_all_anomalies()
        return jsonify({
            'count': len(anomalies),
            'anomalies': [
                {
                    'tracking_no': a.tracking_no,
                    'anomaly_type': a.anomaly_type,
                    'severity': a.severity,
                    'detected_at': a.detected_at,
                    'order_id': a.order_id,
                }
                for a in anomalies
            ],
        })
    except Exception as exc:
        logger.error('이상 목록 조회 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500
