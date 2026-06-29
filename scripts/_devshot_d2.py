"""개발용 — v39 D: 제목 플레이스홀더({REGION_NAME...}) before/after (편집 프리필)."""
import sys, os, glob, threading, time, json
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

mode = sys.argv[1] if len(sys.argv) > 1 else "after"
# before=정제 안 한 원본 제목 그대로 / after=strip 적용(실제 코드 경로)
raw = "러기지 캐리어 20인치 {REGION_NAME - Temu Republic of Korea}"
import src.collectors.universal_scraper as us
title = raw if mode == "before" else us.strip_placeholder_tokens(raw)

_ITEM = {"id": "ph1", "title": title, "url": "https://temu.com/p", "domain": "temu.com",
         "price": "", "currency": "USD", "source": "extension",
         "collected_at": "2026-06-29T09:10", "status": "ok", "image_url": "",
         "extra_json": json.dumps({"title_ko": title, "title": title, "description": "", "images": [], "price": "", "currency": "USD", "price_status": "needs_check"})}
import src.seller_console.views as views
views._get_owned_item = lambda iid: dict(_ITEM)
# before 모드: strip 안 타게 패치
if mode == "before":
    us.strip_placeholder_tokens = lambda t: t

from src.order_webhook import app
def run(): app.run(port=5087, use_reloader=False)
threading.Thread(target=run, daemon=True).start(); time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
ck = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "admin"})

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
    if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**o); ctx = b.new_context(viewport={'width': 1000, 'height': 720}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': ck, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page(); p.goto('http://127.0.0.1:5087/seller/collect/preview/ph1', wait_until='networkidle')
    bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(bs): p.add_style_tag(path=bs)
    p.wait_for_timeout(500)
    # 제목 입력란으로 스크롤
    try: p.locator('#title, input[name=title], textarea[name=title]').first.scroll_into_view_if_needed()
    except Exception: pass
    p.wait_for_timeout(300)
    p.screenshot(path=f'/tmp/shot_d2_{mode}.png')
    b.close()
print("done", mode, "title=", title)
