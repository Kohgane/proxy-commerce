"""개발용 스크린샷 — v42 1-3 중복 수집 방지.
같은 Temu 상품을 두 번 수집. BEFORE(중복방지 없음)=목록 2건 / AFTER(중복방지)=목록 1건 + 안내.
"""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time, json, urllib.request

os.environ["SELLER_CONSOLE_AUTH"] = "0"
import src.api.extension_api as ext
ext._require_token = lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]}
from src.seller_console import collect_history_store as ch

from src.order_webhook import app
def run(): app.run(port=5094, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

URL1 = "https://www.temu.com/kr/g-601150655669129.html"
URL2 = "https://www.temu.com/kr/g-601150655669129.html?_oak_mp_inf=track999"

def collect(url):
    req = urllib.request.Request("http://127.0.0.1:5094/api/v1/collect/extension",
        data=json.dumps({"url": url, "title": "접이식 차량용 책상 · 폴딩 테이블",
                         "price": "61144", "currency": "KRW"}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer x"})
    return json.loads(urllib.request.urlopen(req).read())

def shoot(page, out):
    page.goto("http://127.0.0.1:5094/seller/collect/history", wait_until="networkidle")
    if os.path.exists(_bs):
        page.add_style_tag(path=_bs)
    page.wait_for_timeout(500)
    page.screenshot(path=f"/tmp/shot_dedup_{out}.png", full_page=True)

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 1024, 'height': 720}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()

    # BEFORE: 중복방지 비활성(옛 동작) → 같은 상품 2회 = 2건.
    _real = ch.find_by_product_key
    ch.find_by_product_key = lambda *a, **k: None
    ch._in_memory.clear()
    collect(URL1); collect(URL2)
    shoot(p, "before")
    print("BEFORE rows:", len(ch.list_items(seller_ids={"u1"})))

    # AFTER: 중복방지 활성 → 2회째는 duplicate, 1건 유지.
    ch.find_by_product_key = _real
    ch._in_memory.clear()
    r1 = collect(URL1); r2 = collect(URL2)
    print("AFTER rows:", len(ch.list_items(seller_ids={"u1"})), "2nd duplicate:", r2.get("duplicate"), "msg:", r2.get("message"))
    shoot(p, "after")
    b.close()
print("done")
