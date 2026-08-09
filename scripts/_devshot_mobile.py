"""개발용 모바일 스크린샷 — 핵심 화면을 390px 뷰포트로 캡처(로그인 세션·표본 데이터)."""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time

os.environ["SELLER_CONSOLE_AUTH"] = "0"

from src.order_webhook import app

def run(): app.run(port=5094, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})

PATH = sys.argv[1] if len(sys.argv) > 1 else "/seller/dashboard"
out = sys.argv[2] if len(sys.argv) > 2 else "mobile"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, ignore_https_errors=True,
                        is_mobile=True, has_touch=True, device_scale_factor=2)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto(f'http://127.0.0.1:5094{PATH}', wait_until='networkidle')
    _bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.wait_for_timeout(600)
    # 가로 스크롤 폭 측정(진단)
    sw = p.evaluate("() => ({scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth})")
    p.screenshot(path=f'/tmp/shot_{out}.png', full_page=True)
    b.close()
print(f'/tmp/shot_{out}.png', os.path.getsize(f'/tmp/shot_{out}.png'), 'overflow_x=', sw['scroll'] - sw['client'])
