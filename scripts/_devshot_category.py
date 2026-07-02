"""개발용 스크린샷 — v41 X-2 카테고리 오분류.
편집 페이지에서 '접이식 차량용 책상'의 자동 카테고리 추천을 캡처.
BEFORE(버그): '식품/차' 추천. AFTER(수리): '홈/가구/주방' 추천(차량→차 오매칭 박멸).
out 인자로 파일명 접미(before/after) 지정.
"""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time

os.environ["SELLER_CONSOLE_AUTH"] = "0"
OUT = sys.argv[1] if len(sys.argv) > 1 else "after"

from src.seller_console import collect_history_store as ch
from src.seller_console import market_credentials as mc

_ITEM = {"id": "deskcar", "title": "접이식 차량용 책상 · 폴딩 테이블",
         "url": "https://www.temu.com/p/car-desk", "image_url": "",
         "price": "24.90", "currency": "USD", "status": "ok", "extra_json": "{}"}
ch.get = lambda item_id, **kw: dict(_ITEM)
mc.is_connected = lambda *a, **k: True

from src.order_webhook import app

def run(): app.run(port=5091, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})

_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 900, 'height': 900}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto("http://127.0.0.1:5091/seller/collect/preview/deskcar", wait_until="networkidle")
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.wait_for_timeout(500)
    # 카테고리 form-group을 감싼 카드 영역 캡처
    loc = p.locator("#editCategory").locator("xpath=ancestor::div[contains(@class,'mb-3') or contains(@class,'form-group')][1]")
    hint = p.locator("#categoryHint").inner_text() if p.locator("#categoryHint").count() else "(no hint)"
    print("categoryHint:", hint.strip())
    sel = p.locator("#editCategory")
    print("selected option:", sel.evaluate("el => el.options[el.selectedIndex] && el.options[el.selectedIndex].text"))
    target = loc.first if loc.count() else p.locator("#editCategory")
    target.screenshot(path=f"/tmp/shot_category_{OUT}.png")
    b.close()
print("done", OUT)
