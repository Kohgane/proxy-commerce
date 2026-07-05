"""개발용 스크린샷 — 인덱스 패스트 스크롤(카탈로그 500+): 데스크탑 클릭 점프·모바일 스크럽+버블·sticky 헤더."""
import os, sys, glob, threading, time
from types import SimpleNamespace
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

import src.seller_console.views as views

# 500+ 항목(초성/A-Z/# 고르게)
NAMES_KO = ["가방","강아지","고무장갑","나무도마","냄비","다리미","라텍스베개","마우스패드","바구니","밥솥",
            "사다리","수건","아령","우산","자석","전구","차량용거치대","책상",
            "파우치","프라이팬","하모니카","화분","끈","뜨개바늘","빨래집게","쌀통","짜장","깔개"]
NAMES_EN = ["Apple case","Blender","Camera","Desk lamp","Earbuds","Frame","Grinder","Hanger","Iron","Jar",
            "Kettle","Ladle","Mixer","Notebook","Organizer","Pillow","Ruler","Scale","Tumbler",
            "Umbrella","Vase","Whisk","Yoga mat","Zipper bag"]
NAMES_NUM = ["3단 선반","2구 콘센트","1인용 텐트","#해시 상품","7080 소품"]
pool = NAMES_KO + NAMES_EN + NAMES_NUM
items = []
for i in range(520):
    base = pool[i % len(pool)]
    items.append(SimpleNamespace(
        marketplace="coupang", product_id=f"P{i:04d}", sku=f"SKU{i:04d}",
        state="active", last_synced_at=None,
        title=f"{base} {i//len(pool)+1}", title_ko=f"{base} {i//len(pool)+1}", title_en="",
        price=None, price_krw=1000 + i, currency="KRW"))

def fake_fetch_all(self):
    return SimpleNamespace(items=list(items), source="mock")

from src.seller_console.market_status_sheets import MarketStatusSheetsAdapter
MarketStatusSheetsAdapter.fetch_all = fake_fetch_all

from src.order_webhook import app
def run(): app.run(port=5097, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
_app = "src/static/app.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]

def shot(dev, actions, path, w, h):
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
        if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**o)
        ctx = b.new_context(viewport={'width': w, 'height': h}, ignore_https_errors=True,
                            is_mobile=(dev == "mobile"), has_touch=(dev == "mobile"))
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5097/seller/catalog?sort=title_asc", wait_until="networkidle")
        if os.path.exists(_bs): p.add_style_tag(path=_bs)
        p.wait_for_timeout(600)
        rail = p.query_selector(".kgp-fs-rail")
        info = {
            "rail": rail is not None,
            "letters": len(p.query_selector_all(".kgp-fs-letter")),
            "dim": len(p.query_selector_all(".kgp-fs-dim")),
            "heads": len(p.query_selector_all(".kgp-fs-head")),
            "items": len(p.query_selector_all(".kgp-fs-item")),
        }
        actions(p)
        p.wait_for_timeout(300)
        p.screenshot(path=path)
        b.close()
        return info

# 데스크탑: 'ㅊ' 글자 클릭 점프
def desktop_act(p):
    p.eval_on_selector_all(".kgp-fs-letter", "els=>{const t=els.find(e=>e.textContent==='ㅊ'); if(t)t.click();}")
info_d = shot("desktop", desktop_act, "/tmp/fs_desktop.png", 1200, 820)

# 모바일: 레일 스크럽 → 버블 표시(pointerdown + move on 'ㅅ' 위치)
def mobile_act(p):
    p.eval_on_selector(".kgp-fs-rail", """rail=>{
        const el=[...rail.children].find(e=>e.textContent==='ㅅ'); const r=el.getBoundingClientRect();
        const opt={clientX:r.left+5, clientY:r.top+5, bubbles:true};
        rail.dispatchEvent(new PointerEvent('pointerdown', opt));
        document.dispatchEvent(new PointerEvent('pointermove', opt));
    }""")
info_m = shot("mobile", mobile_act, "/tmp/fs_mobile.png", 412, 820)

print("desktop:", info_d)
print("mobile:", info_m)

# 합성: 좌 데스크탑 + 우 모바일
from PIL import Image, ImageDraw
d1 = Image.open("/tmp/fs_desktop.png").convert("RGB")
m1 = Image.open("/tmp/fs_mobile.png").convert("RGB")
# 데스크탑 상단 크롭
d1 = d1.crop((0, 0, d1.width, min(760, d1.height)))
# 모바일 크롭
m1 = m1.crop((0, 0, m1.width, min(760, m1.height)))
band = 60
W = d1.width + m1.width + 24
H = band + max(d1.height, m1.height) + 12
canvas = Image.new("RGB", (W, H), "white")
dr = ImageDraw.Draw(canvas)
teal, muted, orange = (17,154,142), (120,120,120), (245,130,31)
dr.text((16, 12), "인덱스 패스트 스크롤(폰 앱서랍 방식) — 카탈로그 520 항목 · 이름순", fill=teal)
dr.text((16, 32), f"레일 {info_d['letters']}글자(없는 글자 흐리게 {info_d['dim']}) · 섹션 sticky 헤더 {info_d['heads']}개 · 가상화 항목 {info_d['items']}",
        fill=muted)
canvas.paste(d1, (0, band))
canvas.paste(m1, (d1.width + 24, band))
dr.text((16, band + d1.height - 24), "◀ 데스크탑: 'ㅊ' 클릭 점프 + sticky 헤더", fill=orange)
dr.text((d1.width + 24, band + 4), "모바일: 레일 스크럽 → 'ㅅ' 버블 ▶", fill=orange)
os.makedirs("docs/screens/v45", exist_ok=True)
canvas.save("docs/screens/v45/fastscroll.png")
print("saved docs/screens/v45/fastscroll.png")
