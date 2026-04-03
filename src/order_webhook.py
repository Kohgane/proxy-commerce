import logging
import os
import time

from flask import Flask, request, jsonify
from flask_cors import CORS

from .vendors.shopify_client import verify_webhook
from .vendors.woocommerce_client import verify_woo_webhook
from .orders.router import OrderRouter
from .orders.notifier import OrderNotifier
from .orders.tracker import OrderTracker
from .dashboard.order_status import OrderStatusTracker
from .utils.rate_limiter import create_limiter, LIMIT_WEBHOOK, LIMIT_HEALTH
from .middleware.request_logger import RequestLogger
from .middleware.security import SecurityMiddleware
from .validation.order_validator import OrderValidator, DUPLICATE_ORDER_TAG
from .audit.audit_logger import AuditLogger
from .audit.event_types import EventType

logger = logging.getLogger(__name__)

app = Flask(__name__)

# 대시보드 API Blueprint 등록 (DASHBOARD_API_ENABLED=1 시)
if os.getenv("DASHBOARD_API_ENABLED", "1") == "1":
    try:
        from .api import dashboard_bp
        app.register_blueprint(dashboard_bp)
        logger.info("대시보드 API Blueprint 등록 완료")
    except Exception as _bp_exc:
        logger.warning("대시보드 API Blueprint 등록 실패: %s", _bp_exc)

# 대시보드 웹 UI Blueprint 등록 (DASHBOARD_WEB_UI_ENABLED=1 시)
if os.getenv("DASHBOARD_WEB_UI_ENABLED", "1") == "1":
    try:
        from .dashboard.web_ui import web_ui_bp
        app.register_blueprint(web_ui_bp)
        logger.info("대시보드 웹 UI Blueprint 등록 완료")
    except Exception as _web_ui_exc:
        logger.warning("대시보드 웹 UI Blueprint 등록 실패: %s", _web_ui_exc)

# 설정 관리 API Blueprint 등록
try:
    from .api.config_routes import config_bp
    app.register_blueprint(config_bp)
    logger.info("설정 관리 API Blueprint 등록 완료")
except Exception as _cfg_bp_exc:
    logger.warning("설정 관리 API Blueprint 등록 실패: %s", _cfg_bp_exc)

# 리뷰 관리 API Blueprint 등록
try:
    from .api.reviews_api import reviews_bp
    app.register_blueprint(reviews_bp)
    logger.info("리뷰 API Blueprint 등록 완료")
except Exception as _rev_bp_exc:
    logger.warning("리뷰 API Blueprint 등록 실패: %s", _rev_bp_exc)

# 프로모션 관리 API Blueprint 등록
try:
    from .api.promotions_api import promotions_bp
    app.register_blueprint(promotions_bp)
    logger.info("프로모션 API Blueprint 등록 완료")
except Exception as _promo_bp_exc:
    logger.warning("프로모션 API Blueprint 등록 실패: %s", _promo_bp_exc)

# CRM API Blueprint 등록
try:
    from .api.crm_api import crm_bp
    app.register_blueprint(crm_bp)
    logger.info("CRM API Blueprint 등록 완료")
except Exception as _crm_bp_exc:
    logger.warning("CRM API Blueprint 등록 실패: %s", _crm_bp_exc)

# Marketing API Blueprint 등록
try:
    from .api.marketing_api import marketing_bp
    app.register_blueprint(marketing_bp)
    logger.info("마케팅 API Blueprint 등록 완료")
except Exception as _mkt_bp_exc:
    logger.warning("마케팅 API Blueprint 등록 실패: %s", _mkt_bp_exc)

# 리포트 API Blueprint 등록
try:
    from .api.reports_api import reports_bp
    app.register_blueprint(reports_bp)
    logger.info("리포트 API Blueprint 등록 완료")
except Exception as _rep_bp_exc:
    logger.warning("리포트 API Blueprint 등록 실패: %s", _rep_bp_exc)

