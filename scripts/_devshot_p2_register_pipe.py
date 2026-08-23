"""개발용 스크린샷 — 등록 파이프 P2: 실마진 + 배송(한국) 컬럼.

BEFORE(P1 검수표 — 마진=목표 근사·배송 컬럼 없음) vs AFTER(실마진 순이익·배송불가/가능/미검증·35% 위반 플래그).
_collect_real_draft + ship 훅 몽키패치로 실데이터·네트워크 없이 렌더.
"""
import os, sys, glob, threading, time, functools
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

import src.seller_console.views as V
import src.pipeline.register_pipe as RP

_DRAFTS = {
    "amazon":  {"title_ko": "니치 원목 트레이 테이블", "brand": "Craftly", "currency": "KRW", "price_original": 32900,
                "images": ["https://picsum.photos/seed/a/200"]},
    "alpaka":  {"title_ko": "ALPAKA Metro 백팩 방수", "brand": "ALPAKA", "currency": "KRW", "price_original": 189000,
                "images": ["https://picsum.photos/seed/b/200"]},
    "bulky":   {"title_ko": "대형 캠핑 폴딩 왜건", "brand": "TrailPro", "currency": "KRW", "price_original": 80000,
                "images": ["https://picsum.photos/seed/d/200"]},
    "kr":      {"title_ko": "니치 가죽 카드지갑", "brand": "Ystudio", "currency": "KRW", "price_original": 45000,
                "images": ["https://picsum.photos/seed/e/200"]},
}
def _fake_collect(url, translate=True):
    for k, d in _DRAFTS.items():
        if k in url:
            return d
    return None
V._collect_real_draft = _fake_collect

# 데모용 배송 훅: kr=KR 셀렉터 있음(배송가능), bulky=배송비 40%(35% 위반), 그 외 미조회.
def _ship_check(url):
    return (200, '<option value="KR">Korea</option>') if "kr" in url else (200, '<option value="US">US</option>' if "bulky" in url else "")
def _ship_cost(cost_krw=0, brand="", title="", url=""):
    return round(cost_krw * 0.40) if "bulky" in (url or "") else None

_orig = RP.build_source_review
def _patched(*a, **k):
    k.setdefault("ship_check_fn", _ship_check)
    k.setdefault("ship_cost_fn", _ship_cost)
    return _orig(*a, **k)
RP.build_source_review = _patched

from src.order_webhook import app
app.jinja_env.auto_reload = True
app.jinja_env.cache = {}

def run(): app.run(port=5097, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def shot(path, patched=True):
    # BEFORE = P1 원본(배송/실마진 없음), AFTER = P2 패치.
    RP.build_source_review = _patched if patched else _orig
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY')
        opts = {'executable_path': exe}
        if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**opts)
        ctx = b.new_context(viewport={'width': 1100, 'height': 900}, ignore_https_errors=True,
                            service_workers='block')
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5097/seller/sourcing/register-pipe", wait_until="networkidle")
        p.fill("#urls", "https://amazon.com/dp/1\nhttps://alpaka.example/2\nhttps://bulky.example/3\nhttps://kr.shop/4")
        p.click("form[action='/seller/sourcing/register-pipe'] button[type=submit]")
        p.wait_for_load_state("networkidle")
        p.wait_for_timeout(800)
        if os.path.exists(_bs):
            p.add_style_tag(path=_bs)
        p.wait_for_timeout(400)
        el = p.query_selector("table.pc-swiss-table") or p.query_selector("main") or p
        el.scroll_into_view_if_needed()
        p.wait_for_timeout(200)
        el.screenshot(path=path)
        b.close()

shot("/tmp/p2_before.png", patched=False)
shot("/tmp/p2_after.png", patched=True)

from PIL import Image, ImageDraw
def fit(p, w=560):
    im = Image.open(p).convert("RGB"); r = w/im.width
    return im.resize((w, int(im.height*r)))
a, bmg = fit("/tmp/p2_before.png"), fit("/tmp/p2_after.png")
band = 30
H = max(a.height, bmg.height) + band + 8
canvas = Image.new("RGB", (a.width + bmg.width + 24, H), "white")
d = ImageDraw.Draw(canvas)
d.text((8, 8), "BEFORE — 배송 미조회(미검증·배송비 미반영) · 전례 배송불가만", fill=(150, 60, 60))
d.text((a.width + 20, 8), "AFTER — 실측 배송판정(KR)·배송비 반영 실마진·35% 위반 플래그", fill=(17, 154, 142))
canvas.paste(a, (8, band)); canvas.paste(bmg, (a.width + 20, band))
os.makedirs("docs/screens/regpipe", exist_ok=True)
canvas.save("docs/screens/regpipe/p2-register-pipe.png")
print("saved docs/screens/regpipe/p2-register-pipe.png")
