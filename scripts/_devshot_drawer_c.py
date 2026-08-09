"""개발용 스크린샷 — v39 C 편집 드로어: 목록 클릭 → 우측 드로어(같은 페이지, 새 창 0)."""
import sys, os, glob, threading, time, json
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

_ROWS = [
    {"id": "it0", "title": "요시다 포터 탱커 보스턴백 2WAY 숄더백", "url": "https://www.yoshidakaban.com/p/it0",
     "domain": "yoshidakaban.com", "price": "39,800", "currency": "JPY", "source": "extension",
     "collected_at": "2026-06-29T09:10", "status": "ok", "image_url": "", "extra_json": "{}"},
    {"id": "it1", "title": "프리미엄 가죽 토트백 A4 비즈니스", "url": "https://1688.com/p/it1",
     "domain": "1688.com", "price": "89,000", "currency": "KRW", "source": "manual",
     "collected_at": "2026-06-29T08:40", "status": "ok", "image_url": "", "extra_json": "{}"},
]
import src.seller_console.collect_history_store as ch
ch.list_items = lambda *a, **k: [dict(r) for r in _ROWS]
ch.summary = lambda *a, **k: {"total": 2, "today": 2, "domains": 2, "by_source": {"extension": 1, "manual": 1}}
ch.distinct_domains = lambda *a, **k: ["yoshidakaban.com", "1688.com"]

# 드로어 iframe이 로드할 편집 페이지용 — _get_owned_item 모킹
import src.seller_console.views as views
_ITEM = {"id": "it0", "title": "요시다 포터 탱커 보스턴백 2WAY 숄더백", "url": "https://www.yoshidakaban.com/p/it0",
         "domain": "yoshidakaban.com", "price": "39800", "currency": "JPY", "image_url": "",
         "status": "ok", "source": "extension", "seller_id": "u1",
         "extra_json": json.dumps({"title_ko": "요시다 포터 탱커 보스턴백 2WAY 숄더백",
            "description": "포터 탱커 시리즈 — 가볍고 튼튼한 2WAY 보스턴백.",
            "images": [], "options": [{"name": "색상", "values": ["블랙", "세이지그린"]}],
            "keywords": ["보스턴백", "2way", "숄더백"], "category_code": "BAG"})}
views._get_owned_item = lambda iid: dict(_ITEM) if iid == "it0" else None

from src.order_webhook import app
def run(): app.run(port=5085, use_reloader=False)
threading.Thread(target=run, daemon=True).start(); time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
ck = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "admin"})
mode = sys.argv[1] if len(sys.argv) > 1 else "after"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
    if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**o); ctx = b.new_context(viewport={'width': 1280, 'height': 820}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': ck, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page(); p.goto('http://127.0.0.1:5085/seller/collect/history', wait_until='networkidle')
    bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(bs): p.add_style_tag(path=bs)
    p.wait_for_timeout(500)
    pages_before = len(ctx.pages)
    if mode == "after":
        # 제목 클릭 → 드로어 오픈
        p.locator('.kgp-open-drawer').first.click()
        p.wait_for_timeout(1500)
        # iframe에도 bootstrap 주입(샌드박스 스타일)
        for fr in p.frames:
            if 'preview' in (fr.url or ''):
                try: fr.add_style_tag(path=bs)
                except Exception: pass
        p.wait_for_timeout(800)
        url_now = p.url
        print("URL unchanged:", url_now.endswith('/seller/collect/history'), "| pages(new window?):", len(ctx.pages) == pages_before)
    p.screenshot(path=f'/tmp/shot_drawerC_{mode}.png')
    b.close()
print("done", mode)
