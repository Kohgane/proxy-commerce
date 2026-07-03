"""개발용 스크린샷 — v43-1 삭제 부활 × 자동 새로고침.
5건 수집 → 2건 삭제 → 카운트 폴링 여러 번 → 목록 3건 유지(부활 0).
"""
import sys, os, glob, threading, time, json, urllib.request
sys.path.insert(0, os.getcwd())

os.environ["SELLER_CONSOLE_AUTH"] = "0"
from src.seller_console import collect_history_store as ch
import src.seller_console.views as views
views._seller_identities = lambda: {"u1"}
views._seller_id = lambda: "u1"
ch._in_memory.clear()
ids = [ch.append(source="extension", url=f"https://temu.com/g-{i:015d}.html",
                 title=f"린넨 소파 {i+1}", price=str(120000+i*1000), currency="KRW", seller_id="u1")
       for i in range(5)]

from src.order_webhook import app
def run(): app.run(port=5097, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

def shoot(page, out):
    page.goto("http://127.0.0.1:5097/seller/collect/history", wait_until="networkidle")
    if os.path.exists(_bs):
        page.add_style_tag(path=_bs)
    page.wait_for_timeout(500)
    page.screenshot(path=f"/tmp/shot_del_{out}.png", full_page=True)

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
    shoot(p, "before")   # 5건

    # 2건 삭제(서버 커밋+검증)
    req = urllib.request.Request("http://127.0.0.1:5097/seller/collect/bulk-delete",
        data=json.dumps({"item_ids": ids[:2]}).encode(),
        headers={"Content-Type": "application/json", "Cookie": "session=" + cookie})
    print("delete:", json.loads(urllib.request.urlopen(req).read()))
    # 카운트 폴링 5회 — 부활 0 확인
    for k in range(5):
        c = json.loads(urllib.request.urlopen(
            urllib.request.Request("http://127.0.0.1:5097/seller/collect/history/count",
                                   headers={"Cookie": "session=" + cookie})).read())
        print(f"poll {k+1}: total={c.get('total')}")
    shoot(p, "after")    # 3건(부활 0)
    b.close()
print("done")
