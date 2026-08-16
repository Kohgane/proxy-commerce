"""개발용 스크린샷 — v87-X2 한눈에 보기(수집 이력) 에디토리얼 격상.

BEFORE(제네릭 h3 헤더) vs AFTER(오버라인 금 라벨+세리프+금 헤어라인). 상태 다양성이
보이도록 mock 아이템(정상·번역완료·가격확인·보관) 주입. collect_history.html HEAD↔작업본 스왑.
"""
import os, sys, glob, threading, time, subprocess
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

import src.seller_console.views as views
views._seller_identities = lambda: {"u1"}
views._seller_id = lambda: "u1"
from src.seller_console import collect_history_store as ch
ch._in_memory.clear()

def add(title, price, cur, extra):
    return ch.append(source="extension", url="https://item.rakuten.co.jp/x/" + title[:3],
                     title=title, price=price, currency=cur, seller_id="u1", extra=extra)

add("TSUMUGI 천연목 레코드 보관함 · 오크", "61144", "KRW", {"translated": True, "title_ko": "TSUMUGI 천연목 레코드 보관함 · 오크"})
add("Folding car tray table portable", "", "USD", {"price_status": "needs_check"})
add("스테인리스 진공 텀블러 500ml", "18900", "KRW", {"translated": True})
add("빈티지 캔버스 메신저백", "31000", "KRW", {"status": "archived"})

CH = "src/seller_console/templates/collect_history.html"
NEW = open(CH, encoding="utf-8").read()
OLD = subprocess.check_output(["git", "show", "HEAD:" + CH]).decode("utf-8")

from src.order_webhook import app
app.jinja_env.auto_reload = True
app.jinja_env.cache = {}
def run(): app.run(port=5095, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "seller"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def shot(body, path):
    open(CH, "w", encoding="utf-8").write(body)
    app.jinja_env.cache = {}
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY')
        o = {'executable_path': exe}
        if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**o)
        ctx = b.new_context(viewport={'width': 940, 'height': 820}, ignore_https_errors=True)
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5095/seller/collect/history", wait_until="networkidle")
        if os.path.exists(_bs): p.add_style_tag(path=_bs)
        p.wait_for_timeout(500)
        (p.query_selector("main") or p).screenshot(path=path)
        b.close()

try:
    shot(OLD, "/tmp/kl_before.png")
    shot(NEW, "/tmp/kl_after.png")
finally:
    open(CH, "w", encoding="utf-8").write(NEW)

from PIL import Image, ImageDraw
def fit(p, w=520):
    im = Image.open(p).convert("RGB"); r = w / im.width
    return im.resize((w, int(im.height * r)))
a, bmg = fit("/tmp/kl_before.png"), fit("/tmp/kl_after.png")
band = 30
H = max(a.height, bmg.height) + band + 8
canvas = Image.new("RGB", (a.width + bmg.width + 24, H), "white")
d = ImageDraw.Draw(canvas)
d.text((8, 8), "BEFORE — 제네릭 h3 헤더", fill=(150, 60, 60))
d.text((a.width + 24, 8), "AFTER — 오버라인 금 라벨 · 세리프 · 금 헤어라인", fill=(40, 110, 100))
canvas.paste(a, (0, band + 8)); canvas.paste(bmg, (a.width + 24, band + 8))
out = sys.argv[1] if len(sys.argv) > 1 else "docs/screens/v87x2/x2-killist.png"
os.makedirs(os.path.dirname(out), exist_ok=True)
canvas.save(out)
print("saved", out)