# SEO API Blueprint 등록
try:
    from .api.seo_api import seo_bp
    app.register_blueprint(seo_bp)
    logger.info("SEO API Blueprint 등록 완료")
except Exception as _seo_bp_exc:
    logger.warning("SEO API Blueprint 등록 실패: %s", _seo_bp_exc)

# 경쟁사 분석 API Blueprint 등록
try:
    from .api.competitor_api import competitor_bp
    app.register_blueprint(competitor_bp)
    logger.info("경쟁사 분석 API Blueprint 등록 완료")
except Exception as _comp_bp_exc:
    logger.warning("경쟁사 분석 API Blueprint 등록 실패: %s", _comp_bp_exc)

# 수요 예측 API Blueprint 등록
try:
    from .api.forecast_api import forecast_bp
    app.register_blueprint(forecast_bp)
    logger.info("수요 예측 API Blueprint 등록 완료")
except Exception as _fc_bp_exc:
    logger.warning("수요 예측 API Blueprint 등록 실패: %s", _fc_bp_exc)

# 자동화 API Blueprint 등록
try:
    from .api.automation_api import automation_bp
    app.register_blueprint(automation_bp)
    logger.info("자동화 API Blueprint 등록 완료")
except Exception as _auto_bp_exc:
    logger.warning("자동화 API Blueprint 등록 실패: %s", _auto_bp_exc)

# 결제/정산 API Blueprint 등록
try:
    from .api.payments_api import payments_bp
    app.register_blueprint(payments_bp)
    logger.info("결제/정산 API Blueprint 등록 완료")
except Exception as _pay_bp_exc:
    logger.warning("결제/정산 API Blueprint 등록 실패: %s", _pay_bp_exc)

# 모니터링 API Blueprint 등록
try:
    from .api.monitoring_api import monitoring_bp
    app.register_blueprint(monitoring_bp)
    logger.info("모니터링 API Blueprint 등록 완료")
except Exception as _mon_bp_exc:
    logger.warning("모니터링 API Blueprint 등록 실패: %s", _mon_bp_exc)

# Auth API Blueprint 등록
try:
    from .api.auth_api import auth_api_bp
    app.register_blueprint(auth_api_bp)
    logger.info("Auth API Blueprint 등록 완료")
except Exception as _auth_api_exc:
    logger.warning("Auth API Blueprint 등록 실패: %s", _auth_api_exc)

# 관리자 패널 Blueprint 등록 (Phase 25)
try:
    from .dashboard.admin_views import admin_panel_bp
    app.register_blueprint(admin_panel_bp)
    logger.info("관리자 패널 Blueprint 등록 완료")
except Exception as _admin_bp_exc:
    logger.warning("관리자 패널 Blueprint 등록 실패: %s", _admin_bp_exc)

# 배송 추적 API Blueprint 등록 (Phase 27)
try:
    from .api.shipping_api import shipping_api
    app.register_blueprint(shipping_api)
    logger.info("배송 추적 API Blueprint 등록 완료")
except Exception as _ship_api_exc:
    logger.warning("배송 추적 API Blueprint 등록 실패: %s", _ship_api_exc)

# CS API Blueprint 등록 (Phase 28)
try:
    from .api.cs_api import cs_api
    app.register_blueprint(cs_api)
    logger.info("CS API Blueprint 등록 완료")
except Exception as _cs_api_exc:
    logger.warning("CS API Blueprint 등록 실패: %s", _cs_api_exc)

# 분석 API Blueprint 등록 (Phase 29)
try:
    from .api.analytics_api import analytics_api
    app.register_blueprint(analytics_api)
    logger.info("분석 API Blueprint 등록 완료")
except Exception as _analytics_api_exc:
    logger.warning("분석 API Blueprint 등록 실패: %s", _analytics_api_exc)

# 재고 동기화 API Blueprint 등록
try:
    from .api.inventory_sync_api import inventory_sync_bp
    app.register_blueprint(inventory_sync_bp)
    logger.info("재고 동기화 API Blueprint 등록 완료")
