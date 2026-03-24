"""src/automation/scheduler.py — cron 기반 작업 스케줄러.

간단한 cron 표현식 파서(* */2 * * * 형태)와 작업 등록/실행 관리.
작업 실행 이력은 Google Sheets에 기록된다.

환경변수:
  SCHEDULER_ENABLED — 활성화 여부 (기본 "0")
  GOOGLE_SHEET_ID   — Google Sheets ID
"""

import logging
import os
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)

_ENABLED = os.getenv('SCHEDULER_ENABLED', '0') == '1'
_HISTORY_SHEET = 'scheduler_history'

HISTORY_HEADERS = ['job_name', 'scheduled_at', 'started_at', 'finished_at',
                   'status', 'detail']


def _parse_cron_field(field: str, current: int,
                      min_val: int, max_val: int) -> bool:
    """단일 cron 필드를 파싱하여 현재 값이 해당하는지 반환한다.

    지원 형식:
      *         — 모든 값
      */n       — n마다 (예: */2 = 2의 배수)
      n         — 특정 값
      n,m,...   — 복수 값
      n-m       — 범위
    """
    if field == '*':
        return True

    if ',' in field:
        return any(_parse_cron_field(f.strip(), current, min_val, max_val)
                   for f in field.split(','))

    if field.startswith('*/'):
        try:
            step = int(field[2:])
            return current % step == 0
        except ValueError:
            return False

    if '-' in field:
        parts = field.split('-', 1)
        try:
            return int(parts[0]) <= current <= int(parts[1])
        except (ValueError, IndexError):
            return False

    try:
        return int(field) == current
    except ValueError:
        return False


def parse_cron(expr: str, dt: datetime = None) -> bool:
    """cron 표현식을 평가한다 (5필드: min hour dom mon dow).

    Args:
        expr: cron 표현식 (예: "0 9 * * *", "*/30 * * * *")
        dt: 평가 기준 시각 (None이면 현재 UTC)

    Returns:
        현재 시각이 cron 표현식에 해당하면 True
    """
    if dt is None:
        dt = datetime.utcnow()

    parts = expr.strip().split()
    if len(parts) != 5:
        logger.warning("잘못된 cron 표현식: %s", expr)
        return False

    minute_f, hour_f, dom_f, month_f, dow_f = parts

    return (
        _parse_cron_field(minute_f, dt.minute, 0, 59)
        and _parse_cron_field(hour_f, dt.hour, 0, 23)
        and _parse_cron_field(dom_f, dt.day, 1, 31)
        and _parse_cron_field(month_f, dt.month, 1, 12)
        and _parse_cron_field(dow_f, dt.weekday(), 0, 6)
    )


class Scheduler:
    """작업 스케줄러 — cron 기반 작업 등록 및 실행."""

    def __init__(self):
        self._jobs: list = []  # [{name, schedule, func, args}]
        self._history_sheet = None

    def _get_history_sheet(self):
        if self._history_sheet is None:
            from ..utils.sheets import open_sheet
            sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
            self._history_sheet = open_sheet(sheet_id, _HISTORY_SHEET)
            self._ensure_headers()
        return self._history_sheet

    def _ensure_headers(self):
        ws = self._history_sheet
        rows = ws.get_all_values()
        if not rows or rows[0] != HISTORY_HEADERS:
            ws.clear()
            ws.append_row(HISTORY_HEADERS)

    def _record_history(self, name: str, scheduled_at: str,
                        started_at: str, finished_at: str,
                        status: str, detail: str = ''):
        try:
            ws = self._get_history_sheet()
            ws.append_row([name, scheduled_at, started_at, finished_at,
                           status, detail[:500]])
        except Exception as exc:
            logger.warning("이력 기록 실패: %s", exc)

    def register_job(self, name: str, schedule: str,
                     func, args: tuple = ()) -> bool:
        """작업을 등록한다.

        Args:
            name: 작업 이름
            schedule: cron 표현식 (5필드)
            func: 실행할 함수
            args: 함수 인자 튜플

        Returns:
            등록 성공 여부
        """
        # 중복 이름 체크
        for job in self._jobs:
            if job['name'] == name:
                job.update({'schedule': schedule, 'func': func, 'args': args})
                return True

        self._jobs.append({
            'name': name,
            'schedule': schedule,
            'func': func,
            'args': args,
        })
        logger.info("스케줄러 작업 등록: %s (%s)", name, schedule)
        return True

    def unregister_job(self, name: str) -> bool:
        """작업을 제거한다."""
        before = len(self._jobs)
        self._jobs = [j for j in self._jobs if j['name'] != name]
        return len(self._jobs) < before

    def get_due_jobs(self, dt: datetime = None) -> list:
        """현재 시각에 실행 예정인 작업 리스트를 반환한다."""
        if not _ENABLED:
            return []
        if dt is None:
            dt = datetime.utcnow()
        return [j for j in self._jobs if parse_cron(j['schedule'], dt)]

    def run_due_jobs(self, dt: datetime = None) -> list:
        """실행 예정 작업을 모두 실행하고 결과를 반환한다."""
        if not _ENABLED:
            return []

        due_jobs = self.get_due_jobs(dt)
        results = []
        scheduled_at = (dt or datetime.utcnow()).isoformat()

        for job in due_jobs:
            started_at = datetime.utcnow().isoformat()
            try:
                job['func'](*job['args'])
                finished_at = datetime.utcnow().isoformat()
                status = 'success'
                detail = ''
                logger.info("작업 완료: %s", job['name'])
            except Exception as exc:
                finished_at = datetime.utcnow().isoformat()
                status = 'error'
                detail = traceback.format_exc()[-500:]
                logger.error("작업 실패 (%s): %s", job['name'], exc)

            self._record_history(job['name'], scheduled_at,
                                 started_at, finished_at, status, detail)
            results.append({
                'name': job['name'],
                'status': status,
                'started_at': started_at,
                'finished_at': finished_at,
            })

        return results

    def list_jobs(self) -> list:
        """등록된 작업 목록을 반환한다."""
        return [{'name': j['name'], 'schedule': j['schedule']} for j in self._jobs]

    def get_history(self, limit: int = 50) -> list:
        """실행 이력을 반환한다."""
        try:
            ws = self._get_history_sheet()
            records = ws.get_all_records()
            return records[-limit:]
        except Exception as exc:
            logger.warning("이력 조회 실패: %s", exc)
            return []
