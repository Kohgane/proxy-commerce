"""개발용 스크린샷(단일 상태) — /seller/settlement 렌더. OUT 경로 인자.

주문 소스를 몽키패치(complete 순이익 + 미입력 혼합)해 실계산 결과가 보이게.
BEFORE/AFTER는 git stash로 코드 상태를 바꿔 두 번 호출.
"""
import os, sys, glob
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ["FX_DISABLE_NETWORK"] = "1"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/settle.png"


class _O:
    def __init__(self, d): self._d = d
    def to_dict(self): return dict(self._d)


ORDERS = [
    _O({"order_id": "20260821-0001", "marketplace": "coupang", "total_krw": "58000",
        "shipping_fee_krw": "3000", "landed_cost_krw": "32000", "items": []}),
    _O({"order_id": "20260821-0002", "marketplace": "smartstore", "total_krw": "42000",
        "shipping_fee_krw": "0", "landed_cost_krw": "26500", "items": []}),
    _O({"order_id": "20260820-0044", "marketplace": "11st", "total_krw": "31900",
        "shipping_fee_krw": "0", "items": [{"sku": "NOLINK", "qty": 1}]}),   # 원가 미연결 → 미입력
    _O({"order_id": "20260820-0031", "marketplace": "kohganemultishop", "total_krw": "75000",
        "shipping_fee_krw": "0", "landed_cost_krw": "41000", "items": []}),
]

import src.seller_console.orders.sync_service as ss
class _Svc:
    def list_orders(self, limit=200, offset=0): return list(ORDERS)
    def kpi_summary(self): return {"today_new": 2, "pending_ship": 1, "shipped": 1, "returned_exchanged": 0}
ss.OrderSyncService = _Svc

from src.order_webhook import app
app.jinja_env.cache = {}

import threading, time
def run(): app.run(port=5096, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY')
    opts = {'executable_path': exe}
    if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**opts)
    ctx = b.new_context(viewport={'width': 1000, 'height': 900}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto("http://127.0.0.1:5096/seller/settlement", wait_until="networkidle")
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.wait_for_timeout(700)
    (p.query_selector("main") or p).screenshot(path=OUT)
    b.close()
print("saved", OUT)
