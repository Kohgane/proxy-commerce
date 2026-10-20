"""Y13-D 2 — 캡처: BLACKHOLES 드로어 위쪽(운영 10-19 02:50 UTC 기록 — 사전검증 4마켓 통과 · 대표 3번째 · 갤러리 0번·옵션 사진 0번 사진째 뺌).
운영 주소는 이 환경에서 막혀 있어(프록시 403) 운영 기록 값을 인메모리에 심어 로컬로 그린다. 사용: python scripts/_devshot_y13d2.py [OUT]"""
import glob, json, os, sys, threading, time
sys.path.insert(0, os.getcwd()); sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
os.environ["SELLER_CONSOLE_AUTH"] = "0"
OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/screens/y13d/blackholes"
os.makedirs(OUT, exist_ok=True)
from src.db import image_translate_queue_pg as Q
Q.state_get = lambda k: {}; Q.state_set = lambda k, v: None; Q.counts = lambda item_id="": {"queued": 0, "running": 0}
from src.db import market_registrations_pg as _L
_L.enabled = lambda: False
from src.seller_console import collect_history_store as ch
ch._pg_backend = lambda: None; ch._in_memory.clear()
from test_y13d_owner_decision import _bh, _polished_sku0, IMGS
from src.services import risk_gate as R
ex = _polished_sku0(_bh())
h = next(x for x in R.scan(ex)["hits"] if x["label"] == "인터스텔라")
R.strip_extra(ex, h, pixels="restore")
ex["rep_image"] = IMGS[2]
ex["pv_ready"] = {"at": "2026-10-19T02:50:27.385457+00:00", "ok": True, "job": "e48e7c30b38c46feb7e0c915a89fef8d", "held": [],
                  "markets": ["coupang:gogane", "coupang:woojoo", "smartstore:chezgoga", "smartstore:gocosmos"], "pending": []}
iid = ch.append(source="share", url="https://item.taobao.com/item.htm?id=1", seller_id="u1", title=ex["title_ko"], price="69.90", currency="CNY", extra=ex)
from src.order_webhook import app
PORT = 5137
threading.Thread(target=lambda: app.run(port=PORT, use_reloader=False), daemon=True).start(); time.sleep(2)
cookie = app.session_interface.get_signing_serializer(app).dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_role": "admin"})
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    opts = {'executable_path': exe}
    if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**opts)
    for wname, vw in (("desktop", {'width': 1280, 'height': 1000}), ("mobile", {'width': 390, 'height': 900})):
        c = b.new_context(viewport=vw, is_mobile=(wname == "mobile"))
        c.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        pg = c.new_page()
        pg.goto(f"http://127.0.0.1:{PORT}/seller/collect/preview/{iid}?drawer=1", wait_until="networkidle")
        bs = "/home/user/proxy-commerce/node_modules/bootstrap/dist/css/bootstrap.min.css"
        if os.path.exists(bs): pg.add_style_tag(path=bs)
        pg.wait_for_timeout(700)
        box = pg.locator(".kgp-etabs").first.bounding_box()
        pg.screenshot(path=os.path.join(OUT, f"drawer-top-{wname}.png"), clip={"x": 0, "y": 0, "width": vw["width"], "height": int(box["y"]) + 10 if box else 600})
        loc = pg.locator("[data-role=pv-ready]")
        line = loc.first.inner_text().replace("\n", " / ") if loc.count() else "(없음)"
        open(os.path.join(OUT, f"drawer-top-{wname}.txt"), "w", encoding="utf-8").write(line + "\n"); print(wname, line)
        c.close()
    b.close()
os._exit(0)
