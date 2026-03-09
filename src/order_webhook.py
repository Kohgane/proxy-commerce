import os
from flask import Flask, request, jsonify
from .utils.emailer import send_mail
from .utils.telegram import send_tele
from .utils.notion import create_task_if_env
from .vendors.shopify_client import verify_webhook

app = Flask(__name__)

@app.post('/webhook/shopify/order')
def shopify_order():
    raw_body = request.get_data()
    hmac_header = request.headers.get('X-Shopify-Hmac-Sha256', '')
    if not verify_webhook(raw_body, hmac_header):
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json(force=True)
    order_id = data.get('id')
    line_items = data.get('line_items', [])
    tasks = []
    for it in line_items:
        sku = it.get('sku') or (it.get('variant_id') and str(it['variant_id']))
        src_url = f"lookup_by_sku({sku})"  # 시트 매핑 로직은 추후 확장
        tasks.append(f"[구매요청] order={order_id} sku={sku} src={src_url}")
        create_task_if_env(title=f"구매요청 {sku}", url=src_url, sku=sku, order_id=order_id)
    body = "\n".join(tasks) + "\n\n배대지 주소: <미국/한국 창고주소>\n송장 생성 후 /webhook/forwarder/tracking 으로 POST"
    if os.getenv('EMAIL_ENABLED', '0') == '1':
        send_mail(subject='[구매요청] 신규 주문 태스크', body=body)
    if os.getenv('TELEGRAM_ENABLED', '1') == '1':
        send_tele(body)
    return jsonify({"ok": True})

@app.post('/webhook/forwarder/tracking')
def tracking_update():
    data = request.get_json(force=True)
    # TODO: tracking → 고객 알림/스토어 업데이트
    return {"ok": True}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8000)))
