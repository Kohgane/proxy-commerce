"""개발용 스크린샷 — 소싱 상품 검색창(키워드 CTA 폼)을 캡처(자산은 docs/screens)."""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time

os.environ["SELLER_CONSOLE_AUTH"] = "0"

from src.order_webhook import app

def run(): app.run(port=5095, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
out = sys.argv[1] if len(sys.argv) > 1 else 'search'
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 1080, 'height': 560}, ignore_https_errors=True)
    p = ctx.new_page()
    p.goto('http://127.0.0.1:5095/seller/sourcing', wait_until='networkidle')
    _bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.wait_for_timeout(500)
    # 키워드 검색 폼 카드만 캡처
    loc = p.locator('form[action="/seller/sourcing"]').filter(has_text="무슨 상품을 팔까요").first
    (loc if loc.count() else p).screenshot(path=f'/tmp/shot_{out}.png')
    b.close()
print(f'/tmp/shot_{out}.png', os.path.getsize(f'/tmp/shot_{out}.png'))
