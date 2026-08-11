"""개발용 스크린샷 — v86-T 토큰 관리 화면 상태뱃지 공통화.

BEFORE(부트스트랩 badge bg-*) vs AFTER(pc-badge 청록/주황/뮤트). 활성·유휴만료·삭제됨 3상태 +
스코프 태그가 보이도록 토큰 몽키패치.
"""
import os, sys, glob, threading, time, subprocess
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

TPL = "src/seller_console/templates/personal_tokens.html"
NEW = open(TPL, encoding="utf-8").read()
OLD = subprocess.check_output(["git", "show", "HEAD:" + TPL]).decode("utf-8")

import src.auth.personal_tokens as pt
TOKENS = [
    {"token_hash": "h1", "token_hash_prefix": "kgp_9f2a", "scopes": ["collect.write", "catalog.read"],
     "created_at": "2026-07-01", "last_used_at": "2026-08-10", "expires_at": "2026-10-01",
     "revoked": False, "idle_expired": False},
    {"token_hash": "h2", "token_hash_prefix": "kgp_71bd", "scopes": ["collect.write"],
     "created_at": "2026-04-02", "last_used_at": "2026-04-20", "expires_at": "2026-12-01",
     "revoked": False, "idle_expired": True},
    {"token_hash": "h3", "token_hash_prefix": "kgp_3c8e", "scopes": ["markets.write"],
     "created_at": "2026-03-01", "last_used_at": "2026-03-05", "expires_at": "2026-09-01",
     "revoked": True, "idle_expired": False},
]
pt.list_tokens = lambda user_id, user_ids=None: list(TOKENS)

from src.order_webhook import app
app.jinja_env.auto_reload = True
app.jinja_env.cache = {}
app.config["TEMPLATES_AUTO_RELOAD"] = True

def run(): app.run(port=5099, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def shot(which, path):
    open(TPL, "w", encoding="utf-8").write(which)
    app.jinja_env.cache = {}
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY')
        opts = {'executable_path': exe}
        if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**opts)
        ctx = b.new_context(viewport={'width': 940, 'height': 760}, ignore_https_errors=True)
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5099/seller/me/tokens", wait_until="networkidle")
        if os.path.exists(_bs):
            p.add_style_tag(path=_bs)
        p.wait_for_timeout(600)
        # 활성 토큰 표 카드 우선, 없으면 main.
        card = p.query_selector("table")
        target = None
        if card:
            target = p.evaluate_handle("el => el.closest('.card') || el", card).as_element()
        (target or p.query_selector("main") or p).screenshot(path=path)
        b.close()

try:
    shot(OLD, "/tmp/tok_before.png")
    shot(NEW, "/tmp/tok_after.png")
finally:
    open(TPL, "w", encoding="utf-8").write(NEW)

from PIL import Image, ImageDraw
def fit(p, w=500):
    im = Image.open(p).convert("RGB"); r = w/im.width
    return im.resize((w, int(im.height*r)))
a, bmg = fit("/tmp/tok_before.png"), fit("/tmp/tok_after.png")
band = 30
H = max(a.height, bmg.height) + band + 8
canvas = Image.new("RGB", (a.width + bmg.width + 24, H), "white")
d = ImageDraw.Draw(canvas)
d.text((8, 8), "BEFORE — 부트스트랩 badge bg-*", fill=(150, 60, 60))
d.text((a.width + 20, 8), "AFTER — pc-badge(활성=청록·유휴=주황·삭제=뮤트)", fill=(17, 154, 142))
canvas.paste(a, (8, band)); canvas.paste(bmg, (a.width + 20, band))
os.makedirs("docs/screens/v86t", exist_ok=True)
canvas.save("docs/screens/v86t/v86t-tokens.png")
print("saved docs/screens/v86t/v86t-tokens.png")
