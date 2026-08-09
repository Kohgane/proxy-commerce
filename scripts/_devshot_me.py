"""개발용 스크린샷 — 마이페이지(내 작업공간)를 모의 사용자/표본 카운트로 캡처(자산은 docs/screens)."""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time
from types import SimpleNamespace

os.environ["SELLER_CONSOLE_AUTH"] = "0"

# 모의 사용자(테스트 환경엔 시트가 없어 user 레코드가 비므로 주입)
_USER = SimpleNamespace(
    name="데모 셀러", email="demo@goga.kr", role="seller", avatar_url=None,
    email_verified=True, created_at="2026-03-12T00:00:00", last_login_at="2026-06-28T00:00:00",
    social_accounts=[SimpleNamespace(provider="google")],
)
import src.auth.user_store as us
us.get_store = lambda: SimpleNamespace(find_by_id=lambda _id: _USER)

# 표본 카운트(디자인 가독성용 — 실 스토어는 빈 상태)
import src.seller_console.billing_store as bs
bs.get_account = lambda sid: {"plan": "free", "token_balance": 18}
import src.seller_console.market_credentials as mc
mc.is_connected = lambda sid, m: m in ("coupang", "woocommerce")
import src.seller_console.my_sources_store as ms
ms.list_sources = lambda: [{"domain": "taobao.com"}, {"domain": "1688.com"}, {"domain": "amazon.com"}]
import src.seller_console.collect_history_store as ch
ch.summary = lambda *a, **k: {"total": 27, "today": 3}

from src.order_webhook import app

def run(): app.run(port=5098, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

# 로그인 세션 쿠키 발급
with app.test_request_context():
    pass
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러"})

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
out = sys.argv[1] if len(sys.argv) > 1 else 'me'
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 1180, 'height': 1500}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto('http://127.0.0.1:5098/seller/me', wait_until='networkidle')
    _bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.wait_for_timeout(500)
    # 메인 콘텐츠 영역만 캡처
    loc = p.locator('main, .console-content, #content').first
    (loc if loc.count() else p).screenshot(path=f'/tmp/shot_{out}.png')
    b.close()
print(f'/tmp/shot_{out}.png', os.path.getsize(f'/tmp/shot_{out}.png'))
