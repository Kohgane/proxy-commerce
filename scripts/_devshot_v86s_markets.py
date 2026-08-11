"""개발용 스크린샷 — v86-S 마켓 현황 상태뱃지 격상.

BEFORE(부트스트랩 badge bg-*) vs AFTER(pc-badge 청록/주황/적/뮤트). markets.html 상품 상태 표.
get_all을 live 소스+아이템으로 몽키패치해 상태별 뱃지가 다 보이게.
"""
import os, sys, glob, threading, time, subprocess
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

MK = "src/seller_console/templates/markets.html"
MK_NEW = open(MK, encoding="utf-8").read()
MK_OLD = subprocess.check_output(["git", "show", "HEAD:" + MK]).decode("utf-8")

import src.seller_console.market_status as ms
import src.seller_console.market_status_service as mss
from datetime import datetime
NOW = datetime(2026, 8, 11, 9, 30)

def _it(mp, pid, title, state, price):
    return ms.MarketStatusItem(marketplace=mp, product_id=pid, state=state, sku=pid.upper(),
                               title=title, price=price, currency="KRW", price_krw=int(price),
                               last_synced_at=NOW)

ITEMS = [
    _it("coupang", "c101", "린넨 3인용 소파 내추럴 베이지", "active", 289000),
    _it("smartstore", "s202", "접이식 차량용 트레이 테이블", "out_of_stock", 32900),
    _it("11st", "e303", "무선 블루투스 스피커 방수", "error", 45900),
    _it("coupang", "c404", "스텐 텀블러 500ml 진공", "price_anomaly", 18900),
    _it("smartstore", "s505", "강아지 자동 급식기", "suspended", 79000),
]
SUMS = [
    ms.MarketStatusSummary(marketplace="coupang", active=12, out_of_stock=1, error=0, total=13, source="live"),
    ms.MarketStatusSummary(marketplace="smartstore", active=8, out_of_stock=2, error=0, total=10, source="live"),
]

def _fake_get_all(self, force_refresh=False):
    return ms.AllMarketStatus(summaries=list(SUMS), items=list(ITEMS), fetched_at=NOW, source="live")
mss.MarketStatusService.get_all = _fake_get_all

from src.order_webhook import app
app.jinja_env.auto_reload = True
app.jinja_env.cache = {}
app.config["TEMPLATES_AUTO_RELOAD"] = True

def run(): app.run(port=5098, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def shot(mk, path):
    open(MK, "w", encoding="utf-8").write(mk)
    app.jinja_env.cache = {}
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY')
        opts = {'executable_path': exe}
        if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**opts)
        ctx = b.new_context(viewport={'width': 960, 'height': 900}, ignore_https_errors=True)
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5098/seller/markets", wait_until="networkidle")
        if os.path.exists(_bs):
            p.add_style_tag(path=_bs)
        p.wait_for_timeout(700)
        tbl = p.query_selector("#productTableBody")
        # 상태 표가 보이도록 그 조상 카드 캡처(없으면 main).
        target = None
        if tbl:
            target = p.evaluate_handle("el => el.closest('.card')", tbl).as_element()
        (target or p.query_selector("main") or p).screenshot(path=path)
        b.close()

try:
    shot(MK_OLD, "/tmp/mk_before.png")
    shot(MK_NEW, "/tmp/mk_after.png")
finally:
    open(MK, "w", encoding="utf-8").write(MK_NEW)

from PIL import Image, ImageDraw
def fit(p, w=520):
    im = Image.open(p).convert("RGB"); r = w/im.width
    return im.resize((w, int(im.height*r)))
a, bmg = fit("/tmp/mk_before.png"), fit("/tmp/mk_after.png")
band = 30
H = max(a.height, bmg.height) + band + 8
canvas = Image.new("RGB", (a.width + bmg.width + 24, H), "white")
d = ImageDraw.Draw(canvas)
d.text((8, 8), "BEFORE — 부트스트랩 badge bg-*", fill=(150, 60, 60))
d.text((a.width + 20, 8), "AFTER — pc-badge(청록/주황/적/뮤트) · '가격 이상'", fill=(17, 154, 142))
canvas.paste(a, (8, band)); canvas.paste(bmg, (a.width + 20, band))
os.makedirs("docs/screens/v86s", exist_ok=True)
canvas.save("docs/screens/v86s/v86s-markets.png")
print("saved docs/screens/v86s/v86s-markets.png")
