"""순찰 122b 캡처 — 고급 기능 게이트: 무료(숨김+켜기 입구) / 토글 ON / 숨긴 URL 배너 / 설정 카드. 인증 ON 모드로 실제 분기."""
import sys, os, threading, time, glob
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "1"
os.environ["SECRET_KEY"] = "devshot"
from src.order_webhook import app
from src.seller_console import views as V
V._AUTH_ENABLED = True
from src.seller_console import billing_store as B
B.get_account = lambda sid: {"plan": "free", "token_balance": 0}
from src.auth import user_store as US
class _U(dict):
    __getattr__ = dict.get
US.get_store = lambda: type("S", (), {"find_by_id": staticmethod(lambda uid: _U(email="seller@example.com", name="셀러", role="seller", email_verified=True, social_accounts=[], created_at="2026-10-01", last_login_at="2026-10-26", avatar_url=""))})()

@app.route("/__login")
def _login():
    from flask import session, redirect, request
    session["user_id"] = "devshot-seller"; session["user_email"] = "seller@example.com"; session["user_role"] = "seller"
    return redirect(request.args.get("next", "/seller/orders"))

threading.Thread(target=lambda: app.run(port=5098, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
out = sys.argv[1] if len(sys.argv) > 1 else "docs/screens/y15p122"
bs = next((p for p in ["node_modules/bootstrap/dist/css/bootstrap.min.css", "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"] if os.path.exists(p)), None)
def shot(p, url, name, w=1280, h=900, clip=None):
    p.set_viewport_size({"width": w, "height": h}); p.goto(url, wait_until="networkidle")
    if bs: p.add_style_tag(path=bs)
    p.wait_for_timeout(400); p.screenshot(path=f"{out}/{name}.png", clip=clip, full_page=clip is None and h > 1000)
with sync_playwright() as pw:
    px = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    opts = {"executable_path": exe}
    if px: opts["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
    b = pw.chromium.launch(**opts); ctx = b.new_context(ignore_https_errors=True); p = ctx.new_page()
    p.goto("http://127.0.0.1:5098/__login?next=/seller/orders", wait_until="networkidle")
    shot(p, "http://127.0.0.1:5098/seller/orders", "after-1-free-sidebar-hidden", clip={"x": 0, "y": 0, "width": 300, "height": 900})
    shot(p, "http://127.0.0.1:5098/seller/listing/word-rules", "after-2-hidden-url-banner", clip={"x": 260, "y": 0, "width": 1020, "height": 260})
    shot(p, "http://127.0.0.1:5098/seller/me", "after-3-me-card-off", clip={"x": 260, "y": 0, "width": 1020, "height": 1400})
    p.request.post("http://127.0.0.1:5098/seller/me/advanced", data='{"on":true}', headers={"Content-Type": "application/json"})
    shot(p, "http://127.0.0.1:5098/seller/orders", "after-4-toggle-on-sidebar", clip={"x": 0, "y": 0, "width": 300, "height": 1600})
    # before: 개발 모드(전부 보임)와 같은 모양 — 게이트 끈 채로 한 장
    V._AUTH_ENABLED = False
    shot(p, "http://127.0.0.1:5098/seller/orders", "before-sidebar-all-advanced", clip={"x": 0, "y": 0, "width": 300, "height": 1600})
    b.close()
print(sorted(os.listdir(out)))
