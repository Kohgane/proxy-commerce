import os
from flask import Flask, request, jsonify
from .vendors.shopify_client import verify_webhook
from .orders.router import OrderRouter
from .orders.notifier import OrderNotifier
from .orders.tracker import OrderTracker

app = Flask(__name__)
router = OrderRouter()
notifier = OrderNotifier()
tracker = OrderTracker()


@app.post('/webhook/shopify/order')
def shopify_order():
    raw_body = request.get_data()
    hmac_header = request.headers.get('X-Shopify-Hmac-Sha256', '')
    if not verify_webhook(raw_body, hmac_header):
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json(force=True)

    # 주문 라우팅
    routed = router.route_order(data)

    # 알림 발송
    notifier.notify_new_order(routed)

    return jsonify({"ok": True, "tasks": routed['summary']})


@app.post('/webhook/forwarder/tracking')
def tracking_update():
    data = request.get_json(force=True)

    result = tracker.process_tracking(data)

    if result.get('notification_sent'):
        notifier.notify_tracking_update(
            order_id=data.get('order_id'),
            sku=data.get('sku', ''),
            tracking_number=data.get('tracking_number', ''),
            carrier=data.get('carrier', ''),
        )

    return jsonify(result)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8000)))
