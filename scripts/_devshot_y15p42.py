"""Y15 순찰 42(오너 2026-10-23) — 반려 감시 화면 캡처(390): 일반 셀러가 오너 등록 줄을 보느냐.

인메모리 등록 대장: 오너(칸 생기기 전 = 주인 빈 값) 반려 줄 1 + 일반 셀러 반려 줄 1. 일반 셀러로 로그인해 연다.
사용: python scripts/_devshot_y15p42.py before|after [출력폴더] (before는 머지 전 main 워크트리에서 돌린다)
"""
import glob
import os
import sys
import threading
import time

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "1"
TAG = sys.argv[1] if len(sys.argv) > 1 else "after"
OUT = os.path.join(sys.argv[2] if len(sys.argv) > 2 else "docs/screens/y15p42", TAG)
os.makedirs(OUT, exist_ok=True)
SID = "u-plain-seller"

from src.db import market_registrations_pg as REG
REG.enabled = lambda: False
REG.reset_memory()
REG.record("16350000001", account="gogane", title="오너 등록 상품 — 서버 줄")
try:
    REG.record("16350000002", account="gogane", title="내가 등록한 상품", owner_seller_id=SID)
except TypeError:                                                 # before: 주인 칸이 없다
    REG.record("16350000002", account="gogane", title="내가 등록한 상품")
for pid in ("16350000001", "16350000002"):
    REG.mark_checked(pid, status="rejected", reject_kind="image_spec", reject_comment="대표 이미지 규격 미달")

from src.order_webhook import app
PORT = 5129
threading.Thread(target=lambda: app.run(port=PORT, use_reloader=False), daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": SID, "user_email": "plain-seller@example.com", "user_name": "일반 셀러", "user_role": "seller"})
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
    pg.goto(BASE + "/seller/sourcing/reject-watch", wait_until="networkidle")
    for bs in ("node_modules/bootstrap/dist/css/bootstrap.min.css", "/home/user/proxy-commerce/node_modules/bootstrap/dist/css/bootstrap.min.css"):
        if os.path.exists(bs):
            pg.add_style_tag(path=bs)
            break
    pg.wait_for_timeout(1000)
    pg.screenshot(path=os.path.join(OUT, f"{TAG}-reject-watch-mobile.png"), full_page=True)
    text = pg.locator("body").inner_text()
    with open(os.path.join(OUT, f"{TAG}-reject-watch-mobile.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(ln.strip() for ln in text.split("\n") if ln.strip()) + "\n")
    print("오너 줄 보임:", "오너 등록 상품" in text, "· 내 줄 보임:", "내가 등록한 상품" in text)
    b.close()
os._exit(0)
