"""tests/test_audit_extended.py — Phase 41: 감사 로그 확장 테스트."""
import pytest
from datetime import datetime, timezone


class TestAuditStore:
    def setup_method(self):
        from src.audit.audit_store import AuditStore
        self.store = AuditStore(max_records=100)

    def _make_entry(self, event_type='order.created', actor='system'):
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event_type': event_type,
            'actor': actor,
            'resource': 'order:001',
            'details': {},
            'ip_address': '',
        }

    def test_append(self):
        entry = self._make_entry()
        stored = self.store.append(entry)
        assert stored is entry
        assert self.store.count() == 1

    def test_get_all(self):
        self.store.append(self._make_entry())
        self.store.append(self._make_entry())
        all_records = self.store.get_all()
        assert len(all_records) == 2

    def test_get_recent(self):
        for i in range(10):
            self.store.append(self._make_entry())
        recent = self.store.get_recent(5)
        assert len(recent) == 5

    def test_max_records(self):
        store = __import__('src.audit.audit_store', fromlist=['AuditStore']).AuditStore(max_records=3)
        for i in range(5):
            store.append(self._make_entry())
        assert store.count() == 3

    def test_clear(self):
        self.store.append(self._make_entry())
        count = self.store.clear()
        assert count == 1
        assert self.store.count() == 0

    def test_file_backup(self, tmp_path):
        path = str(tmp_path / 'audit.jsonl')
        store = __import__('src.audit.audit_store', fromlist=['AuditStore']).AuditStore(backup_path=path)
        entry = self._make_entry()
        store.append(entry)
        # 파일 로드 확인
        store2 = __import__('src.audit.audit_store', fromlist=['AuditStore']).AuditStore(backup_path=path)
        loaded = store2.load_from_file(path)
        assert loaded == 1


class TestAuditQuery:
    def setup_method(self):
        from src.audit.audit_store import AuditStore
        from src.audit.audit_query import AuditQuery
        self.store = AuditStore()
        self.query = AuditQuery(store=self.store)
        # 샘플 레코드 추가
        self.store.append({'timestamp': '2024-01-01T10:00:00+00:00', 'event_type': 'order.created',
                           'actor': 'user1', 'resource': 'order:001', 'details': {}, 'ip_address': ''})
        self.store.append({'timestamp': '2024-01-02T10:00:00+00:00', 'event_type': 'order.shipped',
                           'actor': 'user2', 'resource': 'order:002', 'details': {}, 'ip_address': ''})
        self.store.append({'timestamp': '2024-01-03T10:00:00+00:00', 'event_type': 'admin.login',
                           'actor': 'admin', 'resource': 'auth', 'details': {'note': 'test_keyword'},
                           'ip_address': '127.0.0.1'})

    def test_filter_by_event_type(self):
        records = self.query.filter(event_type='order.created')
        assert len(records) == 1

    def test_filter_by_user(self):
        records = self.query.filter(user_id='user1')
        assert len(records) == 1

    def test_filter_by_resource(self):
        records = self.query.filter(resource='order:001')
        assert len(records) == 1

    def test_filter_by_start_time(self):
        records = self.query.filter(start_time='2024-01-02T00:00:00+00:00')
        assert len(records) == 2

    def test_filter_by_end_time(self):
        records = self.query.filter(end_time='2024-01-01T23:59:59+00:00')
        assert len(records) == 1

    def test_search_keyword(self):
        results = self.query.search('test_keyword')
        assert len(results) == 1

    def test_search_no_results(self):
        results = self.query.search('not_in_data')
        assert len(results) == 0

    def test_paginate(self):
        records = self.store.get_all()
        page1 = self.query.paginate(records, page=1, per_page=2)
        assert len(page1['items']) == 2
        assert page1['total'] == 3
        assert page1['pages'] == 2

    def test_query_combined(self):
        result = self.query.query(event_type='order.created', page=1, per_page=10)
        assert result['total'] == 1
        assert len(result['items']) == 1


class TestAuditDecorator:
    def test_audit_log_success(self):
        from src.audit.audit_store import AuditStore
        from src.audit.decorators import audit_log
        store = AuditStore()

        @audit_log(event_type='test.action', actor='test_actor', store=store)
        def my_function(x):
            return x * 2

        result = my_function(5)
        assert result == 10
        assert store.count() == 1
        entry = store.get_all()[0]
        assert entry['event_type'] == 'test.action'
        assert entry['actor'] == 'test_actor'

    def test_audit_log_error(self):
        from src.audit.audit_store import AuditStore
        from src.audit.decorators import audit_log
        store = AuditStore()

        @audit_log(event_type='test.fail', store=store)
        def failing_fn():
            raise ValueError('test error')

        with pytest.raises(ValueError):
            failing_fn()
        assert store.count() == 1
        entry = store.get_all()[0]
        assert entry['details']['error'] == 'test error'
        assert entry['details']['success'] is False

    def test_audit_log_preserves_return(self):
        from src.audit.decorators import audit_log

        @audit_log(event_type='test.return')
        def returns_value():
            return {'key': 'value'}

        result = returns_value()
        assert result == {'key': 'value'}

    def test_audit_log_no_store(self):
        from src.audit.decorators import audit_log

        @audit_log(event_type='no_store.action')
        def simple():
            return 'result'

        result = simple()
        assert result == 'result'


class TestAuditAPI:
    def setup_method(self):
        from flask import Flask
        from src.api.audit_api import audit_bp, _get_store
        app = Flask(__name__)
        app.register_blueprint(audit_bp)
        self.client = app.test_client()
        # 테스트 간 store 초기화
        _get_store().clear()

    def test_status(self):
        resp = self.client.get('/api/v1/audit/status')
        assert resp.status_code == 200

    def test_create_audit_log(self):
        resp = self.client.post('/api/v1/audit/', json={
            'event_type': 'order.created',
            'actor': 'test_actor',
            'resource': 'order:001',
        })
        assert resp.status_code == 201

    def test_create_missing_event_type(self):
        resp = self.client.post('/api/v1/audit/', json={'actor': 'test'})
        assert resp.status_code == 400

    def test_list_audit_logs(self):
        self.client.post('/api/v1/audit/', json={'event_type': 'test.event'})
        resp = self.client.get('/api/v1/audit/')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'items' in data

    def test_search(self):
        self.client.post('/api/v1/audit/', json={
            'event_type': 'search.test', 'resource': 'unique_search_resource'
        })
        resp = self.client.get('/api/v1/audit/search?q=unique_search_resource')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] >= 1

    def test_search_missing_keyword(self):
        resp = self.client.get('/api/v1/audit/search')
        assert resp.status_code == 400

    def test_recent(self):
        resp = self.client.get('/api/v1/audit/recent?n=5')
        assert resp.status_code == 200
