"""개발용 스크린샷 — v86-R 상품 카탈로그 에디토리얼 격상.

BEFORE(제네릭 h4 + 부트스트랩 badge bg-*) vs AFTER(오버라인+금 헤어라인 + pc-badge 청록/주황/
적/뮤트). 같은 앱에서 catalog.html/catalog_rows.html을 스왑해 두 상태 촬영. 상태별 뱃지가 다
보이도록 mock 아이템 주입.
"""
import os, sys, glob, threading, time, subprocess
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

CAT = "src/seller_console/templates/catalog.html"
ROWS = "src/seller_console/templates/catalog_rows.html"
CAT_NEW, ROWS_NEW = open(CAT, encoding="utf-8").read(), open(ROWS, encoding="utf-8").read()
CAT_OLD = subprocess.check_output(["git", "show", "HEAD:" + CAT]).decode("utf-8")
ROWS_OLD = subprocess.check_output(["git", "show", "HEAD:" + ROWS]).decode("utf-8")

import src.seller_console.market_status_sheets as mss
from datetime import datetime
NOW = datetime(2026, 8, 11, 9, 30)

def _it(mp, pid, title, state, price, cur="KRW"):
    return mss.MarketStatusItem(marketplace=mp, product_id=pid, state=state, sku=pid.upper(),
                                title=title, price=price, currency=cur, price_krw=int(price),
                                last_synced_at=NOW)

ITEMS = [
    _it("coupang", "c101", "린넨 3인용 소파 · 내추럴 베이지", "active", 289000),
    _it("smartstore", "s202", "접이식 차량용 트레이 테이블", "out_of_stock", 32900),
    _it("11st", "e303", "무선 블루투스 스피커 방수", "error", 45900),
    _it("coupang", "c404", "스텐 텀블러 500ml 진공", "price_anomaly", 18900),
    _it("smartstore", "s505", "강아지 자동 급식기", "suspended", 79000),
    _it("shopee", "p606", "우드 케이스 무선 충전패드", "active", 26000),  # 준비 중(미ready 마켓)
]

def _fake_fetch_all(self):
    return mss.AllMarketStatus(summaries=[], items=list(ITEMS), source="mock")
mss.MarketStatusSheetsAdapter.fetch_all = _fake_fetch_all

from src.order_webhook import app
app.jinja_env.auto_reload = True
app.jinja_env.cache = {}
app.config["TEMPLATES_AUTO_RELOAD"] = True

def run(): app.run(port=5097, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def shot(cat, rows, path):
    open(CAT, "w", encoding="utf-8").write(cat)
    open(ROWS, "w", encoding="utf-8").write(rows)
    app.jinja_env.cache = {}
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY')
        opts = {'executable_path': exe}
        if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**opts)
        ctx = b.new_context(viewport={'width': 940, 'height': 720}, ignore_https_errors=True)
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5097/seller/catalog", wait_until="networkidle")
        if os.path.exists(_bs):
            p.add_style_tag(path=_bs)
        p.wait_for_timeout(600)
        (p.query_selector("main") or p).screenshot(path=path)
        b.close()

try:
    shot(CAT_OLD, ROWS_OLD, "/tmp/cat_before.png")
    shot(CAT_NEW, ROWS_NEW, "/tmp/cat_after.png")
finally:
    open(CAT, "w", encoding="utf-8").write(CAT_NEW)
    open(ROWS, "w", encoding="utf-8").write(ROWS_NEW)

from PIL import Image, ImageDraw
def fit(p, w=520):
    im = Image.open(p).convert("RGB"); r = w/im.width
    return im.resize((w, int(im.height*r)))
a, bmg = fit("/tmp/cat_before.png"), fit("/tmp/cat_after.png")
band = 30
H = max(a.height, bmg.height) + band + 8
canvas = Image.new("RGB", (a.width + bmg.width + 24, H), "white")
d = ImageDraw.Draw(canvas)
d.text((8, 8), "BEFORE — 제네릭 h4 · 부트스트랩 badge bg-*", fill=(150, 60, 60))
d.text((a.width + 20, 8), "AFTER — 오버라인+금 헤어라인 · pc-badge(청록/주황/적/뮤트)", fill=(17, 154, 142))
canvas.paste(a, (8, band)); canvas.paste(bmg, (a.width + 20, band))
os.makedirs("docs/screens/v86r", exist_ok=True)
canvas.save("docs/screens/v86r/v86r-catalog.png")
print("saved docs/screens/v86r/v86r-catalog.png")