except Exception as _inv_sync_bp_exc:
    logger.warning("재고 동기화 API Blueprint 등록 실패: %s", _inv_sync_bp_exc)

# 번역 관리 API Blueprint 등록
try:
    from .api.translation_api import translation_bp
    app.register_blueprint(translation_bp)
    logger.info("번역 관리 API Blueprint 등록 완료")
except Exception as _trans_bp_exc:
    logger.warning("번역 관리 API Blueprint 등록 실패: %s", _trans_bp_exc)

# 가격 엔진 API Blueprint 등록
try:
    from .api.pricing_api import pricing_bp
    app.register_blueprint(pricing_bp)
    logger.info("가격 엔진 API Blueprint 등록 완료")
except Exception as _pricing_bp_exc:
    logger.warning("가격 엔진 API Blueprint 등록 실패: %s", _pricing_bp_exc)

# 공급자 관리 API Blueprint 등록
try:
    from .api.suppliers_api import suppliers_bp
    app.register_blueprint(suppliers_bp)
    logger.info("공급자 API Blueprint 등록 완료")
except Exception as _sup_bp_exc:
    logger.warning("공급자 API Blueprint 등록 실패: %s", _sup_bp_exc)

# 알림 관리 API Blueprint 등록
try:
    from .api.notifications_api import notifications_bp
    app.register_blueprint(notifications_bp)
    logger.info("알림 관리 API Blueprint 등록 완료")
except Exception as _notif_bp_exc:
    logger.warning("알림 관리 API Blueprint 등록 실패: %s", _notif_bp_exc)

# 반품/교환 API Blueprint 등록 (Phase 37)
try:
    from .api.returns_api import returns_bp
    app.register_blueprint(returns_bp)
    logger.info("반품/교환 API Blueprint 등록 완료")
except Exception as _ret_bp_exc:
    logger.warning("반품/교환 API Blueprint 등록 실패: %s", _ret_bp_exc)

# 쿠폰 API Blueprint 등록 (Phase 38)
try:
    from .api.coupons_api import coupons_bp
    app.register_blueprint(coupons_bp)
    logger.info("쿠폰 API Blueprint 등록 완료")
except Exception as _coup_bp_exc:
    logger.warning("쿠폰 API Blueprint 등록 실패: %s", _coup_bp_exc)

# 카테고리 API Blueprint 등록 (Phase 39)
try:
    from .api.categories_api import categories_bp
    app.register_blueprint(categories_bp)
    logger.info("카테고리 API Blueprint 등록 완료")
except Exception as _cat_bp_exc:
    logger.warning("카테고리 API Blueprint 등록 실패: %s", _cat_bp_exc)

# 스케줄러 API Blueprint 등록 (Phase 40)
try:
    from .api.scheduler_api import scheduler_bp
    app.register_blueprint(scheduler_bp)
    logger.info("스케줄러 API Blueprint 등록 완료")
except Exception as _sched_bp_exc:
    logger.warning("스케줄러 API Blueprint 등록 실패: %s", _sched_bp_exc)

# 감사 로그 API Blueprint 등록 (Phase 41)
try:
    from .api.audit_api import audit_bp
    app.register_blueprint(audit_bp)
    logger.info("감사 로그 API Blueprint 등록 완료")
except Exception as _audit_bp_exc:
    logger.warning("감사 로그 API Blueprint 등록 실패: %s", _audit_bp_exc)

# 위시리스트 API Blueprint 등록 (Phase 43)
try:
    from .api.wishlist_api import wishlist_bp
    app.register_blueprint(wishlist_bp)
    logger.info("위시리스트 API Blueprint 등록 완료")
except Exception as _wishlist_bp_exc:
    logger.warning("위시리스트 API Blueprint 등록 실패: %s", _wishlist_bp_exc)

# 번들 API Blueprint 등록 (Phase 44)
try:
    from .api.bundles_api import bundles_bp
    app.register_blueprint(bundles_bp)
    logger.info("번들 API Blueprint 등록 완료")
except Exception as _bundles_bp_exc:
    logger.warning("번들 API Blueprint 등록 실패: %s", _bundles_bp_exc)

