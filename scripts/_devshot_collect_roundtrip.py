"""개발용 스크린샷 — 수집 라운드트립: 수집 전(빈 목록) vs 확장 수집 후(즉시 반영)."""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time, json, urllib.request

os.environ["SELLER_CONSOLE_AUTH"] = "0"
import src.api.extension_api as ext
ext._require_token = lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]}
from src.seller_console import collect_history_store as ch
ch._in_memory.clear()

from src.order_webhook import app

def run(): app.run(port=5088, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})

def shoot(page, out):
    _bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    page.goto("http://127.0.0.1:5088/seller/collect/history", wait_until="networkidle")
    if os.path.exists(_bs):
        page.add_style_tag(path=_bs)
    page.wait_for_timeout(500)
    loc = page.locator(".card").filter(has=page.locator("table, .console-empty-state")).first
    (loc if loc.count() else page).screenshot(path=f"/tmp/shot_{out}.png")

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 1024, 'height': 700}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    # BEFORE: 수집 전 빈 목록
    shoot(p, "collect_before")
    # 확장 수집 1건(서버 엔드포인트 — 실제 저장 경로)
    req = urllib.request.Request("http://127.0.0.1:5088/api/v1/collect/extension",
        data=json.dumps({"url": "https://www.temu.com/p/abc-123",
                         "title": "Temu 베이직 에코백 캔버스 숄더백",
                         "price": "9.99", "currency": "USD"}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer x"})
    resp = json.loads(urllib.request.urlopen(req).read())
    print("collect resp:", resp.get("ok"), resp.get("item_id"))
    # AFTER: 수집 후 즉시 반영
    shoot(p, "collect_after")
    b.close()
print("done")
