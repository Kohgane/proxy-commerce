"""Y15(오너 2026-10-22) — 요금제 화면 캡처(390): 요금표(한도 숫자) + 이번 달 쓴 양.

일반 가입자(공유 사용자 아님) 한 명, 인메모리: 이번 달 수집 7개 · 사전검증 3회 · 무료 번역 4회.
사용: python scripts/_devshot_y15b.py before|after [출력폴더] (before는 머지 전 main 워크트리에서 돌린다)
"""
import glob
import os
import sys
import threading
import time

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ["USAGE_LIMITS"] = "1"
TAG = sys.argv[1] if len(sys.argv) > 1 else "after"
OUT = os.path.join(sys.argv[2] if len(sys.argv) > 2 else "docs/screens/y15b", TAG)
os.makedirs(OUT, exist_ok=True)
SID = "u-new-seller"

from src.db import image_translate_queue_pg as Q
STATE = {}
Q.state_get = lambda k: STATE.get(k) or {}
Q.state_set = lambda k, v: STATE.__setitem__(k, v)
from src.seller_console import collect_history_store as ch
ch._pg_backend = lambda: None
ch._in_memory.clear()
for i in range(7):
    ch.append(source="extension", url=f"https://item.taobao.com/item.htm?id=70000000{i:04d}", seller_id=SID,
              title=f"수집 상품 {i + 1}", price="89", currency="CNY", extra={})
try:
    from src.seller_console import usage_meter as M
    STATE[M._PRECHECK_KEY + f"{SID}:{M.month_key()}"] = {"n": 3}
except ImportError:
    pass
from src.seller_console import translation_usage as TU
TU._in_memory[SID] = 4

from src.order_webhook import app
PORT = 5127
threading.Thread(target=lambda: app.run(port=PORT, use_reloader=False), daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": SID, "user_email": "new-seller@example.com", "user_name": "새 셀러", "user_role": "seller"})
BASE = f"http://127.0.0.1:{PORT}"
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    opts = {'executable_path': exe}
    if px:
        opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**opts)
    c = b.new_context(viewport={'width': 390, 'height': 844}, ignore_https_errors=True, is_mobile=True, bypass_csp=True)
    c.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    pg = c.new_page()
    pg.goto(BASE + "/seller/billing", wait_until="networkidle")
    for bs in ("node_modules/bootstrap/dist/css/bootstrap.min.css", "/home/user/proxy-commerce/node_modules/bootstrap/dist/css/bootstrap.min.css"):
        if os.path.exists(bs):
            pg.add_style_tag(path=bs)
            break
    pg.wait_for_timeout(1000)
    pg.screenshot(path=os.path.join(OUT, f"{TAG}-billing-mobile.png"), full_page=True)
    main = pg.locator("main, .console-main, #main").first
    text = (main if main.count() else pg.locator("body")).inner_text()
    with open(os.path.join(OUT, f"{TAG}-billing-mobile.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(ln.strip() for ln in text.split("\n") if ln.strip()) + "\n")
    sw = pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
    print("가로 스크롤", sw)
    b.close()
os._exit(0)
