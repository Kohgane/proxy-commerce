"""개발용 모바일 스크린샷 — 수집 상품 편집 페이지(표본)를 390px로 캡처."""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time, json

os.environ["SELLER_CONSOLE_AUTH"] = "0"

_ITEM = {
    "id": "it0", "title": "베이직 에코백 캔버스 데일리 숄더백 대용량",
    "url": "https://item.taobao.com/p0", "domain": "taobao.com",
    "price": "12900", "currency": "KRW", "image_url": "",
    "status": "ok", "source": "extension", "seller_id": "u1",
    "extra_json": json.dumps({
        "title_ko": "베이직 에코백 캔버스 데일리 숄더백 대용량",
        "description": "넉넉한 수납과 데일리 코디에 어울리는 캔버스 에코백.",
        "images": [], "options": [{"name": "색상", "values": ["블랙", "베이지"]}],
        "keywords": ["에코백", "캔버스백", "숄더백"], "category_code": "BAG",
    }),
}
import src.seller_console.views as views
views._get_owned_item = lambda item_id: dict(_ITEM)

from src.order_webhook import app

def run(): app.run(port=5089, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
out = sys.argv[1] if len(sys.argv) > 1 else "edit"
open_modal = (sys.argv[2] if len(sys.argv) > 2 else "0") == "1"

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
    p.goto('http://127.0.0.1:5089/seller/collect/preview/it0', wait_until='networkidle')
    _bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.wait_for_timeout(500)
    sw = p.evaluate("() => ({s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth})")
    if open_modal:
        # 업로드 모달 열기(있으면)
        try:
            p.evaluate("() => { var m=document.querySelector('.modal'); if(m){ m.classList.add('show'); m.style.display='block'; document.body.classList.add('modal-open'); } }")
            p.wait_for_timeout(400)
        except Exception:
            pass
    p.screenshot(path=f'/tmp/shot_{out}.png', full_page=not open_modal)
    b.close()
print(f'/tmp/shot_{out}.png', os.path.getsize(f'/tmp/shot_{out}.png'), 'page_overflow_x=', sw['s'] - sw['c'])
