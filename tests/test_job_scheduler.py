"""tests/test_job_scheduler.py — Phase 40: 작업 스케줄러 테스트."""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock


class TestJobScheduler:
    def setup_method(self):
        from src.scheduler.job_scheduler import JobScheduler
        self.scheduler = JobScheduler()

    def _dummy(self):
        return 'ok'

    def test_every_minutes(self):
        job = self.scheduler.every_minutes('test_job', self._dummy, 5)
        assert job['name'] == 'test_job'
        assert job['schedule_type'] == 'interval_minutes'
        assert job['schedule_value'] == 5

    def test_every_hours(self):
        job = self.scheduler.every_hours('hourly_job', self._dummy, 2)
        assert job['schedule_type'] == 'interval_hours'

    def test_daily_at(self):
        job = self.scheduler.daily_at('daily_job', self._dummy, '09:00')
        assert job['schedule_type'] == 'daily'
        assert job['schedule_value'] == '09:00'

    def test_cron(self):
        job = self.scheduler.cron('cron_job', self._dummy, '0 9 * * *')
        assert job['schedule_type'] == 'cron'

    def test_list_all(self):
        self.scheduler.every_minutes('j1', self._dummy, 5)
        self.scheduler.every_minutes('j2', self._dummy, 10)
        assert len(self.scheduler.list_all()) == 2

    def test_list_enabled_only(self):
        job = self.scheduler.every_minutes('j1', self._dummy, 5)
        self.scheduler.pause(job['id'])
        self.scheduler.every_minutes('j2', self._dummy, 10)
        enabled = self.scheduler.list_all(enabled_only=True)
        assert len(enabled) == 1

    def test_pause_resume(self):
        job = self.scheduler.every_minutes('pausable', self._dummy, 5)
        paused = self.scheduler.pause(job['id'])
        assert paused['status'] == 'paused'
        resumed = self.scheduler.resume(job['id'])
        assert resumed['status'] == 'active'

    def test_delete(self):
        job = self.scheduler.every_minutes('deletable', self._dummy, 5)
        ok = self.scheduler.delete(job['id'])
        assert ok is True
        assert self.scheduler.get(job['id']) is None

    def test_run_job(self):
        job = self.scheduler.every_minutes('runnable', lambda: 'result', 5)
        result = self.scheduler.run_job(job['id'])
        assert result['status'] == 'success'
        assert result['result'] == 'result'

    def test_run_job_failure(self):
        def failing():
            raise RuntimeError('test error')
        job = self.scheduler.every_minutes('failing_job', failing, 5)
        result = self.scheduler.run_job(job['id'])
        assert result['status'] == 'failed'
        assert 'test error' in result['error']

    def test_run_nonexistent_job(self):
        with pytest.raises(ValueError):
            self.scheduler.run_job('nonexistent')

    def test_get_by_name(self):
        self.scheduler.every_minutes('findable', self._dummy, 5)
        job = self.scheduler.get_by_name('findable')
        assert job is not None
        assert job['name'] == 'findable'

    def test_should_run_daily_at(self):
        job = self.scheduler.daily_at('daily', self._dummy, '10:30')
        dt = datetime(2024, 1, 1, 10, 30, tzinfo=timezone.utc)
        assert self.scheduler.should_run(job['id'], now=dt) is True

    def test_should_run_daily_at_wrong_time(self):
        job = self.scheduler.daily_at('daily2', self._dummy, '10:30')
        dt = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)
        assert self.scheduler.should_run(job['id'], now=dt) is False

    def test_should_run_interval_no_last_run(self):
        job = self.scheduler.every_minutes('interval', self._dummy, 5)
        assert self.scheduler.should_run(job['id']) is True

    def test_should_run_interval_too_soon(self):
        job = self.scheduler.every_minutes('interval2', self._dummy, 60)
        self.scheduler.run_job(job['id'])
        assert self.scheduler.should_run(job['id']) is False

    def test_should_run_cron(self):
        job = self.scheduler.cron('cron', self._dummy, '30 10 * * *')
        dt = datetime(2024, 1, 1, 10, 30, tzinfo=timezone.utc)
        assert self.scheduler.should_run(job['id'], now=dt) is True

    def test_should_run_paused_job(self):
        job = self.scheduler.every_minutes('paused_check', self._dummy, 0)
        self.scheduler.pause(job['id'])
        assert self.scheduler.should_run(job['id']) is False


