"""개발용 모바일 스크린샷 — 드로어(사이드바) + PWA 설치 버튼을 390px로 캡처."""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time

os.environ["SELLER_CONSOLE_AUTH"] = "0"
from src.order_webhook import app

def run(): app.run(port=5092, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
out = sys.argv[1] if len(sys.argv) > 1 else "drawer"
show_install = (sys.argv[2] if len(sys.argv) > 2 else "1") == "1"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
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
    p.goto('http://127.0.0.1:5092/seller/dashboard', wait_until='networkidle')
    _bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    # 드로어 열기 + (설치 버튼은 beforeinstallprompt가 헤드리스에선 안 떠서 데모용으로 노출)
    p.evaluate("() => { try { openSidebar(); } catch(e){} }")
    if show_install:
        p.evaluate("() => { var b=document.getElementById('pwaInstallBtn'); if(b) b.classList.remove('d-none'); }")
    p.wait_for_timeout(500)
    loc = p.locator('#sidebarDrawer')
    (loc if loc.count() else p).screenshot(path=f'/tmp/shot_{out}.png')
    b.close()
print(f'/tmp/shot_{out}.png', os.path.getsize(f'/tmp/shot_{out}.png'))
