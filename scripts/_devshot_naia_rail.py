"""개발용 스크린샷 — 나이아 인덱스 레일. 실제 모바일 뷰포트: 기본(최신순) 레일 노출·스크럽+버블·빈초성 dim."""
import os, sys, glob, threading, time
from types import SimpleNamespace
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

# 일부 초성/영문 일부러 비움 → dim + '아직 없음' 확인
NAMES = ["가방","가위","고무장갑","나무도마","냄비","다리미","라텍스베개","마우스패드","바구니",
         "사다리","수건","아령","우산","자석","전구","책상","하모니카","화분",
         "Apple case","Blender","Camera","Grinder","MOFT Stand","OHSNAP","Tumbler","3단 선반"]
items = []
for i in range(180):
    base = NAMES[i % len(NAMES)]
    items.append(SimpleNamespace(marketplace="coupang", product_id=f"P{i:04d}", sku=f"S{i:04d}",
        state="active", last_synced_at=None, title=f"{base} {i//len(NAMES)+1}",
        title_ko=f"{base} {i//len(NAMES)+1}", title_en="", price=None, price_krw=1000+i, currency="KRW"))
from src.seller_console.market_status_sheets import MarketStatusSheetsAdapter
MarketStatusSheetsAdapter.fetch_all = lambda self: SimpleNamespace(items=list(items), source="mock")

from src.order_webhook import app
threading.Thread(target=lambda: app.run(port=5098, use_reloader=False), daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def mobile_shot(url, act, path):
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
        if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**o)
        ctx = b.new_context(viewport={'width': 390, 'height': 780}, ignore_https_errors=True, is_mobile=True, has_touch=True)
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5098" + url, wait_until="networkidle")
        if os.path.exists(_bs): p.add_style_tag(path=_bs)
        p.wait_for_timeout(600)
        info = {"rail": p.query_selector(".kgp-fs-rail") is not None,
                "letters": len(p.query_selector_all(".kgp-fs-letter")),
                "dim": len(p.query_selector_all(".kgp-fs-dim")),
                "heads": len(p.query_selector_all(".kgp-fs-head")),
                "empty": len(p.query_selector_all(".kgp-fs-empty"))}
        if act: act(p)
        p.wait_for_timeout(300)
        p.screenshot(path=path)
        b.close()
        return info

# 1) 기본(최신순) — 레일 노출(그룹핑 없음)
i1 = mobile_shot("/seller/catalog?sort=last_synced_desc", None, "/tmp/naia1.png")
# 2) 이름순 — 스크럽 → 'ㅅ' 버블 + 빈 초성 dim
def scrub(p):
    p.eval_on_selector(".kgp-fs-rail", """rail=>{
      const el=[...rail.children].find(e=>e.textContent==='ㅅ'); const r=el.getBoundingClientRect();
      rail.dispatchEvent(new TouchEvent('touchstart',{bubbles:true,cancelable:true,touches:[new Touch({identifier:1,target:rail,clientX:r.left+8,clientY:r.top+4})]}));
      rail.dispatchEvent(new TouchEvent('touchmove',{bubbles:true,cancelable:true,touches:[new Touch({identifier:1,target:rail,clientX:r.left+8,clientY:r.top+4})]}));
    }""")
i2 = mobile_shot("/seller/catalog?sort=title_asc", scrub, "/tmp/naia2.png")
# 3) 이름순 상단(빈 초성 '아직 없음' + sticky 헤더)
i3 = mobile_shot("/seller/catalog?sort=title_asc", None, "/tmp/naia3.png")

print("default:", i1); print("scrub:", i2); print("namesort:", i3)

from PIL import Image, ImageDraw
imgs = [Image.open(f"/tmp/naia{n}.png").convert("RGB").crop((0,0,390,720)) for n in (1,2,3)]
band = 74; W = 390*3 + 32; H = band + 720 + 10
canvas = Image.new("RGB",(W,H),"white"); d = ImageDraw.Draw(canvas)
teal,muted,orange = (17,154,142),(120,120,120),(245,130,31)
d.text((16,12),"나이아 인덱스 레일 — 실제 모바일 뷰포트(390px). 레일 항상 노출·41글자·빈 초성 dim·대형 버블.",fill=teal)
d.text((16,34),f"레일 {i1['letters']}글자 · dim {i2['dim']} · 섹션(이름순) {i3['heads']}개 · 빈 섹션 '아직 없음' {i3['empty']}개",fill=muted)
for k,(im,cap) in enumerate([(imgs[0],"① 기본(최신순) — 우측 레일 노출"),
                             (imgs[1],"② 스크럽 → 'ㅅ' 대형 버블"),
                             (imgs[2],"③ 이름순 — 41섹션·빈초성 '아직 없음'")]):
    x = k*(390+16)
    canvas.paste(im,(x,band)); d.text((x+8,band+2),cap,fill=orange)
os.makedirs("docs/screens/v45",exist_ok=True); canvas.save("docs/screens/v45/naia-rail.png")
print("saved docs/screens/v45/naia-rail.png")