class TestJobRegistry:
    def test_register_and_get(self):
        from src.scheduler.job_registry import JobRegistry
        registry = JobRegistry(use_global=False)
        registry.register('my_job', lambda: 'hello')
        func = registry.get('my_job')
        assert func is not None
        assert func() == 'hello'

    def test_list_names(self):
        from src.scheduler.job_registry import JobRegistry
        registry = JobRegistry(use_global=False)
        registry.register('job_a', lambda: None)
        registry.register('job_b', lambda: None)
        names = registry.list_names()
        assert 'job_a' in names
        assert 'job_b' in names

    def test_unregister(self):
        from src.scheduler.job_registry import JobRegistry
        registry = JobRegistry(use_global=False)
        registry.register('temp_job', lambda: None)
        ok = registry.unregister('temp_job')
        assert ok is True
        assert registry.get('temp_job') is None

    def test_decorator(self):
        from src.scheduler.job_registry import register_job, JobRegistry
        @register_job(name='decorated_job_test')
        def my_job():
            return 'decorated'
        registry = JobRegistry(use_global=True)
        func = registry.get('decorated_job_test')
        assert func is not None

    def test_contains(self):
        from src.scheduler.job_registry import JobRegistry
        registry = JobRegistry(use_global=False)
        registry.register('check_me', lambda: None)
        assert 'check_me' in registry
        assert 'not_there' not in registry


class TestJobHistory:
    def setup_method(self):
        from src.scheduler.job_history import JobHistory
        self.history = JobHistory(max_records=100)

    def test_record_success(self):
        record = self.history.record('J001', 'my_job', 'success', '2024-01-01T00:00:00+00:00')
        assert record['status'] == 'success'
        assert record['job_id'] == 'J001'

    def test_get_recent(self):
        for i in range(5):
            self.history.record(f'J{i:03d}', f'job_{i}', 'success', f'2024-01-0{i + 1}T00:00:00+00:00')
        recent = self.history.get_recent(n=3)
        assert len(recent) == 3

    def test_get_by_name(self):
        self.history.record('J001', 'target_job', 'success', '2024-01-01T00:00:00+00:00')
        self.history.record('J002', 'other_job', 'success', '2024-01-01T00:00:00+00:00')
        records = self.history.get_by_name('target_job')
        assert len(records) == 1

    def test_get_stats(self):
        self.history.record('J001', 'job', 'success', '2024-01-01T00:00:00+00:00')
        self.history.record('J001', 'job', 'failed', '2024-01-01T01:00:00+00:00')
        stats = self.history.get_stats('J001')
        assert stats['total'] == 2
        assert stats['success'] == 1
        assert stats['failed'] == 1

    def test_max_records_trim(self):
        history = __import__('src.scheduler.job_history', fromlist=['JobHistory']).JobHistory(max_records=3)
        for i in range(5):
            history.record(f'J{i}', f'job_{i}', 'success', '2024-01-01T00:00:00+00:00')
        assert history.count() == 3

    def test_clear(self):
        self.history.record('J001', 'job', 'success', '2024-01-01T00:00:00+00:00')
        count = self.history.clear()
        assert count == 1
        assert self.history.count() == 0


class TestRetryPolicy:
    def test_execute_success(self):
        from src.scheduler.retry_policy import RetryPolicy
        policy = RetryPolicy(max_retries=3)
        result = policy.execute(lambda: 'ok')
        assert result == 'ok'

    def test_execute_retries_then_succeeds(self):
        from src.scheduler.retry_policy import RetryPolicy
        call_count = [0]

        def flaky():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("not yet")
            return 'success'

        policy = RetryPolicy(max_retries=3, base_delay=0.001)
        result = policy.execute(flaky, sleep_fn=lambda x: None)
        assert result == 'success'
        assert call_count[0] == 3

    def test_execute_exhausts_retries(self):
        from src.scheduler.retry_policy import RetryPolicy
        policy = RetryPolicy(max_retries=2, base_delay=0.001)

        def always_fails():
            raise ValueError("always")

        with pytest.raises(ValueError):
            policy.execute(always_fails, sleep_fn=lambda x: None)

    def test_get_delay_backoff(self):
        from src.scheduler.retry_policy import RetryPolicy
        policy = RetryPolicy(max_retries=3, base_delay=1.0, backoff_factor=2.0)
        assert policy.get_delay(0) == 1.0
        assert policy.get_delay(1) == 2.0
        assert policy.get_delay(2) == 4.0

    def test_max_delay_cap(self):
        from src.scheduler.retry_policy import RetryPolicy
        policy = RetryPolicy(max_retries=5, base_delay=10.0, backoff_factor=10.0, max_delay=30.0)
        assert policy.get_delay(3) == 30.0


class TestSchedulerAPI:
    def setup_method(self):
        from flask import Flask
        from src.api.scheduler_api import scheduler_bp
        app = Flask(__name__)
        app.register_blueprint(scheduler_bp)
        self.client = app.test_client()

    def test_status(self):
        resp = self.client.get('/api/v1/scheduler/status')
        assert resp.status_code == 200

    def test_list_jobs_empty(self):
        resp = self.client.get('/api/v1/scheduler/jobs')
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_register_job(self):
        resp = self.client.post('/api/v1/scheduler/jobs', json={
            'name': 'test_api_job',
            'schedule_type': 'interval_minutes',
            'schedule_value': 30,
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'test_api_job'

    def test_registry_list(self):
        resp = self.client.get('/api/v1/scheduler/registry')
        assert resp.status_code == 200
        assert 'jobs' in resp.get_json()
