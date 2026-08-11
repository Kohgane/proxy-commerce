"""개발용 스크린샷 — v86-P 알림 설정 화면 정직화 + 에디토리얼 격상.

BEFORE(제네릭 h4 + 부트스트랩 badge + env-var 노출) vs AFTER(오버라인+금 헤어라인 +
gogabridj pc-badge 청록/주황 + 평문 카피). 같은 앱에서 템플릿 파일을 스왑해 두 상태 촬영.
"""
import os, sys, glob, threading, time, subprocess
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

TPL = "src/seller_console/templates/notifications.html"
NEW = open(TPL, encoding="utf-8").read()
OLD = subprocess.check_output(["git", "show", "HEAD:" + TPL]).decode("utf-8")

# 텔레그램=연결됨, 이메일=미연결 → 두 뱃지 변형이 한 화면에 보이게.
from src.utils import env_catalog
env_catalog.is_active = lambda k: (k == "telegram")

from src.order_webhook import app
app.jinja_env.auto_reload = True
app.jinja_env.cache = {}
app.config["TEMPLATES_AUTO_RELOAD"] = True

def run(): app.run(port=5096, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def shot(which, path):
    open(TPL, "w", encoding="utf-8").write(which)
    app.jinja_env.cache = {}
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY')
        opts = {'executable_path': exe}
        if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**opts)
        ctx = b.new_context(viewport={'width': 760, 'height': 900}, ignore_https_errors=True)
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5096/seller/notifications", wait_until="networkidle")
        if os.path.exists(_bs):
            p.add_style_tag(path=_bs)
        p.wait_for_timeout(500)
        main = p.query_selector("main") or p
        main.screenshot(path=path)
        b.close()

try:
    shot(OLD, "/tmp/notif_before.png")
    shot(NEW, "/tmp/notif_after.png")
finally:
    open(TPL, "w", encoding="utf-8").write(NEW)   # 원복 보장

from PIL import Image, ImageDraw
def fit(p, w=430):
    im = Image.open(p).convert("RGB"); r = w/im.width
    return im.resize((w, int(im.height*r)))
a, bmg = fit("/tmp/notif_before.png"), fit("/tmp/notif_after.png")
band = 30
H = max(a.height, bmg.height) + band + 8
canvas = Image.new("RGB", (a.width + bmg.width + 24, H), "white")
d = ImageDraw.Draw(canvas)
d.text((8, 8), "BEFORE — 제네릭 h4 · 부트스트랩 뱃지 · env-var 노출", fill=(150, 60, 60))
d.text((a.width + 20, 8), "AFTER — 오버라인+금 헤어라인 · pc-badge · 평문", fill=(17, 154, 142))
canvas.paste(a, (8, band))
canvas.paste(bmg, (a.width + 20, band))
os.makedirs("docs/screens/v86p", exist_ok=True)
canvas.save("docs/screens/v86p/v86p-notifications.png")
print("saved docs/screens/v86p/v86p-notifications.png")
