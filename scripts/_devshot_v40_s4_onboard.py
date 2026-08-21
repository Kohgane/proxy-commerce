"""개발용 스크린샷 — 디자인 v2 Stage 4: 온보딩 카드 라벤더 default 제거 → 토큰(청록/금).

BEFORE(라벤더 보더/그라데이션) vs AFTER(금 헤어라인·청록 현재단계/완료). console.css 스왑.
대시보드 온보딩 스텝 카드(compute_onboarding_state)로 렌더.
"""
import os, sys, glob, threading, time, subprocess
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

CSS = "src/seller_console/static/console.css"
CSS_NEW = open(CSS, encoding="utf-8").read()
CSS_OLD = subprocess.check_output(["git", "show", "HEAD:" + CSS]).decode("utf-8")

from src.order_webhook import app
app.jinja_env.auto_reload = True
app.config["TEMPLATES_AUTO_RELOAD"] = True

def run(): app.run(port=5097, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

def shot(css, path):
    open(CSS, "w", encoding="utf-8").write(css)
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY')
        opts = {'executable_path': exe}
        if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**opts)
        ctx = b.new_context(viewport={'width': 980, 'height': 820}, ignore_https_errors=True)
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5097/seller/dashboard", wait_until="networkidle")
        if os.path.exists(_bs):
            p.add_style_tag(path=_bs)
        # 온보딩 카드가 있으면 그것, 없으면 스텝 카드/first card 폴백.
        p.wait_for_timeout(700)
        el = (p.query_selector(".console-onboarding-card") or p.query_selector(".onboarding-step-card")
              or p.query_selector(".card"))
        (el or p).screenshot(path=path)
        b.close()

try:
    shot(CSS_OLD, "/tmp/ob_before.png")
    shot(CSS_NEW, "/tmp/ob_after.png")
finally:
    open(CSS, "w", encoding="utf-8").write(CSS_NEW)

from PIL import Image, ImageDraw
def fit(p, w=460):
    im = Image.open(p).convert("RGB"); r = w/im.width
    return im.resize((w, int(im.height*r)))
a, bmg = fit("/tmp/ob_before.png"), fit("/tmp/ob_after.png")
band = 30
H = max(a.height, bmg.height) + band + 8
canvas = Image.new("RGB", (a.width + bmg.width + 24, H), "white")
d = ImageDraw.Draw(canvas)
d.text((8, 8), "BEFORE — 라벤더 default(보라 보더/그라데)", fill=(150, 60, 60))
d.text((a.width + 20, 8), "AFTER — 금 헤어라인 + 청록 현재/완료", fill=(17, 154, 142))
canvas.paste(a, (8, band)); canvas.paste(bmg, (a.width + 20, band))
os.makedirs("docs/screens/v40s4", exist_ok=True)
canvas.save("docs/screens/v40s4/onboarding-swiss.png")
print("saved docs/screens/v40s4/onboarding-swiss.png")
