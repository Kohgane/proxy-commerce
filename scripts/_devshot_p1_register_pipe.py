"""개발용 스크린샷 — 등록 파이프 P1: 소싱 URL 검수 화면.

BEFORE(빈 입력) vs AFTER(검수표: 통과/취급제외/수집실패). _collect_real_draft 몽키패치로 실데이터 없이 렌더.
"""
import os, sys, glob, threading, time
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

import src.seller_console.views as V
_DRAFTS = {
    "amazon": {"title_ko": "접이식 차량용 트레이 테이블 대형", "currency": "KRW", "price_original": 32900,
               "images": ["https://picsum.photos/seed/a/200"]},
    "rakuten": {"title_ko": "스텐 텀블러 500ml 진공 이중", "currency": "KRW", "price_original": 18900,
                "images": ["https://picsum.photos/seed/b/200"]},
    "perfume": {"title_ko": "샤넬 향수 오드퍼퓸 100ml", "currency": "KRW", "price_original": 210000,
                "images": ["https://picsum.photos/seed/c/200"]},
}
def _fake_collect(url, translate=True):
    for k, d in _DRAFTS.items():
        if k in url:
            return d
    return None
V._collect_real_draft = _fake_collect

from src.order_webhook import app
app.jinja_env.auto_reload = True
app.jinja_env.cache = {}

def run(): app.run(port=5096, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def shot(path, post=False):
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY')
        opts = {'executable_path': exe}
        if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**opts)
        ctx = b.new_context(viewport={'width': 1000, 'height': 900}, ignore_https_errors=True,
                            service_workers='block')
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5096/seller/sourcing/register-pipe", wait_until="networkidle")
        if post:
            p.fill("#urls", "https://amazon.com/dp/1\nhttps://item.rakuten.co.jp/2\nhttps://shop/perfume/3\nhttps://blocked.example/4")
            p.click("form[action='/seller/sourcing/register-pipe'] button[type=submit]")
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(800)
        if os.path.exists(_bs):
            p.add_style_tag(path=_bs)
        p.wait_for_timeout(500)
        (p.query_selector("main") or p).screenshot(path=path)
        b.close()

shot("/tmp/p1_before.png", post=False)
shot("/tmp/p1_after.png", post=True)

from PIL import Image, ImageDraw
def fit(p, w=540):
    im = Image.open(p).convert("RGB"); r = w/im.width
    return im.resize((w, int(im.height*r)))
a, bmg = fit("/tmp/p1_before.png"), fit("/tmp/p1_after.png")
band = 30
H = max(a.height, bmg.height) + band + 8
canvas = Image.new("RGB", (a.width + bmg.width + 24, H), "white")
d = ImageDraw.Draw(canvas)
d.text((8, 8), "BEFORE — URL 입력(빈 검수표)", fill=(150, 60, 60))
d.text((a.width + 20, 8), "AFTER — 검수표(통과/취급제외/수집실패, 등록 없음)", fill=(17, 154, 142))
canvas.paste(a, (8, band)); canvas.paste(bmg, (a.width + 20, band))
os.makedirs("docs/screens/regpipe", exist_ok=True)
canvas.save("docs/screens/regpipe/p1-register-pipe.png")
print("saved docs/screens/regpipe/p1-register-pipe.png")
