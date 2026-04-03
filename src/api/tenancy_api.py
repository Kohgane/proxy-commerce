"""src/api/tenancy_api.py — Phase 49: 테넌시 REST API Blueprint."""
import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

tenancy_bp = Blueprint('tenancy', __name__, url_prefix='/api/v1/tenants')


@tenancy_bp.get('/status')
def tenancy_status():
    return jsonify({'status': 'ok', 'module': 'tenancy'})


@tenancy_bp.post('')
def create_tenant():
    from ..tenancy.tenant_manager import TenantManager
    body = request.get_json(silent=True) or {}
    name = body.get('name', '')
    if not name:
        return jsonify({'error': 'name required'}), 400
    try:
        mgr = TenantManager()
        tenant = mgr.create(name, plan=body.get('plan', 'free'), config=body.get('config'))
        return jsonify(tenant), 201
    except Exception as exc:
        logger.error("테넌트 생성 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@tenancy_bp.get('')
def list_tenants():
    from ..tenancy.tenant_manager import TenantManager
    try:
        mgr = TenantManager()
        return jsonify(mgr.list_tenants())
    except Exception as exc:
        logger.error("테넌트 목록 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@tenancy_bp.get('/<tenant_id>')
def get_tenant(tenant_id: str):
    from ..tenancy.tenant_manager import TenantManager
    try:
        mgr = TenantManager()
        tenant = mgr.get(tenant_id)
        if tenant is None:
            return jsonify({'error': 'not found'}), 404
        return jsonify(tenant)
    except Exception as exc:
        logger.error("테넌트 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@tenancy_bp.put('/<tenant_id>')
def update_tenant(tenant_id: str):
    from ..tenancy.tenant_manager import TenantManager
    body = request.get_json(silent=True) or {}
    try:
        mgr = TenantManager()
        tenant = mgr.update(tenant_id, **body)
        return jsonify(tenant)
    except KeyError:
        return jsonify({'error': 'not found'}), 404
    except Exception as exc:
        logger.error("테넌트 수정 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@tenancy_bp.delete('/<tenant_id>')
def deactivate_tenant(tenant_id: str):
    from ..tenancy.tenant_manager import TenantManager
    try:
        mgr = TenantManager()
        tenant = mgr.deactivate(tenant_id)
        return jsonify(tenant)
    except KeyError:
        return jsonify({'error': 'not found'}), 404
    except Exception as exc:
        logger.error("테넌트 비활성화 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@tenancy_bp.get('/<tenant_id>/config')
def get_tenant_config(tenant_id: str):
    from ..tenancy.tenant_config import TenantConfig
    try:
        cfg = TenantConfig()
        return jsonify(cfg.get_config(tenant_id))
    except Exception as exc:
        logger.error("테넌트 설정 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@tenancy_bp.put('/<tenant_id>/config')
def update_tenant_config(tenant_id: str):
    from ..tenancy.tenant_config import TenantConfig
    body = request.get_json(silent=True) or {}
    try:
        cfg = TenantConfig()
        return jsonify(cfg.set_config(tenant_id, **body))
    except Exception as exc:
        logger.error("테넌트 설정 수정 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@tenancy_bp.get('/<tenant_id>/usage')
def get_tenant_usage(tenant_id: str):
    from ..tenancy.usage_tracker import UsageTracker
    try:
        tracker = UsageTracker()
        return jsonify(tracker.get_usage(tenant_id))
    except Exception as exc:
        logger.error("테넌트 사용량 조회 오류: %s", exc)
        return jsonify({'error': 'Internal server error'}), 500


@tenancy_bp.get('/plans')
def list_plans():
    from ..tenancy.subscription_plan import PLANS
    return jsonify(PLANS)
