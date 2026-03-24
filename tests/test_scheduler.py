"""tests/test_scheduler.py — cron 스케줄러 테스트."""
import os
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestParseCronField:
    def test_wildcard(self):
        from src.automation.scheduler import _parse_cron_field
        assert _parse_cron_field('*', 5, 0, 59)
        assert _parse_cron_field('*', 0, 0, 59)

    def test_specific_value(self):
        from src.automation.scheduler import _parse_cron_field
        assert _parse_cron_field('30', 30, 0, 59)
        assert not _parse_cron_field('30', 29, 0, 59)

    def test_step(self):
        from src.automation.scheduler import _parse_cron_field
        assert _parse_cron_field('*/2', 4, 0, 59)
        assert not _parse_cron_field('*/2', 3, 0, 59)

    def test_comma_list(self):
        from src.automation.scheduler import _parse_cron_field
        assert _parse_cron_field('1,5,10', 5, 0, 59)
        assert not _parse_cron_field('1,5,10', 3, 0, 59)

    def test_range(self):
        from src.automation.scheduler import _parse_cron_field
        assert _parse_cron_field('9-17', 12, 0, 23)
        assert not _parse_cron_field('9-17', 20, 0, 23)


class TestParseCron:
    def test_all_wildcards(self):
        """모든 필드 * → 항상 True."""
        from src.automation.scheduler import parse_cron
        dt = datetime(2026, 3, 15, 10, 30)
        assert parse_cron('* * * * *', dt)

    def test_specific_minute(self):
        from src.automation.scheduler import parse_cron
        dt = datetime(2026, 3, 15, 10, 30)
        assert parse_cron('30 * * * *', dt)
        assert not parse_cron('0 * * * *', dt)

    def test_specific_hour(self):
        from src.automation.scheduler import parse_cron
        dt = datetime(2026, 3, 15, 9, 0)
        assert parse_cron('0 9 * * *', dt)
        assert not parse_cron('0 10 * * *', dt)

    def test_step_expression(self):
        from src.automation.scheduler import parse_cron
        dt = datetime(2026, 3, 15, 10, 30)
        assert parse_cron('*/30 */2 * * *', dt)

    def test_invalid_expr_returns_false(self):
        """잘못된 표현식은 False를 반환해야 한다."""
        from src.automation.scheduler import parse_cron
        assert not parse_cron('invalid')
        assert not parse_cron('* * *')


class TestScheduler:
    @pytest.fixture(autouse=True)
    def enable_scheduler(self, monkeypatch):
        monkeypatch.setenv('SCHEDULER_ENABLED', '1')
        import src.automation.scheduler as s
        s._ENABLED = True
        yield
        s._ENABLED = False

    def test_register_job(self):
        """작업 등록이 성공해야 한다."""
        from src.automation.scheduler import Scheduler
        scheduler = Scheduler()
        scheduler.register_job('test_job', '0 9 * * *', lambda: None)
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]['name'] == 'test_job'

    def test_register_duplicate_updates(self):
        """중복 이름 등록 시 업데이트되어야 한다."""
        from src.automation.scheduler import Scheduler
        scheduler = Scheduler()
        scheduler.register_job('job1', '0 9 * * *', lambda: None)
        scheduler.register_job('job1', '0 10 * * *', lambda: None)
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0]['schedule'] == '0 10 * * *'

    def test_get_due_jobs(self):
        """실행 예정 작업이 반환되어야 한다."""
        from src.automation.scheduler import Scheduler
        scheduler = Scheduler()
        dt = datetime(2026, 3, 15, 9, 0)
        scheduler.register_job('morning_job', '0 9 * * *', lambda: None)
        scheduler.register_job('noon_job', '0 12 * * *', lambda: None)
        due = scheduler.get_due_jobs(dt)
        assert len(due) == 1
        assert due[0]['name'] == 'morning_job'

    def test_run_due_jobs_executes(self):
        """실행 예정 작업이 실행되어야 한다."""
        from src.automation.scheduler import Scheduler
        scheduler = Scheduler()
        executed = []
        dt = datetime(2026, 3, 15, 9, 0)
        scheduler.register_job('test_job', '0 9 * * *', lambda: executed.append(True))

        with patch.object(scheduler, '_record_history'):
            results = scheduler.run_due_jobs(dt)

        assert len(executed) == 1
        assert results[0]['status'] == 'success'

    def test_run_due_jobs_handles_error(self):
        """작업 실패 시 error 상태를 반환해야 한다."""
        from src.automation.scheduler import Scheduler
        scheduler = Scheduler()
        dt = datetime(2026, 3, 15, 9, 0)

        def _failing_job():
            raise RuntimeError('test error')

        scheduler.register_job('fail_job', '0 9 * * *', _failing_job)

        with patch.object(scheduler, '_record_history'):
            results = scheduler.run_due_jobs(dt)

        assert results[0]['status'] == 'error'

    def test_unregister_job(self):
        """작업 제거가 성공해야 한다."""
        from src.automation.scheduler import Scheduler
        scheduler = Scheduler()
        scheduler.register_job('job1', '* * * * *', lambda: None)
        ok = scheduler.unregister_job('job1')
        assert ok
        assert scheduler.list_jobs() == []
