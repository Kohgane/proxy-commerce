import logging
import os
import time

from flask import Flask, request, jsonify
from flask_cors import CORS

from .vendors.shopify_client import verify_webhook
from .orders.router import OrderRouter
from .orders.notifier import OrderNotifier
from .orders.tracker import OrderTracker
from .dashboard.order_status import OrderStatusTracker
from .utils.rate_limiter import create_limiter, LIMIT_WEBHOOK, LIMIT_HEALTH

logger = logging.getLogger(__name__)

app = Flask(__name__)

# CORS 설정 — 허용 오리진은 환경변수로 제어
# 프로덕션에서는 CORS_ORIGINS에 허용할 도메인을 명시적으로 설정할 것
_cors_origins = os.getenv('CORS_ORIGINS', '*')
CORS(app, resources={r'/health/*': {'origins': _cors_origins}})

# Rate Limiter 초기화
limiter = create_limiter(app)

# 서버 시작 시각 (uptime 계산용)
_START_TIME = time.time()

router = OrderRouter()
notifier = OrderNotifier()
tracker = OrderTracker()
status_tracker = OrderStatusTracker()


@app.post('/webhook/shopify/order')
@limiter.limit(LIMIT_WEBHOOK)
def shopify_order():
    raw_body = request.get_data()
    hmac_header = request.headers.get('X-Shopify-Hmac-Sha256', '')
    if not verify_webhook(raw_body, hmac_header):
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json(force=True)

    # 주문 라우팅
    routed = router.route_order(data)

    # 주문 상태 기록
    try:
        status_tracker.record_order(data, routed)
    except Exception as e:
        logger.warning("Failed to record order status: %s", e)

    # 알림 발송
    notifier.notify_new_order(routed)

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
