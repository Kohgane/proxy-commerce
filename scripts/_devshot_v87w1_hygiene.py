"""개발용 스크린샷 — v87-W1 수집 목록 위생: 정리 후보 뷰.

좌: 일반 목록('비상품 의심' 배지 + '정리 후보 보기' 진입) / 우: 정리 후보 필터 뷰
(안내 배너 + 후보만 + '선택 보관(복원 가능)'). 삭제 아님을 명시.
"""
import os, sys, glob, threading, time, json
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

import src.seller_console.views as views
views._seller_id = lambda: "u1"
views._seller_identities = lambda: {"u1"}
import src.seller_console.collect_history_store as ch
ch._in_memory.clear()

ROWS = [
    ("https://www.temu.com/kr/g-601104878115983.html", "큐브 RGB 조명 무선 스피커", "12730", "KRW", "https://img.kwcdn.com/a.jpg", {"images": ["a"], "options": [{"name": "색"}]}),
    ("https://item.rakuten.co.jp/shop/abc/", "요시다 가방 블랙", "17800", "JPY", "https://x/y.jpg", {"images": ["a"]}),
    ("https://www.icloud.com/mail/", "iCloud Mail", "", "", "", {}),
    ("https://chatgpt.com/c/6f2a-abc", "ChatGPT", "", "", "", {}),
    ("https://mail.google.com/mail/u/0/#inbox", "받은편지함 (2,144)", "", "", "", {}),
    ("https://www.google.com/search?q=bluetooth+speaker", "bluetooth speaker - Google 검색", "", "", "", {}),
    ("https://blog.naver.com/someone/223", "무선스피커 추천 후기 블로그", "", "", "", {}),
]
for url, title, price, cur, img, extra in ROWS:
    ch.append(source="extension", url=url, title=title, image=img, price=price, currency=cur, extra=extra, seller_id="u1")

from src.order_webhook import app
app.jinja_env.cache = {}
def run(): app.run(port=5087, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def shot(qs, path):
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY')
        opts = {'executable_path': exe}
        if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**opts)
        ctx = b.new_context(viewport={'width': 980, 'height': 900}, ignore_https_errors=True)
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5087/seller/collect/history" + qs, wait_until="networkidle")
        if os.path.exists(_bs):
            p.add_style_tag(path=_bs)
        p.wait_for_timeout(700)
        (p.query_selector("main") or p).screenshot(path=path)
        b.close()

shot("?days=3650", "/tmp/hyg_before.png")
shot("?days=3650&hygiene=cleanup", "/tmp/hyg_after.png")

from PIL import Image, ImageDraw
def fit(p, w=520):
    im = Image.open(p).convert("RGB"); r = w/im.width
    return im.resize((w, int(im.height*r)))
a, bmg = fit("/tmp/hyg_before.png"), fit("/tmp/hyg_after.png")
band = 30
H = max(a.height, bmg.height) + band + 8
canvas = Image.new("RGB", (a.width + bmg.width + 24, H), "white")
d = ImageDraw.Draw(canvas)
d.text((8, 8), "일반 목록 — '비상품 의심' 배지 + '정리 후보 보기' 진입", fill=(120, 90, 20))
d.text((a.width + 20, 8), "정리 후보 — 안내 배너 + 후보만 + '선택 보관(복원 가능)'", fill=(17, 154, 142))
canvas.paste(a, (8, band)); canvas.paste(bmg, (a.width + 20, band))
os.makedirs("docs/screens/v87w1", exist_ok=True)
canvas.save("docs/screens/v87w1/v87w1-hygiene.png")
print("saved docs/screens/v87w1/v87w1-hygiene.png")
