"""src/api/china_marketplace_api.py — 중국 마켓플레이스 API Blueprint (Phase 104).

Blueprint: /api/v1/china-marketplace

엔드포인트:
  POST /search                    — 상품 검색
  GET  /product/<path:url>        — 상품 상세 조회
  POST /orders                    — 구매 주문 생성
  GET  /orders                    — 주문 목록
  GET  /orders/<id>               — 주문 상세
  POST /orders/<id>/cancel        — 주문 취소
  GET  /orders/<id>/tracking      — 주문 추적
  POST /seller/verify             — 셀러 검증
  GET  /seller/<seller_id>        — 셀러 프로필
  GET  /sellers/blacklist         — 블랙리스트 조회
  POST /sellers/blacklist         — 블랙리스트 추가
  GET  /agents                    — 에이전트 목록
  POST /agents/<agent_id>/assign  — 에이전트 배정
  POST /rpa/task                  — RPA 작업 생성
  GET  /rpa/tasks                 — RPA 작업 목록
  GET  /dashboard                 — 대시보드 데이터
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

china_marketplace_bp = Blueprint(
    'china_marketplace',
    __name__,
    url_prefix='/api/v1/china-marketplace',
)

# ── 지연 초기화 ──────────────────────────────────────────────────────────────
_engine = None
_taobao_agent = None
_alibaba_agent = None
_agent_manager = None
_rpa_controller = None
_seller_service = None
_payment_service = None
_dashboard = None


def _get_engine():
    global _engine
    if _engine is None:
        from ..china_marketplace.engine import ChinaMarketplaceEngine
        _engine = ChinaMarketplaceEngine()
    return _engine


def _get_taobao():
    global _taobao_agent
    if _taobao_agent is None:
        from ..china_marketplace.taobao_agent import TaobaoAgent
        _taobao_agent = TaobaoAgent()
    return _taobao_agent


def _get_alibaba():
    global _alibaba_agent
    if _alibaba_agent is None:
        from ..china_marketplace.alibaba_agent import Alibaba1688Agent
        _alibaba_agent = Alibaba1688Agent()
    return _alibaba_agent


def _get_agent_manager():
    global _agent_manager
    if _agent_manager is None:
        from ..china_marketplace.agent_manager import AgentManager
        _agent_manager = AgentManager()
    return _agent_manager


def _get_rpa():
    global _rpa_controller
    if _rpa_controller is None:
        from ..china_marketplace.rpa_controller import RPAController
        _rpa_controller = RPAController()
    return _rpa_controller


def _get_seller_service():
    global _seller_service
    if _seller_service is None:
        from ..china_marketplace.seller_verification import SellerVerificationService
        _seller_service = SellerVerificationService()
    return _seller_service


def _get_payment():
    global _payment_service
    if _payment_service is None:
        from ..china_marketplace.payment import ChinaPaymentService
        _payment_service = ChinaPaymentService()
    return _payment_service


def _get_dashboard():
    global _dashboard
    if _dashboard is None:
        from ..china_marketplace.dashboard import ChinaPurchaseDashboard
        _dashboard = ChinaPurchaseDashboard(
            engine=_get_engine(),
            agent_manager=_get_agent_manager(),
            seller_service=_get_seller_service(),
            payment_service=_get_payment(),
            rpa_controller=_get_rpa(),
        )
    return _dashboard


# ── 상품 검색 ────────────────────────────────────────────────────────────────

@china_marketplace_bp.post('/search')
def search_product():
    """POST /search — 상품 검색."""
    data = request.get_json(silent=True) or {}
    keyword = data.get('keyword', '').strip()
    marketplace = data.get('marketplace', 'taobao')
    max_results = int(data.get('max_results', 10))

    if not keyword:
        return jsonify({'error': 'keyword 필드가 필요합니다.'}), 400

    if marketplace == 'taobao':
        products = _get_taobao().search(keyword, max_results=max_results)
        return jsonify({'marketplace': 'taobao', 'keyword': keyword, 'results': [p.to_dict() for p in products]})
    elif marketplace == '1688':
        products = _get_alibaba().search(keyword, max_results=max_results)
        return jsonify({'marketplace': '1688', 'keyword': keyword, 'results': [p.to_dict() for p in products]})
    else:
        return jsonify({'error': f'지원하지 않는 마켓플레이스: {marketplace}'}), 400


# ── 상품 상세 ────────────────────────────────────────────────────────────────

@china_marketplace_bp.get('/product/<path:url>')
def get_product(url: str):
    """GET /product/<url> — 상품 상세 조회."""
    marketplace = request.args.get('marketplace', 'taobao')
    if marketplace == 'taobao':
        product = _get_taobao().search_by_url(url)
    else:
        product = _get_alibaba().search_by_url(url)

    if not product:
        return jsonify({'error': '상품을 찾을 수 없습니다.'}), 404
    return jsonify(product.to_dict())


# ── 주문 ─────────────────────────────────────────────────────────────────────

@china_marketplace_bp.post('/orders')
def create_order():
    """POST /orders — 구매 주문 생성."""
    data = request.get_json(silent=True) or {}
    marketplace = data.get('marketplace', 'taobao')
    product_url = data.get('product_url', '').strip()
    quantity = int(data.get('quantity', 1))
    metadata = data.get('metadata', {})

    if not product_url:
        return jsonify({'error': 'product_url 필드가 필요합니다.'}), 400
    if marketplace not in ('taobao', '1688'):
        return jsonify({'error': f'지원하지 않는 마켓플레이스: {marketplace}'}), 400

    order = _get_engine().create_order(
        marketplace=marketplace,
        product_url=product_url,
        quantity=quantity,
        metadata=metadata,
    )

    # 에이전트 자동 배정
    agent_mgr = _get_agent_manager()
    category = data.get('category')
    agent = agent_mgr.assign_best_agent(order.order_id, marketplace, category)
    if agent:
        order = _get_engine().assign_agent(order.order_id, agent.agent_id)

    return jsonify(order.to_dict()), 201


@china_marketplace_bp.get('/orders')
def list_orders():
    """GET /orders — 주문 목록."""
    status_str = request.args.get('status')
    marketplace = request.args.get('marketplace')

    from ..china_marketplace.engine import ChinaPurchaseStatus
    status = None
    if status_str:
        try:
            status = ChinaPurchaseStatus(status_str)
        except ValueError:
            return jsonify({'error': f'유효하지 않은 상태: {status_str}'}), 400

    orders = _get_engine().list_orders(status=status, marketplace=marketplace)
    return jsonify({'orders': [o.to_dict() for o in orders], 'total': len(orders)})


@china_marketplace_bp.get('/orders/<order_id>')
def get_order(order_id: str):
    """GET /orders/<id> — 주문 상세."""
    order = _get_engine().get_order(order_id)
    if not order:
        return jsonify({'error': f'주문을 찾을 수 없습니다: {order_id}'}), 404
    return jsonify(order.to_dict())


@china_marketplace_bp.post('/orders/<order_id>/cancel')
def cancel_order(order_id: str):
    """POST /orders/<id>/cancel — 주문 취소."""
    data = request.get_json(silent=True) or {}
    reason = data.get('reason', '')
    try:
        order = _get_engine().cancel_order(order_id, reason)
        return jsonify(order.to_dict())
    except KeyError as exc:
        return jsonify({'error': str(exc)}), 404


@china_marketplace_bp.get('/orders/<order_id>/tracking')
def get_tracking(order_id: str):
    """GET /orders/<id>/tracking — 주문 추적."""
    order = _get_engine().get_order(order_id)
    if not order:
        return jsonify({'error': f'주문을 찾을 수 없습니다: {order_id}'}), 404

    if order.marketplace == 'taobao':
        tracking = _get_taobao().track_order(order_id)
    else:
        tracking = {'order_id': order_id, 'status': '처리중', 'carrier': '-'}

    return jsonify(tracking)


# ── 셀러 ─────────────────────────────────────────────────────────────────────

@china_marketplace_bp.post('/seller/verify')
def verify_seller():
    """POST /seller/verify — 셀러 검증."""
    data = request.get_json(silent=True) or {}
    seller_id = data.get('seller_id', '').strip()
    if not seller_id:
        return jsonify({'error': 'seller_id 필드가 필요합니다.'}), 400

    svc = _get_seller_service()
    # 프로필이 없으면 mock 등록
    if not svc.get_seller(seller_id):
        import random
        svc.register_seller(
            seller_id=seller_id,
            name=data.get('name', f'셀러 {seller_id}'),
            marketplace=data.get('marketplace', 'taobao'),
            rating=data.get('rating', round(random.uniform(3.5, 5.0), 1)),
            sales_count=data.get('sales_count', random.randint(100, 50000)),
            years_active=data.get('years_active', round(random.uniform(1, 10), 1)),
        )

    score = svc.verify_seller(seller_id)
    return jsonify(score.to_dict())


@china_marketplace_bp.get('/seller/<seller_id>')
def get_seller(seller_id: str):
    """GET /seller/<seller_id> — 셀러 프로필."""
    profile = _get_seller_service().get_seller(seller_id)
    if not profile:
        return jsonify({'error': f'셀러를 찾을 수 없습니다: {seller_id}'}), 404
    return jsonify(profile.to_dict())


@china_marketplace_bp.get('/sellers/blacklist')
def get_blacklist():
    """GET /sellers/blacklist — 블랙리스트 조회."""
    bl = _get_seller_service().get_blacklist()
    return jsonify({'blacklist': bl, 'total': len(bl)})


@china_marketplace_bp.post('/sellers/blacklist')
def add_to_blacklist():
    """POST /sellers/blacklist — 블랙리스트 추가."""
    data = request.get_json(silent=True) or {}
    seller_id = data.get('seller_id', '').strip()
    reason = data.get('reason', '')
    if not seller_id:
        return jsonify({'error': 'seller_id 필드가 필요합니다.'}), 400

    _get_seller_service().add_to_blacklist(seller_id, reason)
    return jsonify({'seller_id': seller_id, 'blacklisted': True, 'reason': reason})


# ── 에이전트 ─────────────────────────────────────────────────────────────────

@china_marketplace_bp.get('/agents')
def list_agents():
    """GET /agents — 에이전트 목록."""
    marketplace = request.args.get('marketplace')
    agents = _get_agent_manager().list_agents(marketplace=marketplace)
    return jsonify({'agents': [a.to_dict() for a in agents], 'total': len(agents)})


@china_marketplace_bp.post('/agents/<agent_id>/assign')
def assign_agent(agent_id: str):
    """POST /agents/<agent_id>/assign — 에이전트 배정."""
    data = request.get_json(silent=True) or {}
    order_id = data.get('order_id', '').strip()
    if not order_id:
        return jsonify({'error': 'order_id 필드가 필요합니다.'}), 400

    try:
        agent = _get_agent_manager().assign_agent(order_id, agent_id)
        return jsonify({'order_id': order_id, 'agent': agent.to_dict()})
    except KeyError as exc:
        return jsonify({'error': str(exc)}), 404


# ── RPA ──────────────────────────────────────────────────────────────────────

@china_marketplace_bp.post('/rpa/task')
def create_rpa_task():
    """POST /rpa/task — RPA 작업 생성 및 실행."""
    data = request.get_json(silent=True) or {}
    task_type_str = data.get('task_type', 'search_product')
    metadata = data.get('metadata', {})
    auto_execute = data.get('auto_execute', True)

    from ..china_marketplace.rpa_controller import RPATaskType
    try:
        task_type = RPATaskType(task_type_str)
    except ValueError:
        return jsonify({'error': f'유효하지 않은 작업 유형: {task_type_str}'}), 400

    rpa = _get_rpa()
    task = rpa.create_task(task_type, metadata)

    if auto_execute:
        task = rpa.execute_task(task.task_id)

    return jsonify(task.to_dict()), 201


@china_marketplace_bp.get('/rpa/tasks')
def list_rpa_tasks():
    """GET /rpa/tasks — RPA 작업 목록."""
    status_str = request.args.get('status')
    task_type_str = request.args.get('task_type')

    from ..china_marketplace.rpa_controller import RPATaskStatus, RPATaskType
    status = None
    task_type = None
    if status_str:
        try:
            status = RPATaskStatus(status_str)
        except ValueError:
            return jsonify({'error': f'유효하지 않은 상태: {status_str}'}), 400
    if task_type_str:
        try:
            task_type = RPATaskType(task_type_str)
        except ValueError:
            return jsonify({'error': f'유효하지 않은 작업 유형: {task_type_str}'}), 400

    tasks = _get_rpa().list_tasks(status=status, task_type=task_type)
    return jsonify({'tasks': [t.to_dict() for t in tasks], 'total': len(tasks)})


# ── 대시보드 ─────────────────────────────────────────────────────────────────

@china_marketplace_bp.get('/dashboard')
def get_dashboard():
    """GET /dashboard — 대시보드 데이터."""
    return jsonify(_get_dashboard().get_summary())
