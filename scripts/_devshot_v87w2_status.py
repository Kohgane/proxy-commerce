"""개발용 스크린샷 — v87-W2-impl 주문 상태 계층색 + 비색 단서 + 색약(그레이스케일) 재검증.

BEFORE(부트스트랩 무순서 색 뱃지) vs AFTER(진행=금+도트1~4·완료=청록+체크·취소=먹뮤트·되돌림=브론즈+↺)
+ AFTER를 그레이스케일로 변환해 '색 없이도 구분되는가' 실증(도트 수·아이콘 생존).
orders.html + app.css + _status_badge.html을 origin/main↔작업본 스왑.
"""
import os, sys, glob, threading, time, subprocess
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

import src.seller_console.views as views

_STATUSES = ["new", "paid", "preparing", "shipped", "delivered", "canceled", "returned", "exchanged", "refund_requested"]
_MP = ["coupang", "smartstore", "11st", "coupang", "smartstore", "11st", "coupang", "smartstore", "11st"]

class _O:
    def __init__(self, i, st, mp):
        self._d = {"marketplace": mp, "order_id": f"ORD-{1000+i}", "placed_at": "2026-08-16T09:30",
                   "items": [{"title": "린넨 3인 소파 · 아이보리"}], "total_krw": 289000 + i * 1000,
                   "status": st, "tracking_no": "", "courier": ""}
    def to_dict(self): return dict(self._d)

class _Svc:
    def list_orders(self, filters=None, limit=50, offset=0):
        return [_O(i, st, mp) for i, (st, mp) in enumerate(zip(_STATUSES, _MP))]
    def kpi_summary(self):
        return {"today_new": 1, "pending_ship": 2, "shipped": 1, "returned_exchanged": 3, "source": "mock"}

views._get_order_sync_service = lambda: _Svc()
views._order_source_info = lambda od: {"linked": False, "sourced": False, "copy_text": "", "source_url": ""}

FILES = ["src/seller_console/templates/orders.html", "src/static/app.css",
         "src/seller_console/templates/_status_badge.html"]
NEW = {f: open(f, encoding="utf-8").read() for f in FILES}
def _old(f):
    try: return subprocess.check_output(["git", "show", "origin/main:" + f]).decode("utf-8")
    except subprocess.CalledProcessError: return None   # 신규 파일은 origin/main에 없음
OLD = {f: _old(f) for f in FILES}

from src.order_webhook import app
app.jinja_env.auto_reload = True
app.jinja_env.cache = {}
def run(): app.run(port=5094, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "seller"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def _write(state):
    for f in FILES:
        body = state[f]
        if body is None:
            if os.path.exists(f): os.remove(f)
        else:
            open(f, "w", encoding="utf-8").write(body)
    app.jinja_env.cache = {}

def shot(state, path, grayscale=False):
    _write(state)
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY')
        o = {'executable_path': exe}
        if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**o)
        ctx = b.new_context(viewport={'width': 560, 'height': 720}, ignore_https_errors=True)
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5094/seller/orders", wait_until="networkidle")
        if os.path.exists(_bs): p.add_style_tag(path=_bs)
        if grayscale:
            p.add_style_tag(content="html{filter:grayscale(1)!important}")
        p.wait_for_timeout(500)
        # 상태 열만 좁게: 테이블 캡처
        el = p.query_selector("table") or p.query_selector("main") or p
        el.screenshot(path=path)
        b.close()

try:
    shot(OLD, "/tmp/w2_before.png")
    shot(NEW, "/tmp/w2_after.png")
    shot(NEW, "/tmp/w2_gray.png", grayscale=True)
finally:
    _write(NEW)

from PIL import Image, ImageDraw
def fit(p, w=440):
    im = Image.open(p).convert("RGB"); r = w / im.width
    return im.resize((w, int(im.height * r)))
a, bmg, g = fit("/tmp/w2_before.png"), fit("/tmp/w2_after.png"), fit("/tmp/w2_gray.png")
band = 28
H = max(a.height, bmg.height, g.height) + band + 8
canvas = Image.new("RGB", (a.width + bmg.width + g.width + 36, H), "white")
d = ImageDraw.Draw(canvas)
d.text((6, 8), "BEFORE — 부트스트랩 무순서 색", fill=(150, 60, 60))
d.text((a.width + 18, 8), "AFTER — 계층색+도트/아이콘", fill=(40, 110, 100))
d.text((a.width + bmg.width + 30, 8), "AFTER 그레이스케일(색약) — 도트/아이콘 생존", fill=(70, 70, 70))
canvas.paste(a, (0, band + 8)); canvas.paste(bmg, (a.width + 18, band + 8))
canvas.paste(g, (a.width + bmg.width + 30, band + 8))
out = sys.argv[1] if len(sys.argv) > 1 else "docs/screens/v87w2impl/w2-impl-status.png"
os.makedirs(os.path.dirname(out), exist_ok=True)
canvas.save(out)
print("saved", out)
