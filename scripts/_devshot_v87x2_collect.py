"""개발용 스크린샷 — v87-X2 상품 수집(manual_collect) 에디토리얼 격상.

BEFORE(제네릭 h1.h4 + alert-info/alert-light + text-primary 파랑) vs
AFTER(오버라인 금 라벨 + 세리프 헤더 + 금 헤어라인 + pc-status + text-teal).
같은 앱에서 manual_collect.html을 HEAD↔작업본 스왑해 두 상태 촬영(실행 결과만 렌더).
"""
import os, sys, glob, threading, time, subprocess
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

MC = "src/seller_console/templates/manual_collect.html"
NEW = open(MC, encoding="utf-8").read()
OLD = subprocess.check_output(["git", "show", "origin/main:" + MC]).decode("utf-8")

from src.order_webhook import app
app.jinja_env.auto_reload = True
app.jinja_env.cache = {}
app.config["TEMPLATES_AUTO_RELOAD"] = True

def run(): app.run(port=5098, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "seller"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def shot(body, path):
    open(MC, "w", encoding="utf-8").write(body)
    app.jinja_env.cache = {}
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY')
        opts = {'executable_path': exe}
        if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**opts)
        ctx = b.new_context(viewport={'width': 940, 'height': 900}, ignore_https_errors=True)
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5098/seller/collect", wait_until="networkidle")
        if os.path.exists(_bs):
            p.add_style_tag(path=_bs)
        p.wait_for_timeout(600)
        (p.query_selector("main") or p).screenshot(path=path)
        b.close()

try:
    shot(OLD, "/tmp/mc_before.png")
    shot(NEW, "/tmp/mc_after.png")
finally:
    open(MC, "w", encoding="utf-8").write(NEW)

from PIL import Image, ImageDraw
def fit(p, w=520):
    im = Image.open(p).convert("RGB"); r = w / im.width
    return im.resize((w, int(im.height * r)))
a, bmg = fit("/tmp/mc_before.png"), fit("/tmp/mc_after.png")
band = 30
H = max(a.height, bmg.height) + band + 8
canvas = Image.new("RGB", (a.width + bmg.width + 24, H), "white")
d = ImageDraw.Draw(canvas)
d.text((8, 8), "BEFORE — 제네릭 h4 · alert-info/light · text-primary(파랑)", fill=(150, 60, 60))
d.text((a.width + 24, 8), "AFTER — 오버라인 금 라벨 · 세리프 · 금 헤어라인 · pc-status · text-teal", fill=(40, 110, 100))
canvas.paste(a, (0, band + 8))
canvas.paste(bmg, (a.width + 24, band + 8))
out = sys.argv[1] if len(sys.argv) > 1 else "docs/screens/v87x2/x2-collect.png"
os.makedirs(os.path.dirname(out), exist_ok=True)
canvas.save(out)
print("saved", out)
