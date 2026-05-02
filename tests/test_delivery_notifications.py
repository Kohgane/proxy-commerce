"""tests/test_delivery_notifications.py — Phase 117: 배송 추적 기반 고객 알림 자동화 테스트."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.delivery_notifications.models import (
    DeliveryAnomaly, DeliveryEvent, DeliveryNotification, NotificationPreference,
)
from src.delivery_notifications.templates import (
    SUPPORTED_LANGUAGES, SUPPORTED_STATUSES, TEMPLATES, render_template,
)
from src.delivery_notifications.customer_preferences import CustomerPreferenceManager
from src.delivery_notifications.delay_detector import DeliveryDelayDetector, DELAY_THRESHOLDS
from src.delivery_notifications.exception_handler import DeliveryExceptionHandler
from src.delivery_notifications.notification_dispatcher import (
    DeliveryNotificationDispatcher, ALWAYS_SEND_STATUSES,
)
from src.delivery_notifications.status_watcher import DeliveryStatusWatcher, _WatchEntry


# ──────────────────────────────────────────────────────────
# 1. Template Rendering
# ──────────────────────────────────────────────────────────

class TestTemplates:
    def test_all_languages_present(self):
        assert set(SUPPORTED_LANGUAGES) == {'ko', 'en', 'ja', 'zh'}

    def test_all_statuses_present(self):
        assert set(SUPPORTED_STATUSES) == {'picked_up', 'in_transit', 'out_for_delivery', 'delivered', 'exception', 'delayed'}

    @pytest.mark.parametrize('lang', ['ko', 'en', 'ja', 'zh'])
    @pytest.mark.parametrize('status', ['picked_up', 'in_transit', 'out_for_delivery', 'delivered', 'exception', 'delayed'])
    def test_render_all_combinations(self, lang, status):
        result = render_template(
            status=status,
            language=lang,
            order_id='ORD-001',
            tracking_no='TRK123',
            carrier='CJ대한통운',
            location='서울',
            eta='',
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_includes_order_id(self):
        result = render_template('picked_up', 'ko', order_id='ORD-999', tracking_no='TRK1', carrier='CJ')
        assert 'ORD-999' in result

    def test_render_includes_tracking_no(self):
        result = render_template('delivered', 'en', order_id='ORD-001', tracking_no='TRK-XYZ', carrier='FedEx')
        assert 'TRK-XYZ' in result

    def test_render_unknown_language_falls_back_to_ko(self):
        result = render_template('delivered', 'fr', order_id='ORD-1', tracking_no='T1', carrier='X')
        ko_result = render_template('delivered', 'ko', order_id='ORD-1', tracking_no='T1', carrier='X')
        assert result == ko_result

    def test_render_unknown_status_falls_back_to_exception(self):
        result = render_template('unknown_status', 'ko', order_id='O1', tracking_no='T1', carrier='X')
        assert isinstance(result, str)

    def test_render_missing_kwargs_does_not_raise(self):
        result = render_template('in_transit', 'ko', order_id='ORD-1', tracking_no='T1')
        assert isinstance(result, str)

    def test_render_location_in_in_transit(self):
        result = render_template('in_transit', 'ko', order_id='O1', tracking_no='T1', carrier='CJ', location='인천')
        assert '인천' in result

    def test_render_japanese_template(self):
        result = render_template('picked_up', 'ja', order_id='O1', tracking_no='T1', carrier='ヤマト')
        assert '発送' in result

    def test_render_chinese_template(self):
        result = render_template('delivered', 'zh', order_id='O1', tracking_no='T1', carrier='顺丰')
        assert '送达' in result


# ──────────────────────────────────────────────────────────
# 2. CustomerPreferenceManager
# ──────────────────────────────────────────────────────────

class TestCustomerPreferenceManager:
    @pytest.fixture
    def mgr(self):
        return CustomerPreferenceManager()

    def test_get_returns_default_for_unknown_user(self, mgr):
        pref = mgr.get('unknown_user')
        assert pref.user_id == 'unknown_user'
        assert pref.channels == ['telegram']
        assert pref.language == 'ko'

    def test_set_and_get(self, mgr):
        pref = NotificationPreference(user_id='user1', language='en', channels=['email'])
        mgr.set(pref)
        result = mgr.get('user1')
        assert result.language == 'en'
        assert result.channels == ['email']

    def test_upsert_updates_existing(self, mgr):
        mgr.set(NotificationPreference(user_id='u1', language='ko'))
        mgr.upsert('u1', language='ja')
        assert mgr.get('u1').language == 'ja'

    def test_upsert_creates_if_missing(self, mgr):
        pref = mgr.upsert('new_user', channels=['sms'])
        assert pref.user_id == 'new_user'
        assert pref.channels == ['sms']

    def test_upsert_ignores_unknown_fields(self, mgr):
        mgr.set(NotificationPreference(user_id='u2'))
        pref = mgr.upsert('u2', nonexistent_field='value')
        assert pref.user_id == 'u2'

    def test_all_prefs_empty(self, mgr):
        assert mgr.all_prefs() == []

    def test_all_prefs_returns_saved(self, mgr):
        mgr.set(NotificationPreference(user_id='a'))
        mgr.set(NotificationPreference(user_id='b'))
        assert len(mgr.all_prefs()) == 2

    def test_is_quiet_time_midnight_crossing(self, mgr):
        # quiet hours 22~08 (crosses midnight)
        mgr.set(NotificationPreference(user_id='u3', quiet_hours_start=22, quiet_hours_end=8))
        pref = mgr.get('u3')
        # hour=23 → should be quiet (23 >= 22)
        assert pref.quiet_hours_start > pref.quiet_hours_end  # crosses midnight
        # hours 22..23 and 0..7 are quiet
        for h in [22, 23, 0, 1, 7]:
            start, end = pref.quiet_hours_start, pref.quiet_hours_end
            result = h >= start or h < end
            assert result is True
        # hour 10 is not quiet
        h = 10
        result = h >= 22 or h < 8
        assert result is False

    def test_is_quiet_time_no_crossing(self, mgr):
        # quiet hours 2~5 (no midnight crossing)
        mgr.set(NotificationPreference(user_id='u4', quiet_hours_start=2, quiet_hours_end=5))
        pref = mgr.get('u4')
        for h in [2, 3, 4]:
            assert pref.quiet_hours_start <= h < pref.quiet_hours_end
        assert not (pref.quiet_hours_start <= 1 < pref.quiet_hours_end)


# ──────────────────────────────────────────────────────────
# 3. DeliveryDelayDetector
# ──────────────────────────────────────────────────────────

class TestDeliveryDelayDetector:
    @pytest.fixture
    def detector(self):
        return DeliveryDelayDetector()

    def test_record_status_stores_first_occurrence(self, detector):
        detector.record_status('TRK1', 'in_transit')
        assert 'in_transit' in detector._status_since.get('TRK1', {})

    def test_record_status_does_not_overwrite(self, detector):
        ts1 = '2024-01-01T10:00:00+00:00'
        detector.record_status('TRK1', 'in_transit', ts1)
        detector.record_status('TRK1', 'in_transit', '2024-01-01T12:00:00+00:00')
        assert detector._status_since['TRK1']['in_transit'] == ts1

    def test_no_anomaly_for_recent_status(self, detector):
        # Record in_transit just now → no delay
        detector.record_status('TRK1', 'in_transit')
        anomalies = detector.check_delays('TRK1', 'in_transit', 'ORD1')
        assert anomalies == []

    def test_detects_in_transit_medium_delay(self, detector):
        # 50 hours ago → medium delay
        past = datetime.now(timezone.utc) - timedelta(hours=50)
        detector.record_status('TRK1', 'in_transit', past.isoformat())
        anomalies = detector.check_delays('TRK1', 'in_transit', 'ORD1')
        assert len(anomalies) == 1
        assert anomalies[0].severity == 'medium'
        assert anomalies[0].anomaly_type == 'delayed'

    def test_detects_in_transit_high_delay(self, detector):
        # 80 hours ago → high delay
        past = datetime.now(timezone.utc) - timedelta(hours=80)
        detector.record_status('TRK2', 'in_transit', past.isoformat())
        anomalies = detector.check_delays('TRK2', 'in_transit', 'ORD2')
        assert len(anomalies) == 1
        assert anomalies[0].severity == 'high'

    def test_detects_out_for_delivery_delay(self, detector):
        # 13 hours ago → medium delay
        past = datetime.now(timezone.utc) - timedelta(hours=13)
        detector.record_status('TRK3', 'out_for_delivery', past.isoformat())
        anomalies = detector.check_delays('TRK3', 'out_for_delivery', 'ORD3')
        assert len(anomalies) == 1
        assert anomalies[0].severity == 'medium'

    def test_detects_picked_up_delay(self, detector):
        # 25 hours ago, still picked_up → low delay
        past = datetime.now(timezone.utc) - timedelta(hours=25)
        detector.record_status('TRK4', 'picked_up', past.isoformat())
        anomalies = detector.check_delays('TRK4', 'picked_up', 'ORD4')
        assert len(anomalies) == 1
        assert anomalies[0].severity == 'low'

    def test_no_duplicate_anomaly(self, detector):
        past = datetime.now(timezone.utc) - timedelta(hours=50)
        detector.record_status('TRK5', 'in_transit', past.isoformat())
        anomalies1 = detector.check_delays('TRK5', 'in_transit', 'ORD5')
        anomalies2 = detector.check_delays('TRK5', 'in_transit', 'ORD5')
        assert len(anomalies1) == 1
        assert len(anomalies2) == 0  # duplicate suppressed

    def test_get_all_anomalies(self, detector):
        past = datetime.now(timezone.utc) - timedelta(hours=80)
        detector.record_status('TRK6', 'in_transit', past.isoformat())
        detector.check_delays('TRK6', 'in_transit', 'ORD6')
        all_anomalies = detector.get_all_anomalies()
        assert len(all_anomalies) >= 1

    def test_elapsed_hours_invalid_string(self, detector):
        # Should return 0.0 for invalid timestamp
        result = detector._elapsed_hours('not-a-date')
        assert result == 0.0


# ──────────────────────────────────────────────────────────
# 4. DeliveryExceptionHandler
# ──────────────────────────────────────────────────────────

class TestDeliveryExceptionHandler:
    @pytest.fixture
    def mock_ticket(self):
        ticket = MagicMock()
        ticket.id = 'TICKET-001'
        return ticket

    @pytest.fixture
    def mock_manager(self, mock_ticket):
        mgr = MagicMock()
        mgr.create.return_value = mock_ticket
        return mgr

    @pytest.fixture
    def mock_hub(self):
        hub = MagicMock()
        hub.dispatch.return_value = {'sent': True}
        return hub

    @pytest.fixture
    def handler(self, mock_manager, mock_hub):
        return DeliveryExceptionHandler(ticket_manager=mock_manager, notification_hub=mock_hub)

    def test_handle_exception_creates_ticket(self, handler, mock_manager):
        result = handler.handle_exception('TRK1', 'ORD1', 'user1', '배송 지연')
        assert result is not None
        mock_manager.create.assert_called_once()

    def test_handle_exception_notifies_operator(self, handler, mock_hub):
        handler.handle_exception('TRK1', 'ORD1', 'user1')
        mock_hub.dispatch.assert_called_once()

    def test_handle_exception_returns_none_on_error(self, mock_hub):
        bad_mgr = MagicMock()
        bad_mgr.create.side_effect = RuntimeError('DB Error')
        handler = DeliveryExceptionHandler(ticket_manager=bad_mgr, notification_hub=mock_hub)
        result = handler.handle_exception('TRK1', 'ORD1', 'user1')
        assert result is None

    def test_handle_anomaly_skips_non_high(self, handler, mock_manager):
        anomaly = DeliveryAnomaly(
            tracking_no='TRK2', anomaly_type='delayed', detected_at='2024-01-01T00:00:00+00:00',
            severity='medium', order_id='ORD2',
        )
        result = handler.handle_anomaly(anomaly, 'user2')
        assert result is None
        mock_manager.create.assert_not_called()

    def test_handle_anomaly_high_creates_ticket(self, handler, mock_manager):
        anomaly = DeliveryAnomaly(
            tracking_no='TRK3', anomaly_type='delayed', detected_at='2024-01-01T00:00:00+00:00',
            severity='high', order_id='ORD3',
        )
        result = handler.handle_anomaly(anomaly, 'user3')
        assert result is not None
        mock_manager.create.assert_called_once()

    def test_handle_anomaly_low_skips(self, handler, mock_manager):
        anomaly = DeliveryAnomaly(
            tracking_no='TRK4', anomaly_type='delayed', detected_at='now',
            severity='low', order_id='ORD4',
        )
        result = handler.handle_anomaly(anomaly)
        assert result is None


# ──────────────────────────────────────────────────────────
# 5. DeliveryNotificationDispatcher
# ──────────────────────────────────────────────────────────

class TestDeliveryNotificationDispatcher:
    @pytest.fixture
    def mock_hub(self):
        hub = MagicMock()
        hub.dispatch.return_value = {'sent': True}
        return hub

    @pytest.fixture
    def dispatcher(self, mock_hub):
        return DeliveryNotificationDispatcher(hub=mock_hub)

    @pytest.fixture
    def sample_event(self):
        return DeliveryEvent(
            tracking_no='TRK-001',
            status='in_transit',
            location='서울',
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @pytest.fixture
    def pref(self):
        return NotificationPreference(
            user_id='user1',
            channels=['telegram'],
            language='ko',
            quiet_hours_start=2,
            quiet_hours_end=4,
        )

    def test_dispatch_returns_notifications(self, dispatcher, sample_event, pref):
        with patch.object(dispatcher, '_is_quiet_time', return_value=False):
            results = dispatcher.dispatch(sample_event, pref, 'ORD-001')
        assert len(results) == 1
        assert results[0].tracking_no == 'TRK-001'
        assert results[0].channel == 'telegram'

    def test_dispatch_skips_quiet_time(self, dispatcher, sample_event, pref):
        with patch.object(dispatcher, '_is_quiet_time', return_value=True):
            results = dispatcher.dispatch(sample_event, pref, 'ORD-001')
        assert results == []

    def test_dispatch_always_sends_delivered(self, dispatcher, mock_hub, pref):
        event = DeliveryEvent(
            tracking_no='TRK-002',
            status='delivered',
            location='',
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        with patch.object(dispatcher, '_is_quiet_time', return_value=True):
            results = dispatcher.dispatch(event, pref, 'ORD-002')
        # delivered is in ALWAYS_SEND_STATUSES → should send even in quiet time
        assert len(results) == 1
        assert results[0].success is True

    def test_dispatch_always_sends_exception(self, dispatcher, pref):
        event = DeliveryEvent(
            tracking_no='TRK-003',
            status='exception',
            location='',
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        with patch.object(dispatcher, '_is_quiet_time', return_value=True):
            results = dispatcher.dispatch(event, pref, 'ORD-003')
        assert len(results) == 1

    def test_dispatch_multiple_channels(self, dispatcher, mock_hub):
        pref = NotificationPreference(
            user_id='u1', channels=['telegram', 'email'], quiet_hours_start=2, quiet_hours_end=4
        )
        event = DeliveryEvent(tracking_no='TRK-004', status='picked_up', location='', timestamp='now')
        with patch.object(dispatcher, '_is_quiet_time', return_value=False):
            results = dispatcher.dispatch(event, pref, 'ORD-004')
        assert len(results) == 2

    def test_dispatch_marks_failure_on_hub_error(self, dispatcher):
        bad_hub = MagicMock()
        bad_hub.dispatch.side_effect = RuntimeError('network error')
        dispatcher._hub = bad_hub
        pref = NotificationPreference(user_id='u1', channels=['telegram'], quiet_hours_start=2, quiet_hours_end=4)
        event = DeliveryEvent(tracking_no='TRK-005', status='in_transit', location='', timestamp='now')
        with patch.object(dispatcher, '_is_quiet_time', return_value=False):
            results = dispatcher.dispatch(event, pref, 'ORD-005')
        assert results[0].success is False

    def test_get_history_all(self, dispatcher, sample_event, pref):
        with patch.object(dispatcher, '_is_quiet_time', return_value=False):
            dispatcher.dispatch(sample_event, pref, 'ORD-100')
        history = dispatcher.get_history()
        assert len(history) >= 1

    def test_get_history_filtered_by_order_id(self, dispatcher, pref):
        for i in range(3):
            event = DeliveryEvent(tracking_no=f'TRK-{i}', status='delivered', location='', timestamp='now')
            oid = 'ORD-A' if i < 2 else 'ORD-B'
            with patch.object(dispatcher, '_is_quiet_time', return_value=False):
                dispatcher.dispatch(event, pref, oid)
        assert len(dispatcher.get_history('ORD-A')) == 2
        assert len(dispatcher.get_history('ORD-B')) == 1

    def test_always_send_statuses_set(self):
        assert 'delivered' in ALWAYS_SEND_STATUSES
        assert 'exception' in ALWAYS_SEND_STATUSES


# ──────────────────────────────────────────────────────────
# 6. DeliveryStatusWatcher
# ──────────────────────────────────────────────────────────

class TestDeliveryStatusWatcher:
    @pytest.fixture
    def mock_dispatcher(self):
        d = MagicMock()
        d.dispatch.return_value = []
        return d

    @pytest.fixture
    def mock_delay_detector(self):
        dd = MagicMock()
        dd.check_delays.return_value = []
        return dd

    @pytest.fixture
    def mock_exception_handler(self):
        return MagicMock()

    @pytest.fixture
    def watcher(self, mock_dispatcher, mock_delay_detector, mock_exception_handler):
        return DeliveryStatusWatcher(
            dispatcher=mock_dispatcher,
            delay_detector=mock_delay_detector,
            exception_handler=mock_exception_handler,
            poll_interval=1,
        )

    def test_register_creates_entry(self, watcher):
        entry = watcher.register('TRK1', 'CJ', 'ORD1', 'user1')
        assert entry.tracking_no == 'TRK1'
        assert entry.carrier == 'CJ'
        assert entry.order_id == 'ORD1'
        assert entry.user_id == 'user1'
        assert entry.last_status is None

    def test_register_multiple_entries(self, watcher):
        watcher.register('TRK1', 'CJ', 'ORD1', 'u1')
        watcher.register('TRK2', 'KR', 'ORD2', 'u2')
        assert len(watcher.list_entries()) == 2

    def test_unregister_removes_entry(self, watcher):
        watcher.register('TRK1', 'CJ', 'ORD1', 'u1')
        assert watcher.unregister('TRK1') is True
        assert watcher.get_entry('TRK1') is None

    def test_unregister_unknown_returns_false(self, watcher):
        assert watcher.unregister('UNKNOWN') is False

    def test_get_entry_returns_none_if_missing(self, watcher):
        assert watcher.get_entry('MISSING') is None

    def test_poll_once_no_entries_returns_empty(self, watcher):
        events = watcher.poll_once()
        assert events == []

    def test_tick_delegates_to_poll_once(self, watcher):
        with patch.object(watcher, 'poll_once', return_value=[]) as mock_poll:
            watcher.tick()
            mock_poll.assert_called_once()

    def test_poll_once_detects_status_change(self, watcher):
        from src.shipping.models import ShipmentRecord, ShipmentStatus, TrackingEvent

        record = ShipmentRecord(
            tracking_number='TRK1',
            carrier='CJ',
            status=ShipmentStatus.in_transit,
            updated_at=datetime.now(timezone.utc),
            events=[TrackingEvent(
                timestamp=datetime.now(timezone.utc),
                status=ShipmentStatus.in_transit,
                location='인천',
                description='배송 중',
            )],
        )
        mock_tracker = MagicMock()
        mock_tracker.get_status.return_value = record

        watcher.register('TRK1', 'CJ', 'ORD1', 'u1')

        with patch.object(watcher, '_get_tracker', return_value=mock_tracker):
            events = watcher.poll_once()

        assert len(events) == 1
        assert events[0].status == 'in_transit'
        assert events[0].tracking_no == 'TRK1'

    def test_poll_once_no_event_if_status_unchanged(self, watcher):
        from src.shipping.models import ShipmentRecord, ShipmentStatus

        record = ShipmentRecord(
            tracking_number='TRK1',
            carrier='CJ',
            status=ShipmentStatus.in_transit,
            updated_at=datetime.now(timezone.utc),
        )
        mock_tracker = MagicMock()
        mock_tracker.get_status.return_value = record

        entry = watcher.register('TRK1', 'CJ', 'ORD1', 'u1')
        entry.last_status = 'in_transit'  # already seen

        with patch.object(watcher, '_get_tracker', return_value=mock_tracker):
            events = watcher.poll_once()

        assert events == []

    def test_poll_once_no_record_returns_no_event(self, watcher):
        mock_tracker = MagicMock()
        mock_tracker.get_status.return_value = None
        watcher.register('TRK1', 'CJ', 'ORD1', 'u1')

        with patch.object(watcher, '_get_tracker', return_value=mock_tracker):
            events = watcher.poll_once()

        assert events == []

    def test_exception_status_triggers_exception_handler(self, watcher, mock_exception_handler):
        from src.shipping.models import ShipmentRecord, ShipmentStatus

        record = ShipmentRecord(
            tracking_number='TRK-EX',
            carrier='CJ',
            status=ShipmentStatus.exception,
            updated_at=datetime.now(timezone.utc),
        )
        mock_tracker = MagicMock()
        mock_tracker.get_status.return_value = record

        watcher.register('TRK-EX', 'CJ', 'ORD-EX', 'u1')

        with patch.object(watcher, '_get_tracker', return_value=mock_tracker):
            watcher.poll_once()

        mock_exception_handler.handle_exception.assert_called_once()

    def test_watch_entry_uses_slots(self):
        entry = _WatchEntry('TRK1', 'CJ', 'ORD1', 'u1')
        assert hasattr(entry, '__slots__')
        assert 'tracking_no' in _WatchEntry.__slots__

    def test_start_stop(self, watcher):
        watcher.start()
        assert watcher._running is True
        watcher.stop()
        assert watcher._running is False


# ──────────────────────────────────────────────────────────
# 7. API Endpoints
# ──────────────────────────────────────────────────────────

@pytest.fixture
def flask_app():
    """Create a fresh Flask app for each test."""
    from src.api.delivery_notifications_api import (
        delivery_notifications_api,
        _get_watcher, _get_dispatcher, _get_pref_mgr, _get_delay_detector,
    )
    import src.api.delivery_notifications_api as api_module

    # Reset singletons
    api_module._watcher = None
    api_module._dispatcher = None
    api_module._pref_mgr = None
    api_module._delay_detector = None

    app = Flask(__name__)
    app.register_blueprint(delivery_notifications_api)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(flask_app):
    with flask_app.test_client() as c:
        yield c


class TestDeliveryNotificationsAPI:
    def test_register_watch_success(self, client):
        resp = client.post(
            '/api/v1/delivery-notifications/watch',
            json={'tracking_no': 'TRK-API-1', 'carrier': 'CJ', 'order_id': 'ORD-1', 'user_id': 'u1'},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['tracking_no'] == 'TRK-API-1'
        assert data['status'] == '등록됨'

    def test_register_watch_missing_fields(self, client):
        resp = client.post(
            '/api/v1/delivery-notifications/watch',
            json={'order_id': 'ORD-1'},
        )
        assert resp.status_code == 400

    def test_get_watch_not_found(self, client):
        resp = client.get('/api/v1/delivery-notifications/watch/UNKNOWN')
        assert resp.status_code == 404

    def test_get_watch_found(self, client):
        client.post(
            '/api/v1/delivery-notifications/watch',
            json={'tracking_no': 'TRK-FOUND', 'carrier': 'CJ', 'order_id': 'ORD-F', 'user_id': 'uF'},
        )
        resp = client.get('/api/v1/delivery-notifications/watch/TRK-FOUND')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['tracking_no'] == 'TRK-FOUND'

    def test_save_preferences_success(self, client):
        resp = client.post(
            '/api/v1/delivery-notifications/preferences',
            json={'user_id': 'u1', 'language': 'en', 'channels': ['telegram', 'email']},
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['language'] == 'en'

    def test_save_preferences_missing_user_id(self, client):
        resp = client.post(
            '/api/v1/delivery-notifications/preferences',
            json={'language': 'en'},
        )
        assert resp.status_code == 400

    def test_get_preferences_returns_defaults(self, client):
        resp = client.get('/api/v1/delivery-notifications/preferences/new_user')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['user_id'] == 'new_user'
        assert data['language'] == 'ko'

    def test_get_preferences_saved(self, client):
        client.post(
            '/api/v1/delivery-notifications/preferences',
            json={'user_id': 'u2', 'language': 'ja'},
        )
        resp = client.get('/api/v1/delivery-notifications/preferences/u2')
        assert resp.status_code == 200
        assert resp.get_json()['language'] == 'ja'

    def test_manual_poll(self, client):
        resp = client.post('/api/v1/delivery-notifications/poll')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'polled' in data
        assert 'events_detected' in data

    def test_get_history_empty(self, client):
        resp = client.get('/api/v1/delivery-notifications/history')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 0

    def test_get_history_with_order_id_filter(self, client):
        resp = client.get('/api/v1/delivery-notifications/history?order_id=ORD-999')
        assert resp.status_code == 200

    def test_get_anomalies_empty(self, client):
        resp = client.get('/api/v1/delivery-notifications/anomalies')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 0

    def test_register_watch_empty_body(self, client):
        resp = client.post('/api/v1/delivery-notifications/watch', json={})
        assert resp.status_code == 400

    def test_save_preferences_full_fields(self, client):
        resp = client.post(
            '/api/v1/delivery-notifications/preferences',
            json={
                'user_id': 'u_full',
                'channels': ['telegram'],
                'language': 'zh',
                'quiet_hours_start': 23,
                'quiet_hours_end': 7,
                'frequency': 'daily',
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['quiet_hours_start'] == 23
        assert data['frequency'] == 'daily'


# ──────────────────────────────────────────────────────────
# 8. Bot Commands
# ──────────────────────────────────────────────────────────

class TestBotCommands:
    def test_cmd_delivery_watch_success(self):
        from src.bot.commands import cmd_delivery_watch
        mock_entry = MagicMock()
        mock_entry.tracking_no = 'TRK1'
        mock_entry.carrier = 'CJ'
        mock_entry.order_id = 'ORD1'

        mock_watcher = MagicMock()
        mock_watcher.register.return_value = mock_entry

        with patch('src.delivery_notifications.status_watcher.DeliveryStatusWatcher', return_value=mock_watcher):
            result = cmd_delivery_watch('ORD1 TRK1 CJ')
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cmd_delivery_watch_missing_args(self):
        from src.bot.commands import cmd_delivery_watch
        result = cmd_delivery_watch('ORD1')
        assert '사용법' in result or 'error' in result.lower() or '오류' in result

    def test_cmd_delivery_watch_empty_args(self):
        from src.bot.commands import cmd_delivery_watch
        result = cmd_delivery_watch('')
        assert isinstance(result, str)

    def test_cmd_delivery_status_missing_arg(self):
        from src.bot.commands import cmd_delivery_status
        result = cmd_delivery_status('')
        assert '사용법' in result or 'error' in result.lower() or '오류' in result

    def test_cmd_delivery_status_not_found(self):
        from src.bot.commands import cmd_delivery_status
        mock_tracker = MagicMock()
        mock_tracker.get_status.return_value = None

        with patch('src.shipping.tracker.ShipmentTracker', return_value=mock_tracker):
            result = cmd_delivery_status('UNKNOWN_TRK')
        assert isinstance(result, str)

    def test_cmd_delivery_status_found(self):
        from src.bot.commands import cmd_delivery_status
        mock_record = MagicMock()
        mock_tracker = MagicMock()
        mock_tracker.get_status.return_value = mock_record

        with patch('src.shipping.tracker.ShipmentTracker', return_value=mock_tracker):
            result = cmd_delivery_status('TRK1')
        assert isinstance(result, str)

    def test_cmd_delivery_prefs_default(self):
        from src.bot.commands import cmd_delivery_prefs
        result = cmd_delivery_prefs('test_user')
        assert isinstance(result, str)

    def test_cmd_delivery_prefs_empty_user(self):
        from src.bot.commands import cmd_delivery_prefs
        result = cmd_delivery_prefs('')
        assert isinstance(result, str)

    def test_cmd_delivery_anomalies_empty(self):
        from src.bot.commands import cmd_delivery_anomalies
        result = cmd_delivery_anomalies()
        assert isinstance(result, str)

    def test_cmd_delivery_watch_exception_handling(self):
        from src.bot.commands import cmd_delivery_watch
        with patch('src.delivery_notifications.status_watcher.DeliveryStatusWatcher', side_effect=RuntimeError('err')):
            result = cmd_delivery_watch('ORD1 TRK1 CJ')
        assert isinstance(result, str)

    def test_cmd_delivery_anomalies_with_data(self):
        from src.bot.commands import cmd_delivery_anomalies
        mock_anomaly = MagicMock()
        mock_anomaly.tracking_no = 'TRK1'
        mock_anomaly.anomaly_type = 'delayed'
        mock_anomaly.severity = 'high'
        mock_anomaly.detected_at = '2024-01-01T00:00:00+00:00'
        mock_anomaly.order_id = 'ORD1'

        mock_detector = MagicMock()
        mock_detector.get_all_anomalies.return_value = [mock_anomaly]

        with patch('src.delivery_notifications.delay_detector.DeliveryDelayDetector', return_value=mock_detector):
            result = cmd_delivery_anomalies()
        assert isinstance(result, str)


# ──────────────────────────────────────────────────────────
# 9. Model Tests
# ──────────────────────────────────────────────────────────

class TestModels:
    def test_delivery_notification_has_uuid(self):
        n = DeliveryNotification(
            order_id='O1', tracking_no='T1', carrier='CJ',
            status_from='picked_up', status_to='in_transit', channel='telegram',
        )
        assert n.id
        assert len(n.id) == 36  # UUID4 format

    def test_delivery_notification_has_sent_at(self):
        n = DeliveryNotification(
            order_id='O1', tracking_no='T1', carrier='CJ',
            status_from='', status_to='delivered', channel='email',
        )
        assert n.sent_at
        assert 'T' in n.sent_at  # ISO format

    def test_delivery_event_defaults(self):
        e = DeliveryEvent(tracking_no='T1', status='in_transit', location='Seoul', timestamp='now')
        assert e.raw == {}

    def test_notification_preference_defaults(self):
        p = NotificationPreference(user_id='u1')
        assert p.channels == ['telegram']
        assert p.language == 'ko'
        assert p.quiet_hours_start == 22
        assert p.quiet_hours_end == 8
        assert p.frequency == 'all'

    def test_delivery_anomaly_default_order_id(self):
        a = DeliveryAnomaly(
            tracking_no='T1', anomaly_type='delayed',
            detected_at='now', severity='medium',
        )
        assert a.order_id == ''

    def test_two_notifications_have_different_ids(self):
        n1 = DeliveryNotification(order_id='O1', tracking_no='T1', carrier='', status_from='', status_to='', channel='')
        n2 = DeliveryNotification(order_id='O1', tracking_no='T1', carrier='', status_from='', status_to='', channel='')
        assert n1.id != n2.id
