"""개발용 모바일 스크린샷 — 주문 목록(표본)을 390px로 캡처(표→카드 대비)."""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time
from types import SimpleNamespace

os.environ["SELLER_CONSOLE_AUTH"] = "0"

_ORDERS = [
    {"marketplace": "coupang", "order_id": "CP-20260628-001", "placed_at": "2026-06-28T09:12",
     "items": [{"title": "베이직 에코백 캔버스 데일리 숄더백"}], "total_krw": 18900,
     "status": "paid", "tracking_no": "", "courier": ""},
    {"marketplace": "smartstore", "order_id": "SS-20260628-114", "placed_at": "2026-06-28T08:40",
     "items": [{"title": "프리미엄 가죽 토트백"}, {"title": "추가"}], "total_krw": 89000,
     "status": "shipped", "tracking_no": "1234567890", "courier": "CJ"},
    {"marketplace": "11st", "order_id": "11-20260627-552", "placed_at": "2026-06-27T19:05",
     "items": [{"title": "캐주얼 크로스백 미니"}], "total_krw": 23500,
     "status": "delivered", "tracking_no": "9988776655", "courier": "한진"},
]
import src.seller_console.views as views
_KPI = {"today_new": 1, "pending_ship": 1, "shipped": 1, "returned_exchanged": 0, "source": "demo"}
_svc = SimpleNamespace(
    list_orders=lambda **k: [SimpleNamespace(to_dict=lambda d=d: dict(d)) for d in _ORDERS],
    kpi_summary=lambda: dict(_KPI),
)
views._get_order_sync_service = lambda: _svc

from src.order_webhook import app

def run(): app.run(port=5090, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
out = sys.argv[1] if len(sys.argv) > 1 else "orders"

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
    p.goto('http://127.0.0.1:5090/seller/orders', wait_until='networkidle')
    _bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.wait_for_timeout(600)
    sw = p.evaluate("() => ({s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth})")
    loc = p.locator('.table-responsive').first
    (loc if loc.count() else p).screenshot(path=f'/tmp/shot_{out}.png')
    b.close()
print(f'/tmp/shot_{out}.png', os.path.getsize(f'/tmp/shot_{out}.png'), 'page_overflow_x=', sw['s'] - sw['c'])
