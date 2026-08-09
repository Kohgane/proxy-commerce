"""개발용 스크린샷 — 공백 섞인 BRAND_NAME_KO env에서 사이드바 한글 표기 캡처(정규화 대비)."""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time

os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ["BRAND_NAME_KO"] = "고가 브릿지"   # 공백 섞인 override(오너 라이브 증상 모사)

from src.order_webhook import app

def run(): app.run(port=5091, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
out = sys.argv[1] if len(sys.argv) > 1 else "brand"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 390, 'height': 320}, ignore_https_errors=True,
                        is_mobile=True, has_touch=True, device_scale_factor=2)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto('http://127.0.0.1:5091/seller/dashboard', wait_until='networkidle')
    _bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.evaluate("() => { try { openSidebar(); } catch(e){} }")
    p.wait_for_timeout(400)
    loc = p.locator('.console-brand')
    (loc if loc.count() else p).screenshot(path=f'/tmp/shot_{out}.png')
    b.close()
print(f'/tmp/shot_{out}.png', os.path.getsize(f'/tmp/shot_{out}.png'))
