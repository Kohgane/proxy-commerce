"""개발용 스크린샷 — v39 F: 없는 수집 항목 클릭 시 드로어가 404가 아닌 '수집 실패' 빈 상태."""
import sys, os, glob, threading, time, json
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

_ROWS = [{"id": "missing0", "title": "요시다 포터 탱커 보스턴백(끊긴 수집)", "url": "https://yoshidakaban.com/p",
          "domain": "yoshidakaban.com", "price": "", "currency": "JPY", "source": "extension",
          "collected_at": "2026-06-29T09:10", "status": "ok", "image_url": "", "extra_json": "{}"}]
import src.seller_console.collect_history_store as ch
ch.list_items = lambda *a, **k: [dict(r) for r in _ROWS]
ch.summary = lambda *a, **k: {"total": 1, "today": 1, "domains": 1, "by_source": {"extension": 1}}
ch.distinct_domains = lambda *a, **k: ["yoshidakaban.com"]
import src.seller_console.views as views
views._get_owned_item = lambda iid: None   # 상세 조회 실패(끊긴 수집/별칭 등) 모사

from src.order_webhook import app
def run(): app.run(port=5083, use_reloader=False)
threading.Thread(target=run, daemon=True).start(); time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
ck = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "admin"})

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
    if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**o); ctx = b.new_context(viewport={'width': 1280, 'height': 760}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': ck, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page(); p.goto('http://127.0.0.1:5083/seller/collect/history', wait_until='networkidle')
    bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(bs): p.add_style_tag(path=bs)
    p.wait_for_timeout(400)
    p.locator('.kgp-open-drawer').first.click()
    p.wait_for_timeout(1500)
    for fr in p.frames:
        if 'preview' in (fr.url or ''):
            try: fr.add_style_tag(path=bs)
            except Exception: pass
    p.wait_for_timeout(700)
    mode = sys.argv[1] if len(sys.argv) > 1 else "after"
    p.screenshot(path=f'/tmp/shot_f_{mode}.png')
    b.close()
print("done")
