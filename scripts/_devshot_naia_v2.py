"""개발용 스크린샷 — 나이아 레일 v2: 스크럽 오버레이(빈 화면+초성+실데이터)·벤딩·토스트0·필터 접힘."""
import os, sys, glob, threading, time
from types import SimpleNamespace
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

NAMES = ["가방","가위","고무장갑","나무도마","냄비","다리미","마우스패드","바구니","사다리","수건",
         "소파쿠션","숄더백","아령","우산","자석","전구","책상","하모니카","화분",
         "Apple case","Blender","Camera","MOFT Stand","OHSNAP","Tumbler","3단 선반"]
items = []
for i in range(160):
    base = NAMES[i % len(NAMES)]
    items.append(SimpleNamespace(marketplace="coupang", product_id=f"P{i:04d}", sku=f"S{i:04d}",
        state="active", last_synced_at=None, title=f"{base} {i//len(NAMES)+1}",
        title_ko=f"{base} {i//len(NAMES)+1}", title_en="", price=None, price_krw=1000+i, currency="KRW"))
from src.seller_console.market_status_sheets import MarketStatusSheetsAdapter
MarketStatusSheetsAdapter.fetch_all = lambda self: SimpleNamespace(items=list(items), source="mock")

from src.order_webhook import app
threading.Thread(target=lambda: app.run(port=5099, use_reloader=False), daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def shot(act, path, sort="title_asc"):
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
        if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**o)
        ctx = b.new_context(viewport={'width': 390, 'height': 780}, ignore_https_errors=True, is_mobile=True, has_touch=True)
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto(f"http://127.0.0.1:5099/seller/catalog?sort={sort}", wait_until="networkidle")
        if os.path.exists(_bs): p.add_style_tag(path=_bs)
        p.wait_for_timeout(600)
        info = {
          "rail": p.query_selector(".kgp-fs-rail") is not None,
          "filter_visible": p.eval_on_selector("#catalogFilters", "el=>el.classList.contains('show')") if p.query_selector("#catalogFilters") else None,
          "toast_transition": p.evaluate("document.body.innerText.includes('이름순으로 전환됨')"),
        }
        if act: info.update(act(p) or {})
        p.wait_for_timeout(250)
        p.screenshot(path=path)
        b.close()
        return info

# 1) 기본 — 필터 접힘(목록이 첫 화면), 우측 레일
i1 = shot(None, "/tmp/nv1.png")

# 2) 스크럽 — 'ㅅ' 위치 터치 → 오버레이(빈 화면+큰 초성+실데이터) + 벤딩
def scrub(p):
    return p.eval_on_selector(".kgp-fs-rail", """rail=>{
      const el=[...rail.children].find(e=>e.textContent==='ㅅ'); const r=el.getBoundingClientRect();
      const y=r.top+4, x=r.left+8;
      const t=(id)=>new Touch({identifier:id,target:rail,clientX:x,clientY:y});
      rail.dispatchEvent(new TouchEvent('touchstart',{bubbles:true,cancelable:true,touches:[t(1)]}));
      rail.dispatchEvent(new TouchEvent('touchmove',{bubbles:true,cancelable:true,touches:[t(1)]}));
      const sc=document.querySelector('.kgp-fs-scrub');
      const big=document.querySelector('.kgp-fs-scrub-big');
      const rows=document.querySelectorAll('.kgp-fs-scrub-row').length;
      // 벤딩: 근접 글자 transform 적용됐는지
      const bent=[...rail.children].some(s=>s.style.transform && s.style.transform.includes('translateX'));
      return {scrub_on: sc && sc.classList.contains('kgp-fs-scrub-on'), scrub_big: big && big.textContent, scrub_rows: rows, bent};
    }""")
i2 = shot(scrub, "/tmp/nv2.png")

print("default:", i1); print("scrub:", i2)

from PIL import Image, ImageDraw
im1 = Image.open("/tmp/nv1.png").convert("RGB").crop((0,0,390,720))
im2 = Image.open("/tmp/nv2.png").convert("RGB").crop((0,0,390,720))
band=80; W=390*2+24; H=band+720+10
cv=Image.new("RGB",(W,H),"white"); d=ImageDraw.Draw(cv)
teal,muted,orange,red=(17,154,142),(120,120,120),(245,130,31),(200,70,60)
d.text((16,12),"나이아 레일 v2 — 실제 모바일 390px. 스크럽 오버레이·벤딩·토스트0·필터 접힘.",fill=teal)
d.text((16,34),f"필터 접힘(show={i1['filter_visible']}) · 스크럽 오버레이={i2.get('scrub_on')} 초성='{i2.get('scrub_big')}' 항목 {i2.get('scrub_rows')}행 · 벤딩={i2.get('bent')}",fill=muted)
d.text((16,56),f"토스트 '이름순으로 전환됨' 노출: 기본={i1['toast_transition']} 스크럽={i2['toast_transition']}  (둘 다 False=토스트0)",fill=(red if (i1['toast_transition'] or i2['toast_transition']) else teal))
cv.paste(im1,(0,band)); cv.paste(im2,(390+24,band))
d.text((8,band+2),"① 기본 — 필터 접힘·목록 첫 화면·우측 레일",fill=orange)
d.text((390+30,band+2),"② 스크럽 — 빈 화면+'ㅅ'+실데이터·레일 벤딩",fill=orange)
os.makedirs("docs/screens/v45",exist_ok=True); cv.save("docs/screens/v45/naia-v2.png")
print("saved docs/screens/v45/naia-v2.png")
