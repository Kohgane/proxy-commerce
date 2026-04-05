"""src/api/vendor_api.py — 멀티벤더 마켓플레이스 API Blueprint (Phase 98).

Blueprint: /api/v1/vendors

엔드포인트:
  POST /apply                              — 판매자 신청
  GET  /                                   — 판매자 목록 (관리자)
  GET  /<vendor_id>                        — 판매자 상세
  PUT  /<vendor_id>                        — 판매자 정보 수정
  POST /<vendor_id>/approve                — 판매자 승인
  POST /<vendor_id>/reject                 — 판매자 거절
  POST /<vendor_id>/suspend                — 판매자 정지
  GET  /<vendor_id>/products               — 판매자 상품 목록
  POST /<vendor_id>/products               — 판매자 상품 등록
  POST /<vendor_id>/products/<product_id>/approve — 상품 승인
  GET  /<vendor_id>/settlements            — 정산 내역
  POST /<vendor_id>/settlements/generate   — 정산 생성
  GET  /<vendor_id>/dashboard              — 판매자 대시보드
  GET  /<vendor_id>/analytics              — 판매자 분석
  GET  /ranking                            — 판매자 랭킹
  GET  /commission-rules                   — 수수료 정책 조회
  POST /commission-rules                   — 수수료 정책 등록
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

vendor_bp = Blueprint('vendor', __name__, url_prefix='/api/v1/vendors')

# ── 지연 초기화 싱글턴 ────────────────────────────────────────────────────

_onboarding = None
_profile_mgr = None
_product_mgr = None
_settlement_mgr = None
_payout_svc = None
_commission_calc = None
_fee_mgr = None
_admin_mgr = None
_compliance = None
_notification_svc = None
_dashboard = None
_analytics = None
_scoring = None
_ranking = None


def _get_services():
    global _onboarding, _profile_mgr, _product_mgr, _settlement_mgr, _payout_svc
    global _commission_calc, _fee_mgr, _admin_mgr, _compliance, _notification_svc
    global _dashboard, _analytics, _scoring, _ranking
    if _onboarding is None:
        from ..vendor_marketplace.vendor_manager import (
            VendorOnboardingManager, VendorProfileManager,
        )
        from ..vendor_marketplace.vendor_products import VendorProductManager
        from ..vendor_marketplace.commission import CommissionCalculator
        from ..vendor_marketplace.settlement import SettlementManager, PayoutService
        from ..vendor_marketplace.vendor_admin import (
            VendorAdminManager, PlatformFeeManager, VendorComplianceChecker,
        )
        from ..vendor_marketplace.vendor_notifications import VendorNotificationService
        from ..vendor_marketplace.vendor_analytics import (
            VendorDashboard, VendorAnalytics, VendorScoring, VendorRanking,
        )

        _onboarding = VendorOnboardingManager()
        _profile_mgr = VendorProfileManager()
        _commission_calc = CommissionCalculator()
        _product_mgr = VendorProductManager()
        _settlement_mgr = SettlementManager(calculator=_commission_calc)
        _payout_svc = PayoutService()
        _fee_mgr = PlatformFeeManager(calculator=_commission_calc)
        _admin_mgr = VendorAdminManager(onboarding_manager=_onboarding)
        _compliance = VendorComplianceChecker(onboarding_manager=_onboarding)
        _notification_svc = VendorNotificationService()
        _dashboard = VendorDashboard()
        _analytics = VendorAnalytics()
        _scoring = VendorScoring()
        _ranking = VendorRanking()

    return (
        _onboarding, _profile_mgr, _product_mgr, _settlement_mgr, _payout_svc,
        _commission_calc, _fee_mgr, _admin_mgr, _compliance, _notification_svc,
        _dashboard, _analytics, _scoring, _ranking,
    )


# ---------------------------------------------------------------------------
# POST /apply — 판매자 신청
# ---------------------------------------------------------------------------

@vendor_bp.post('/apply')
def apply_vendor():
    """POST /api/v1/vendors/apply — 판매자 신청."""
    body = request.get_json(silent=True) or {}
    required = ['name', 'email', 'phone', 'business_number']
    missing = [f for f in required if not body.get(f)]
    if missing:
        return jsonify({'error': f'필수 필드 누락: {missing}'}), 400

    try:
        onboarding, *_ = _get_services()
        vendor = onboarding.apply(
            name=body['name'],
            email=body['email'],
            phone=body['phone'],
            business_number=body['business_number'],
            tier=body.get('tier', 'basic'),
            metadata=body.get('metadata', {}),
        )
        return jsonify(vendor.to_dict()), 201
    except ValueError as exc:
        logger.warning('판매자 신청 검증 오류: %s', exc)
        return jsonify({'error': '입력값이 유효하지 않습니다.'}), 422
    except Exception as exc:
        logger.error('판매자 신청 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET / — 판매자 목록
# ---------------------------------------------------------------------------

@vendor_bp.get('/')
def list_vendors():
    """GET /api/v1/vendors — 판매자 목록 (관리자)."""
    status = request.args.get('status')
    tier = request.args.get('tier')
    keyword = request.args.get('q')
    try:
        *_, admin_mgr, _c, _n, _d, _a, _s, _r = _get_services()
        vendors = admin_mgr.list_vendors(status=status, tier=tier, keyword=keyword)
        return jsonify({'vendors': vendors, 'total': len(vendors)})
    except Exception as exc:
        logger.error('판매자 목록 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /ranking — 판매자 랭킹
# ---------------------------------------------------------------------------

@vendor_bp.get('/ranking')
def vendor_ranking():
    """GET /api/v1/vendors/ranking — 판매자 랭킹."""
    try:
        services = _get_services()
        ranking_svc = services[-1]  # _ranking
        body = request.get_json(silent=True) or {}
        vendor_stats = body.get('vendor_stats', [])
        leaderboard = ranking_svc.build_leaderboard(vendor_stats)
        return jsonify({'ranking': leaderboard, 'count': len(leaderboard)})
    except Exception as exc:
        logger.error('랭킹 조회 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /commission-rules — 수수료 정책 조회
# POST /commission-rules — 수수료 정책 등록
# ---------------------------------------------------------------------------

@vendor_bp.get('/commission-rules')
def list_commission_rules():
    """GET /api/v1/vendors/commission-rules — 수수료 정책 조회."""
    try:
        services = _get_services()
        fee_mgr = services[6]  # _fee_mgr
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        rules = fee_mgr.list_rules(active_only=active_only)
        return jsonify({'rules': rules, 'total': len(rules)})
    except Exception as exc:
        logger.error('수수료 규칙 조회 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


@vendor_bp.post('/commission-rules')
def create_commission_rule():
    """POST /api/v1/vendors/commission-rules — 수수료 정책 등록."""
    body = request.get_json(silent=True) or {}
    if not body.get('vendor_tier') or body.get('rate') is None:
        return jsonify({'error': 'vendor_tier, rate 필수'}), 400
    try:
        services = _get_services()
        fee_mgr = services[6]  # _fee_mgr
        rule = fee_mgr.create_rule(
            vendor_tier=body['vendor_tier'],
            rate=float(body['rate']),
            category=body.get('category', ''),
            min_amount=float(body.get('min_amount', 0)),
            max_amount=float(body.get('max_amount', float('inf'))),
        )
        return jsonify(rule.to_dict()), 201
    except Exception as exc:
        logger.error('수수료 규칙 생성 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /<vendor_id> — 판매자 상세
# PUT /<vendor_id> — 판매자 정보 수정
# ---------------------------------------------------------------------------

@vendor_bp.get('/<vendor_id>')
def get_vendor(vendor_id: str):
    """GET /api/v1/vendors/<vendor_id> — 판매자 상세."""
    try:
        onboarding, profile_mgr, *_ = _get_services()
        vendor = onboarding.get_vendor(vendor_id)
        if vendor is None:
            return jsonify({'error': '판매자 없음'}), 404
        result = vendor.to_dict()
        profile = profile_mgr.get(vendor_id)
        if profile:
            result['profile'] = profile.to_dict()
        return jsonify(result)
    except Exception as exc:
        logger.error('판매자 조회 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


@vendor_bp.put('/<vendor_id>')
def update_vendor(vendor_id: str):
    """PUT /api/v1/vendors/<vendor_id> — 판매자 정보 수정."""
    body = request.get_json(silent=True) or {}
    try:
        onboarding, profile_mgr, *_ = _get_services()
        vendor = onboarding.get_vendor(vendor_id)
        if vendor is None:
            return jsonify({'error': '판매자 없음'}), 404
        # 기본 필드 업데이트
        for field in ('name', 'email', 'phone'):
            if field in body:
                setattr(vendor, field, body[field])
                vendor.touch()
        # 프로필 업데이트
        profile_fields = {
            k: v for k, v in body.items()
            if k in ('brand_name', 'logo_url', 'description', 'shipping_policy',
                     'return_policy', 'cs_email', 'cs_phone', 'bank_name',
                     'bank_account', 'bank_holder', 'address')
        }
        if profile_fields:
            profile_mgr.create_or_update(vendor_id, **profile_fields)

        return jsonify(vendor.to_dict())
    except Exception as exc:
        logger.error('판매자 수정 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# POST /<vendor_id>/approve — 판매자 승인
# POST /<vendor_id>/reject  — 판매자 거절
# POST /<vendor_id>/suspend — 판매자 정지
# ---------------------------------------------------------------------------

@vendor_bp.post('/<vendor_id>/approve')
def approve_vendor(vendor_id: str):
    """POST /api/v1/vendors/<vendor_id>/approve — 판매자 승인."""
    body = request.get_json(silent=True) or {}
    try:
        onboarding, *_ = _get_services()
        vendor = onboarding.approve(vendor_id, reason=body.get('reason', ''))
        notif_svc = _get_services()[9]
        notif_svc.notify_approval(vendor_id, vendor.name)
        return jsonify(vendor.to_dict())
    except (KeyError, ValueError) as exc:
        logger.warning('판매자 승인 오류: %s', exc)
        return jsonify({'error': '요청을 처리할 수 없습니다.'}), 422
    except Exception as exc:
        logger.error('판매자 승인 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


@vendor_bp.post('/<vendor_id>/reject')
def reject_vendor(vendor_id: str):
    """POST /api/v1/vendors/<vendor_id>/reject — 판매자 거절."""
    body = request.get_json(silent=True) or {}
    try:
        onboarding, *_ = _get_services()
        vendor = onboarding.reject(vendor_id, reason=body.get('reason', ''))
        notif_svc = _get_services()[9]
        notif_svc.notify_rejection(vendor_id, vendor.name, body.get('reason', ''))
        return jsonify(vendor.to_dict())
    except (KeyError, ValueError) as exc:
        logger.warning('판매자 거절 오류: %s', exc)
        return jsonify({'error': '요청을 처리할 수 없습니다.'}), 422
    except Exception as exc:
        logger.error('판매자 거절 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


@vendor_bp.post('/<vendor_id>/suspend')
def suspend_vendor(vendor_id: str):
    """POST /api/v1/vendors/<vendor_id>/suspend — 판매자 정지."""
    body = request.get_json(silent=True) or {}
    try:
        services = _get_services()
        onboarding = services[0]
        vendor = onboarding.suspend(vendor_id, reason=body.get('reason', ''))
        notif_svc = services[9]
        notif_svc.notify_suspension(vendor_id, vendor.name, body.get('reason', ''))
        return jsonify(vendor.to_dict())
    except (KeyError, ValueError) as exc:
        logger.warning('판매자 정지 오류: %s', exc)
        return jsonify({'error': '요청을 처리할 수 없습니다.'}), 422
    except Exception as exc:
        logger.error('판매자 정지 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET  /<vendor_id>/products               — 판매자 상품 목록
# POST /<vendor_id>/products               — 판매자 상품 등록
# POST /<vendor_id>/products/<product_id>/approve — 상품 승인
# ---------------------------------------------------------------------------

@vendor_bp.get('/<vendor_id>/products')
def list_vendor_products(vendor_id: str):
    """GET /api/v1/vendors/<vendor_id>/products — 판매자 상품 목록."""
    status = request.args.get('status')
    try:
        services = _get_services()
        product_mgr = services[2]
        products = product_mgr.list_vendor_products(vendor_id, status=status)
        return jsonify({'products': products, 'total': len(products)})
    except Exception as exc:
        logger.error('상품 목록 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


@vendor_bp.post('/<vendor_id>/products')
def add_vendor_product(vendor_id: str):
    """POST /api/v1/vendors/<vendor_id>/products — 판매자 상품 등록."""
    body = request.get_json(silent=True) or {}
    if not body.get('name') or body.get('price') is None:
        return jsonify({'error': 'name, price 필수'}), 400
    try:
        services = _get_services()
        onboarding = services[0]
        product_mgr = services[2]

        vendor = onboarding.get_vendor(vendor_id)
        if vendor is None:
            return jsonify({'error': '판매자 없음'}), 404

        product = product_mgr.add_product(
            vendor_id=vendor_id,
            vendor_tier=vendor.tier.value,
            name=body['name'],
            price=float(body['price']),
            category=body.get('category', 'other'),
            description=body.get('description', ''),
            images=body.get('images', []),
            stock=int(body.get('stock', 0)),
            metadata=body.get('metadata', {}),
        )
        return jsonify(product), 201
    except PermissionError as exc:
        logger.warning('상품 등록 권한 오류: %s', exc)
        return jsonify({'error': '상품 등록 한도를 초과했습니다. 티어 업그레이드가 필요합니다.'}), 403
    except Exception as exc:
        logger.error('상품 등록 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


@vendor_bp.post('/<vendor_id>/products/<product_id>/approve')
def approve_vendor_product(vendor_id: str, product_id: str):
    """POST /api/v1/vendors/<vendor_id>/products/<product_id>/approve — 상품 승인."""
    try:
        services = _get_services()
        product_mgr = services[2]
        notif_svc = services[9]
        onboarding = services[0]

        # 심사 제출 먼저
        product = product_mgr.get_product(product_id)
        if product is None:
            return jsonify({'error': '상품 없음'}), 404
        if product['status'] == 'draft':
            product_mgr.submit_for_review(vendor_id, product_id)

        result = product_mgr.approve_product(product_id)
        vendor = onboarding.get_vendor(vendor_id)
        if vendor:
            if result['status'] == 'listed':
                notif_svc.notify_product_approved(vendor_id, vendor.name, result['name'])
            else:
                notif_svc.notify_product_rejected(
                    vendor_id, vendor.name, result['name'],
                    '; '.join(result.get('approval_issues', []))
                )
        return jsonify(result)
    except (KeyError, ValueError) as exc:
        logger.warning('상품 승인 오류: %s', exc)
        return jsonify({'error': '요청을 처리할 수 없습니다.'}), 422
    except Exception as exc:
        logger.error('상품 승인 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET  /<vendor_id>/settlements            — 정산 내역
# POST /<vendor_id>/settlements/generate   — 정산 생성
# ---------------------------------------------------------------------------

@vendor_bp.get('/<vendor_id>/settlements')
def list_settlements(vendor_id: str):
    """GET /api/v1/vendors/<vendor_id>/settlements — 정산 내역."""
    status = request.args.get('status')
    try:
        services = _get_services()
        settlement_mgr = services[3]
        settlements = settlement_mgr.list_vendor_settlements(vendor_id, status=status)
        return jsonify({
            'settlements': [s.to_dict() for s in settlements],
            'total': len(settlements),
        })
    except Exception as exc:
        logger.error('정산 목록 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


@vendor_bp.post('/<vendor_id>/settlements/generate')
def generate_settlement(vendor_id: str):
    """POST /api/v1/vendors/<vendor_id>/settlements/generate — 정산 생성."""
    body = request.get_json(silent=True) or {}
    try:
        services = _get_services()
        onboarding = services[0]
        settlement_mgr = services[3]

        vendor = onboarding.get_vendor(vendor_id)
        vendor_tier = vendor.tier.value if vendor else 'basic'

        settlement = settlement_mgr.generate_settlement(
            vendor_id=vendor_id,
            orders=body.get('orders', []),
            vendor_tier=vendor_tier,
            cycle=body.get('cycle', 'weekly'),
        )
        return jsonify(settlement.to_dict()), 201
    except Exception as exc:
        logger.error('정산 생성 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /<vendor_id>/dashboard — 판매자 대시보드
# ---------------------------------------------------------------------------

@vendor_bp.get('/<vendor_id>/dashboard')
def vendor_dashboard(vendor_id: str):
    """GET /api/v1/vendors/<vendor_id>/dashboard — 판매자 대시보드."""
    body = request.get_json(silent=True) or {}
    try:
        services = _get_services()
        settlement_mgr = services[3]
        dashboard = services[10]

        orders = body.get('orders', [])
        settlements = [
            s.to_dict() for s in settlement_mgr.list_vendor_settlements(vendor_id)
        ]
        low_stock = body.get('low_stock', [])
        summary = dashboard.get_summary(vendor_id, orders, settlements, low_stock)
        return jsonify(summary)
    except Exception as exc:
        logger.error('대시보드 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500


# ---------------------------------------------------------------------------
# GET /<vendor_id>/analytics — 판매자 분석
# ---------------------------------------------------------------------------

@vendor_bp.get('/<vendor_id>/analytics')
def vendor_analytics(vendor_id: str):
    """GET /api/v1/vendors/<vendor_id>/analytics — 판매자 분석."""
    body = request.get_json(silent=True) or {}
    try:
        services = _get_services()
        analytics = services[11]
        scoring_svc = services[12]

        orders = body.get('orders', [])
        reviews = body.get('reviews', [])
        days = int(request.args.get('days', 30))

        daily = analytics.daily_trend(orders, days=days)
        ranking = analytics.product_ranking(orders)
        return_rate = analytics.return_rate(orders)
        avg_rating = analytics.average_rating(reviews)
        score = scoring_svc.calculate(
            delivery_delay_rate=body.get('delivery_delay_rate', 0.05),
            return_rate=return_rate / 100,
            avg_rating=avg_rating or 5.0,
            cs_response_hours=body.get('cs_response_hours', 2.0),
        )

        return jsonify({
            'vendor_id': vendor_id,
            'daily_trend': daily,
            'product_ranking': ranking[:10],
            'return_rate_pct': return_rate,
            'avg_rating': avg_rating,
            'score': score,
        })
    except Exception as exc:
        logger.error('분석 오류: %s', exc)
        return jsonify({'error': 'Internal server error'}), 500