# 멀티통화 API Blueprint 등록 (Phase 45)
try:
    from .api.multicurrency_api import multicurrency_bp
    app.register_blueprint(multicurrency_bp)
    logger.info("멀티통화 API Blueprint 등록 완료")
except Exception as _mc_bp_exc:
    logger.warning("멀티통화 API Blueprint 등록 실패: %s", _mc_bp_exc)

# 결제 게이트웨이 API Blueprint 등록 (Phase 45)
try:
    from .api.payment_api import payment_bp
    app.register_blueprint(payment_bp)
    logger.info("결제 게이트웨이 API Blueprint 등록 완료")
except Exception as _pay_bp_exc:
    logger.warning("결제 게이트웨이 API Blueprint 등록 실패: %s", _pay_bp_exc)

# 이미지 관리 API Blueprint 등록 (Phase 46)
try:
    from .api.images_api import images_bp
    app.register_blueprint(images_bp)
    logger.info("이미지 관리 API Blueprint 등록 완료")
except Exception as _img_bp_exc:
    logger.warning("이미지 관리 API Blueprint 등록 실패: %s", _img_bp_exc)

# 사용자 프로필 API Blueprint 등록 (Phase 47)
try:
    from .api.users_api import users_bp
    app.register_blueprint(users_bp)
    logger.info("사용자 프로필 API Blueprint 등록 완료")
except Exception as _users_bp_exc:
    logger.warning("사용자 프로필 API Blueprint 등록 실패: %s", _users_bp_exc)

# 검색 엔진 API Blueprint 등록 (Phase 48)
try:
    from .api.search_api import search_bp
    app.register_blueprint(search_bp)
    logger.info("검색 엔진 API Blueprint 등록 완료")
except Exception as _search_bp_exc:
    logger.warning("검색 엔진 API Blueprint 등록 실패: %s", _search_bp_exc)

# 멀티테넌시 API Blueprint 등록 (Phase 49)
try:
    from .api.tenancy_api import tenancy_bp
    app.register_blueprint(tenancy_bp)
    logger.info("멀티테넌시 API Blueprint 등록 완료")
except Exception as _tenancy_bp_exc:
    logger.warning("멀티테넌시 API Blueprint 등록 실패: %s", _tenancy_bp_exc)

# A/B 테스트 API Blueprint 등록 (Phase 50)
try:
    from .api.ab_testing_api import ab_testing_bp
    app.register_blueprint(ab_testing_bp)
    logger.info("A/B 테스트 API Blueprint 등록 완료")
except Exception as _ab_testing_bp_exc:
    logger.warning("A/B 테스트 API Blueprint 등록 실패: %s", _ab_testing_bp_exc)

# 웹훅 관리 API Blueprint 등록 (Phase 51)
try:
    from .api.webhook_manager_api import webhook_manager_bp
    app.register_blueprint(webhook_manager_bp)
    logger.info("웹훅 관리 API Blueprint 등록 완료")
except Exception as _webhook_manager_bp_exc:
    logger.warning("웹훅 관리 API Blueprint 등록 실패: %s", _webhook_manager_bp_exc)

# API 문서 Blueprint 등록 (Phase 52)
try:
    from .api.docs_api import docs_bp
    app.register_blueprint(docs_bp)
    logger.info("API 문서 Blueprint 등록 완료")
except Exception as _docs_bp_exc:
    logger.warning("API 문서 Blueprint 등록 실패: %s", _docs_bp_exc)

# 로깅/추적 API Blueprint 등록 (Phase 53)
try:
    from .api.traces_api import traces_bp
    app.register_blueprint(traces_bp)
    logger.info("로깅/추적 API Blueprint 등록 완료")
except Exception as _traces_bp_exc:
    logger.warning("로깅/추적 API Blueprint 등록 실패: %s", _traces_bp_exc)

# 벤치마크 API Blueprint 등록 (Phase 54)
try:
    from .api.benchmark_api import benchmark_bp
    app.register_blueprint(benchmark_bp)
    logger.info("벤치마크 API Blueprint 등록 완료")
