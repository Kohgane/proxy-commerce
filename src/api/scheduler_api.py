"""src/api/scheduler_api.py — Phase 40: 스케줄러 REST API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

scheduler_bp = Blueprint('scheduler', __name__, url_prefix='/api/v1/scheduler')


@scheduler_bp.get('/status')
def scheduler_status():
    return jsonify({'status': 'ok', 'module': 'scheduler'})


@scheduler_bp.get('/jobs')
def list_jobs():
    """GET /api/v1/scheduler/jobs — 등록된 작업 목록."""
    from ..scheduler.job_scheduler import JobScheduler
    enabled_only = request.args.get('enabled_only', 'false').lower() == 'true'
    try:
        scheduler = JobScheduler()
        jobs = scheduler.list_all(enabled_only=enabled_only)
        # func 객체 제거 (직렬화 불가)
        safe_jobs = [{k: v for k, v in j.items() if k != 'func'} for j in jobs]
        return jsonify(safe_jobs)
    except Exception as exc:
        logger.error("오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@scheduler_bp.post('/jobs')
def register_job():
    """POST /api/v1/scheduler/jobs — 작업 등록."""
    from ..scheduler.job_scheduler import JobScheduler
    from ..scheduler.job_registry import JobRegistry
    body = request.get_json(silent=True) or {}
    name = body.get('name', '')
    schedule_type = body.get('schedule_type', 'interval_minutes')
    schedule_value = body.get('schedule_value', 60)
    if not name:
        return jsonify({'error': 'name is required'}), 400
    try:
        registry = JobRegistry()
        func = registry.get(name)
        if func is None:
            # 더미 함수로 등록
            def dummy_func():
                return f"Job {name} executed"
            func = dummy_func
        scheduler = JobScheduler()
        if schedule_type == 'interval_minutes':
            job = scheduler.every_minutes(name, func, int(schedule_value))
        elif schedule_type == 'interval_hours':
            job = scheduler.every_hours(name, func, int(schedule_value))
        elif schedule_type == 'daily':
            job = scheduler.daily_at(name, func, str(schedule_value))
        elif schedule_type == 'cron':
            job = scheduler.cron(name, func, str(schedule_value))
        else:
            return jsonify({'error': f'지원하지 않는 스케줄 타입: {schedule_type}'}), 400
        safe_job = {k: v for k, v in job.items() if k != 'func'}
        return jsonify(safe_job), 201
    except Exception as exc:
        logger.error("작업 등록 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@scheduler_bp.post('/jobs/<job_id>/pause')
def pause_job(job_id: str):
    """POST /api/v1/scheduler/jobs/<id>/pause — 작업 일시정지."""
    from ..scheduler.job_scheduler import JobScheduler
    try:
        scheduler = JobScheduler()
        job = scheduler.pause(job_id)
        if job is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify({k: v for k, v in job.items() if k != 'func'})
    except Exception as exc:
        logger.error("오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@scheduler_bp.post('/jobs/<job_id>/resume')
def resume_job(job_id: str):
    """POST /api/v1/scheduler/jobs/<id>/resume — 작업 재개."""
    from ..scheduler.job_scheduler import JobScheduler
    try:
        scheduler = JobScheduler()
        job = scheduler.resume(job_id)
        if job is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify({k: v for k, v in job.items() if k != 'func'})
    except Exception as exc:
        logger.error("오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@scheduler_bp.delete('/jobs/<job_id>')
def delete_job(job_id: str):
    """DELETE /api/v1/scheduler/jobs/<id> — 작업 삭제."""
    from ..scheduler.job_scheduler import JobScheduler
    try:
        scheduler = JobScheduler()
        ok = scheduler.delete(job_id)
        if not ok:
            return jsonify({'error': 'not found'}), 404
        return jsonify({'deleted': True})
    except Exception as exc:
        logger.error("오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@scheduler_bp.get('/registry')
def list_registry():
    """GET /api/v1/scheduler/registry — 등록된 작업 이름 목록."""
    from ..scheduler.job_registry import JobRegistry
    try:
        registry = JobRegistry()
        return jsonify({'jobs': registry.list_names()})
    except Exception as exc:
        logger.error("오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
