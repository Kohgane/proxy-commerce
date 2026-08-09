"""개발용 스크린샷 — 토큰 관리 페이지(활성+폐기 표본)를 캡처(폐기 분리 대비)."""
import sys, os, glob, threading, time
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

_SAMPLE = [
    {"token_hash_prefix": "9f3a1c2e...", "token_hash": "9f3a1c2e", "scopes": ["collect.write"],
     "created_at": "2026-06-26T00:00:00", "last_used_at": "2026-06-28T00:00:00", "expires_at": "2027-06-26", "revoked": False},
    {"token_hash_prefix": "4b7d88aa...", "token_hash": "4b7d88aa", "scopes": ["collect.write"],
     "created_at": "2026-05-10T00:00:00", "last_used_at": "2026-05-20T00:00:00", "expires_at": "2027-05-10", "revoked": True},
    {"token_hash_prefix": "1122ccdd...", "token_hash": "1122ccdd", "scopes": ["catalog.read"],
     "created_at": "2026-04-02T00:00:00", "last_used_at": "", "expires_at": "2027-04-02", "revoked": True},
    {"token_hash_prefix": "77ee55ff...", "token_hash": "77ee55ff", "scopes": ["collect.write"],
     "created_at": "2026-03-15T00:00:00", "last_used_at": "", "expires_at": "2027-03-15", "revoked": True},
]
import src.auth.personal_tokens as pt
pt.list_tokens = lambda user_id: [dict(t) for t in _SAMPLE]

from src.order_webhook import app
def run(): app.run(port=5086, use_reloader=False)
threading.Thread(target=run, daemon=True).start(); time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
ck = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "admin"})
out = sys.argv[1] if len(sys.argv) > 1 else "tokens"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
    if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**o); ctx = b.new_context(viewport={'width': 1000, 'height': 720}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': ck, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page(); p.goto('http://127.0.0.1:5086/seller/me/tokens', wait_until='networkidle')
    bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(bs): p.add_style_tag(path=bs)
    p.wait_for_timeout(500)
    # 토큰 목록 카드 영역 위주
    loc = p.locator('main, .console-content').first
    (loc if loc.count() else p).screenshot(path=f'/tmp/shot_{out}.png')
    b.close()
print("done")
