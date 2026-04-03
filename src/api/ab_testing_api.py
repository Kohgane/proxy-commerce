"""src/api/ab_testing_api.py — Phase 50: A/B 테스트 API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

ab_testing_bp = Blueprint('ab_testing', __name__, url_prefix='/api/v1/experiments')


@ab_testing_bp.get('/status')
def ab_testing_status():
    return jsonify({'status': 'ok', 'module': 'ab_testing'})


@ab_testing_bp.post('')
def create_experiment():
    from ..ab_testing.experiment_manager import ExperimentManager
    body = request.get_json(silent=True) or {}
    name = body.get('name', '')
    variants = body.get('variants', [])
    if not name or not variants:
        return jsonify({'error': 'name and variants required'}), 400
    try:
        mgr = ExperimentManager()
        exp = mgr.create(name, variants)
        return jsonify(exp), 201
    except Exception as exc:
        logger.error("실험 생성 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@ab_testing_bp.get('')
def list_experiments():
    from ..ab_testing.experiment_manager import ExperimentManager
    try:
        mgr = ExperimentManager()
        return jsonify(mgr.list_experiments())
    except Exception as exc:
        logger.error("실험 목록 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@ab_testing_bp.get('/<experiment_id>')
def get_experiment(experiment_id: str):
    from ..ab_testing.experiment_manager import ExperimentManager
    try:
        mgr = ExperimentManager()
        exp = mgr.get(experiment_id)
        if exp is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(exp)
    except Exception as exc:
        logger.error("실험 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@ab_testing_bp.post('/<experiment_id>/start')
def start_experiment(experiment_id: str):
    from ..ab_testing.experiment_manager import ExperimentManager
    try:
        mgr = ExperimentManager()
        exp = mgr.start(experiment_id)
        return jsonify(exp)
    except KeyError:
        return jsonify({'error': 'not found'}), 404
    except Exception as exc:
        logger.error("실험 시작 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@ab_testing_bp.post('/<experiment_id>/stop')
def stop_experiment(experiment_id: str):
    from ..ab_testing.experiment_manager import ExperimentManager
    try:
        mgr = ExperimentManager()
        exp = mgr.stop(experiment_id)
        return jsonify(exp)
    except KeyError:
        return jsonify({'error': 'not found'}), 404
    except Exception as exc:
        logger.error("실험 중지 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@ab_testing_bp.post('/<experiment_id>/assign')
def assign_variant(experiment_id: str):
    from ..ab_testing.experiment_manager import ExperimentManager
    from ..ab_testing.variant_assigner import VariantAssigner
    body = request.get_json(silent=True) or {}
    user_id = body.get('user_id', '')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    try:
        mgr = ExperimentManager()
        exp = mgr.get(experiment_id)
        if exp is None:
            return jsonify({'error': 'not found'}), 404
        assigner = VariantAssigner()
        variant = assigner.assign(experiment_id, user_id, exp.get('variants', []))
        return jsonify({'experiment_id': experiment_id, 'user_id': user_id, 'variant': variant})
    except Exception as exc:
        logger.error("변형 할당 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@ab_testing_bp.post('/<experiment_id>/track')
def track_event(experiment_id: str):
    from ..ab_testing.metrics_tracker import MetricsTracker
    body = request.get_json(silent=True) or {}
    variant = body.get('variant', '')
    event_type = body.get('event_type', '')
    if not variant or not event_type:
        return jsonify({'error': 'variant and event_type required'}), 400
    try:
        tracker = MetricsTracker()
        tracker.track_event(experiment_id, variant, event_type, body.get('value', 1))
        return jsonify({'status': 'tracked'})
    except Exception as exc:
        logger.error("이벤트 추적 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@ab_testing_bp.get('/<experiment_id>/report')
def get_report(experiment_id: str):
    from ..ab_testing.experiment_report import ExperimentReport
    try:
        report = ExperimentReport()
        return jsonify(report.generate(experiment_id))
    except Exception as exc:
        logger.error("보고서 생성 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500
