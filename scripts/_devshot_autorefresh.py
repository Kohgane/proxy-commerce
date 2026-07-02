"""개발용 스크린샷 — v41 STEP 1-0b 수집→목록 자동 반영.

BEFORE: 수집이력 화면 열림(빈 목록). AFTER: 수집 후 '새로고침 없이'(탭 포커스 재조회로 poll 발동)
같은 화면에 새 상품이 자동 등장. 사람이 새로고침 버튼을 누르지 않음을 증명.
"""
import sys, os
sys.path.insert(0, os.getcwd())
import glob, threading, time, json, urllib.request

os.environ["SELLER_CONSOLE_AUTH"] = "0"
import src.api.extension_api as ext
ext._require_token = lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]}
from src.seller_console import collect_history_store as ch
ch._in_memory.clear()

from src.order_webhook import app

def run(): app.run(port=5090, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})

_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

def shoot(page, out):
    if os.path.exists(_bs):
        page.add_style_tag(path=_bs)
    page.wait_for_timeout(400)
    page.screenshot(path=f"/tmp/shot_{out}.png", full_page=True)

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 1024, 'height': 760}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()

    # BEFORE: 빈 수집이력 화면을 열어둔다(사용자가 보고 있는 상태).
    p.goto("http://127.0.0.1:5090/seller/collect/history", wait_until="networkidle")
    shoot(p, "autorefresh_before")

    # 다른 창/확장에서 상품 1건 수집(서버 실제 저장 경로).
    req = urllib.request.Request("http://127.0.0.1:5090/api/v1/collect/extension",
        data=json.dumps({"url": "https://www.temu.com/p/sofa-9",
                         "title": "린넨 3인 소파 · 아이보리",
                         "price": "129.00", "currency": "USD"}).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer x"})
    resp = json.loads(urllib.request.urlopen(req).read())
    print("collect resp:", resp.get("ok"), resp.get("item_id"))

    # 사용자는 새로고침을 누르지 않는다 — 탭 복귀(visibilitychange)로 poll이 발동해 자동 반영.
    p.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    p.wait_for_load_state("networkidle")   # poll → count 증가 감지 → 자동 reload
    p.wait_for_timeout(600)
    # AFTER: 같은 화면(수동 새로고침 없이) 새 상품 자동 등장.
    shoot(p, "autorefresh_after")
    b.close()
print("done")