except Exception as _benchmark_bp_exc:
    logger.warning("벤치마크 API Blueprint 등록 실패: %s", _benchmark_bp_exc)

# CORS 설정 — 허용 오리진은 환경변수로 제어
# 프로덕션에서는 CORS_ORIGINS에 허용할 도메인을 명시적으로 설정할 것
_cors_origins = os.getenv('CORS_ORIGINS', '*')
CORS(app, resources={r'/health/*': {'origins': _cors_origins}})

# Rate Limiter 초기화
limiter = create_limiter(app)

# 요청 로거 미들웨어 초기화
request_logger = RequestLogger(app)

# 보안 미들웨어 초기화
security = SecurityMiddleware(app)

# 서버 시작 시각 (uptime 계산용)
_START_TIME = time.time()

router = OrderRouter()
notifier = OrderNotifier()
tracker = OrderTracker()
status_tracker = OrderStatusTracker()

# 주문 검증기 + 감사 로거 초기화
order_validator = OrderValidator()
audit_logger = AuditLogger()


@app.post('/webhook/shopify/order')
@limiter.limit(LIMIT_WEBHOOK)
def shopify_order():
    raw_body = request.get_data()
    hmac_header = request.headers.get('X-Shopify-Hmac-Sha256', '')
    if not verify_webhook(raw_body, hmac_header):
        audit_logger.log(
            EventType.WEBHOOK_REJECTED,
            actor="shopify_webhook",
            resource="webhook:/webhook/shopify/order",
            ip_address=request.remote_addr or "",
        )
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json(force=True)

    # 주문 페이로드 검증
    is_valid, validation_errors = order_validator.validate_shopify(data)
    if not is_valid:
        logger.warning("Shopify 주문 검증 실패: %s", validation_errors)
        is_duplicate = any(e.startswith(DUPLICATE_ORDER_TAG) for e in validation_errors)
        audit_logger.log(
            EventType.ORDER_DUPLICATE_DETECTED if is_duplicate else EventType.WEBHOOK_REJECTED,
            actor="order_validator",
            resource=f"order:{data.get('id')}",
            details={"errors": validation_errors},
            ip_address=request.remote_addr or "",
        )
        # 중복 주문은 200 반환 (재전송 방지), 다른 검증 실패는 400
        if is_duplicate:
            return jsonify({"ok": True, "skipped": "duplicate"}), 200
        return jsonify({"error": "validation_failed", "details": validation_errors}), 400

    # 주문 라우팅
    routed = router.route_order(data)

    # 주문 상태 기록
    try:
        status_tracker.record_order(data, routed)
    except Exception as e:
        logger.warning("Failed to record order status: %s", e)

    # 알림 발송
    notifier.notify_new_order(routed)

    # 감사 로그 기록
    audit_logger.log_order(
        EventType.ORDER_ROUTED,
        order_id=data.get('id'),
        details={"summary": routed.get('summary', {})},
        ip_address=request.remote_addr or "",
    )

    return jsonify({"ok": True, "tasks": routed['summary']})


@app.post('/webhook/woo')
@limiter.limit(LIMIT_WEBHOOK)
def woocommerce_order():
    """WooCommerce 주문 웹훅 처리 엔드포인트."""
    raw_body = request.get_data()
    sig_header = request.headers.get('X-WC-Webhook-Signature', '')
    if not verify_woo_webhook(raw_body, sig_header):
        audit_logger.log(
            EventType.WEBHOOK_REJECTED,
            actor="woo_webhook",
            resource="webhook:/webhook/woo",
            ip_address=request.remote_addr or "",
        )
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json(force=True)

    # 주문 페이로드 검증
    is_valid, validation_errors = order_validator.validate_woocommerce(data)
    if not is_valid:
        logger.warning("WooCommerce 주문 검증 실패: %s", validation_errors)
        is_duplicate = any(e.startswith(DUPLICATE_ORDER_TAG) for e in validation_errors)
        if is_duplicate:
            return jsonify({"ok": True, "skipped": "duplicate"}), 200
        return jsonify({"error": "validation_failed", "details": validation_errors}), 400

    routed = router.route_order(data)

    try:
        status_tracker.record_order(data, routed)
    except Exception as e:
        logger.warning("Failed to record woo order status: %s", e)

    notifier.notify_new_order(routed)

    audit_logger.log_order(
        EventType.ORDER_ROUTED,
        order_id=data.get('id'),
        details={"summary": routed.get('summary', {}), "source": "woocommerce"},
        ip_address=request.remote_addr or "",
    )

    return jsonify({"ok": True, "tasks": routed['summary']})


