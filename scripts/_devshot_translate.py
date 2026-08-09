"""개발용 스크린샷 — v39 D: 편집 페이지 번역 전/후(원문→한국어, 가격 확인 필요)."""
import sys, os, glob, threading, time, json
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

mode = sys.argv[1] if len(sys.argv) > 1 else "before"

if mode == "before":
    EX = {"title": "ヨシダ PORTER タンカー ボストンバッグ 2WAY", "title_en": "ヨシダ PORTER タンカー ボストンバッグ 2WAY",
          "description": "ポーター タンカー シリーズ。", "price_status": "needs_check"}
    ITEM = {"title": "ヨシダ PORTER タンカー ボストンバッグ 2WAY", "price": "", "currency": "JPY"}
else:  # after — 번역됨(title_ko 한국어), 원문은 title_en로 보존
    EX = {"title_ko": "요시다 포터 탱커 보스턴백 2WAY 숄더백",
          "title": "ヨシダ PORTER タンカー ボストンバッグ 2WAY", "title_en": "ヨシダ PORTER タンカー ボストンバッグ 2WAY",
          "description_ko": "포터 탱커 시리즈 — 가볍고 튼튼한 2WAY 보스턴백.",
          "description": "ポーター タンカー シリーズ。", "price_status": "needs_check"}
    ITEM = {"title": "ヨシダ PORTER タンカー ボストンバッグ 2WAY", "price": "", "currency": "JPY"}

import src.seller_console.views as views
views._get_owned_item = lambda iid: {"id": iid, "title": ITEM["title"], "url": "https://yoshidakaban.com/p",
    "domain": "yoshidakaban.com", "price": ITEM["price"], "currency": ITEM["currency"], "image_url": "",
    "status": "ok", "source": "extension", "seller_id": "u1", "extra_json": json.dumps(EX)}

from src.order_webhook import app
def run(): app.run(port=5084, use_reloader=False)
threading.Thread(target=run, daemon=True).start(); time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
ck = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "admin"})

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
    if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**o); ctx = b.new_context(viewport={'width': 900, 'height': 720}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': ck, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page(); p.goto('http://127.0.0.1:5084/seller/collect/preview/it9?drawer=1', wait_until='networkidle')
    bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
    if os.path.exists(bs): p.add_style_tag(path=bs)
    p.wait_for_timeout(700)
    # 제목+가격 영역만
    loc = p.locator('.card').first
    (loc if loc.count() else p).screenshot(path=f'/tmp/shot_xlate_{mode}.png')
    b.close()
print("done", mode)
