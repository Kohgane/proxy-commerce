"""Z6 캡처: 공개 가입자(stranger) 세션으로 /seller/markets/connect 를 390px로 렌더.

usage: python capture.py <repo_root> <out.png> <port>
오너 서버 env는 가짜 값(OWNER_*)으로 주입 — 실제 키 아님.
"""
import os
import sys
import tempfile
import threading
import time

root, out, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.chdir(root)
sys.path.insert(0, root)
tmp = tempfile.mkdtemp()
os.environ.update({
    "MARKET_CRED_DIR": tmp, "SECRET_KEY": "z6-capture", "SELLER_CONSOLE_AUTH": "1",
    "FAMILY_EMAILS": "mom@example.com",
    "SHOPIFY_SHOP": "owner-shop.myshopify.com", "SHOPIFY_CLIENT_ID": "owner-cid", "SHOPIFY_CLIENT_SECRET": "shpss_owner",
    "WC_URL": "https://owner-wc.example", "WC_KEY": "ck_owner", "WC_SECRET": "cs_owner",
    "COUPANG_ACCESS_KEY": "owner-ak", "COUPANG_SECRET_KEY": "owner-sk", "COUPANG_VENDOR_ID": "A00OWNER",
    "COUPANG_RETURN_ADDRESS": "서울 오너 반품지 주소", "ELEVENST_API_KEY": "owner-11st",
    "NAVER_CLIENT_ID": "owner-naver", "NAVER_CLIENT_SECRET": "owner-naver-sec",
})
for k in ("DATABASE_URL", "ADMIN_EMAILS", "MARKET_CRED_ENC_KEY"):
    os.environ.pop(k, None)

from src.order_webhook import app  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

srv = make_server("127.0.0.1", port, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(0.5)
cookie = app.session_interface.get_signing_serializer(app).dumps(
    {"user_id": "stranger-z6", "user_email": "stranger@example.com", "user_role": "seller"})

from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    ctx.add_cookies([{"name": app.config.get("SESSION_COOKIE_NAME", "session"), "value": cookie,
                      "domain": "127.0.0.1", "path": "/"}])
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{port}/seller/markets/connect", wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(800)
    txt = pg.inner_text("body")
    print("owner-shop visible:", "owner-shop.myshopify.com" in txt)
    print("서버 환경변수 visible:", "서버 환경변수" in txt)
    pg.screenshot(path=out, full_page=True)
    b.close()
srv.shutdown()