@app.post('/webhook/forwarder/tracking')
@limiter.limit(LIMIT_WEBHOOK)
def tracking_update():
    data = request.get_json(force=True)

    result = tracker.process_tracking(data)

    # 주문 상태 업데이트
    try:
        status_tracker.update_status(
            order_id=data.get('order_id'),
            sku=data.get('sku', ''),
            new_status='shipped_domestic',
            tracking_number=data.get('tracking_number', ''),
            carrier=data.get('carrier', ''),
        )
    except Exception as e:
        logger.warning("Failed to update order status: %s", e)

    if result.get('notification_sent'):
        notifier.notify_tracking_update(
            order_id=data.get('order_id'),
            sku=data.get('sku', ''),
            tracking_number=data.get('tracking_number', ''),
            carrier=data.get('carrier', ''),
        )

    return jsonify(result)


@app.get('/health')
@limiter.limit(LIMIT_HEALTH)
def health():
    """Healthcheck 엔드포인트 — Docker/LB용."""
    return jsonify({
        "status": "ok",
        "service": "proxy-commerce",
        "version": os.getenv("APP_VERSION", "dev"),
    })


@app.get('/health/ready')
@limiter.limit(LIMIT_HEALTH)
def readiness():
    """Readiness check — 외부 의존성(Sheets 등) 연결 확인."""
    checks = {}
    try:
        from .utils.secret_check import check_secrets
        result = check_secrets('core')
        checks['secrets_core'] = len(result['core']['missing']) == 0
    except Exception:
        checks['secrets_core'] = False

    all_ok = all(checks.values())
    status_code = 200 if all_ok else 503
    return jsonify({
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
    }), status_code


@app.get('/health/deep')
@limiter.limit(LIMIT_HEALTH)
def deep_health():
    """Deep healthcheck — 외부 의존성 상세 연결 확인.

    응답 JSON:
        {
            "status": "ok" | "degraded",
            "timestamp": "ISO8601",
            "uptime_seconds": float,
            "checks": {
                "secrets_core": bool,
                "google_sheets": bool,
                ...
            },
            "version": str
        }
    """
    import datetime
    checks = {}
    now_iso = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    uptime = round(time.time() - _START_TIME, 1)

    # 1) 시크릿 검증
    try:
        from .utils.secret_check import check_secrets
        secret_result = check_secrets('core')
        checks['secrets_core'] = len(secret_result['core']['missing']) == 0
    except Exception as exc:
        logger.warning("Deep health: secret check failed: %s", exc)
        checks['secrets_core'] = False

    # 2) Google Sheets 연결 확인
    try:
        from .utils.sheets import open_sheet
        sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
        if sheet_id:
            open_sheet(sheet_id, os.getenv('WORKSHEET', 'catalog'))
            checks['google_sheets'] = True
        else:
            checks['google_sheets'] = False
    except Exception as exc:
        logger.warning("Deep health: Google Sheets check failed: %s", exc)
        checks['google_sheets'] = False

    all_ok = all(checks.values())
    status_code = 200 if all_ok else 503
    return jsonify({
        "status": "ok" if all_ok else "degraded",
        "timestamp": now_iso,
        "uptime_seconds": uptime,
        "version": os.getenv("APP_VERSION", "dev"),
        "checks": checks,
    }), status_code


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8000)))
