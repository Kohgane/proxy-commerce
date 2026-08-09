"""개발용 스크린샷 — v45 P9 편집 드로어 칩 탭 분리(퍼센티 벤치마크·고가브릿지 토큰).

상품명·카테고리 / 가격 / 옵션 / 키워드 / 썸네일 / 상세페이지 / 업로드 7탭. 한 탭씩 표시.
탭별 캡처를 한 장으로 합성.
"""
import os, sys, glob, threading, time, base64
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

from src.seller_console import collect_history_store as ch
import src.seller_console.views as views
views._seller_identities = lambda: {"u1"}
views._seller_id = lambda: "u1"
ch._in_memory.clear()

def _img(color, label):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240">'
           f'<rect width="240" height="240" fill="{color}"/>'
           f'<text x="120" y="128" font-size="22" fill="#fff" text-anchor="middle" font-family="sans-serif">{label}</text></svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()

extra = {
    "title": "린넨 3인용 소파 · 내추럴 베이지",
    "description": "촘촘한 린넨 커버와 견고한 원목 프레임. 폭 200cm, 깊이 90cm. 커버 분리 세탁 가능.",
    "keywords": "소파, 린넨, 3인용, 거실가구, 내추럴",
    "currency": "KRW",
    "price": "289000",
    "images": [_img("#2f8f6f", "대표"), _img("#4a78c0", "갤러리2"), _img("#c07a2a", "갤러리3")],
    "detail_images": [_img("#7a5ca8", "상세1")],
    "options": [{"name": "색상", "values": "베이지, 그레이, 차콜"}, {"name": "구성", "values": "3인용, 4인용"}],
    "category_code": "HOM",
}
iid = ch.append(source="extension", url="https://temu.com/g-000111.html",
                title=extra["title"], image=extra["images"][0], price="289000", currency="KRW",
                extra=extra, seller_id="u1")

from src.order_webhook import app
def run(): app.run(port=5094, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

TABS = [("basic", "상품명·카테고리"), ("price", "가격"), ("options", "옵션"),
        ("keywords", "키워드"), ("thumb", "썸네일"), ("detail", "상세페이지"), ("upload", "업로드")]

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
shots = []
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY')
    opts = {'executable_path': exe}
    if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**opts)
    ctx = b.new_context(viewport={'width': 900, 'height': 720}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto(f"http://127.0.0.1:5094/seller/collect/preview/{iid}?drawer=1", wait_until="networkidle")
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.wait_for_timeout(500)
    for key, label in TABS:
        p.evaluate(f"kgpEtab('{key}')")
        p.wait_for_timeout(250)
        card = p.query_selector(".card")
        path = f"/tmp/shot_p9_{key}.png"
        (card or p).screenshot(path=path)
        shots.append((label, path))
    b.close()

from PIL import Image, ImageDraw
CW = 452
def fit(im):
    r = CW / im.width
    return im.resize((CW, int(im.height * r)))
imgs = [(lbl, fit(Image.open(pth).convert("RGB"))) for lbl, pth in shots]
band = 30
cols = 2
rows = (len(imgs) + cols - 1) // cols
colw = CW + 16
rowhs = []
for r in range(rows):
    rh = max(imgs[r*cols + c][1].height for c in range(cols) if r*cols + c < len(imgs))
    rowhs.append(rh + band + 12)
canvas = Image.new("RGB", (colw*cols + 8, sum(rowhs) + 8), "white")
d = ImageDraw.Draw(canvas)
y = 4
for r in range(rows):
    x = 4
    for c in range(cols):
        i = r*cols + c
        if i >= len(imgs): break
        lbl, im = imgs[i]
        d.text((x + 4, y + 8), f"[{lbl}] 탭", fill=(17, 154, 142))
        canvas.paste(im, (x, y + band))
        x += colw
    y += rowhs[r]
os.makedirs("docs/screens/v45", exist_ok=True)
canvas.save("docs/screens/v45/p9-drawer-tabs.png")
print("saved docs/screens/v45/p9-drawer-tabs.png ; tabs:", [t[0] for t in TABS])
