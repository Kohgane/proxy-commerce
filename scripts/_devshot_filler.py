"""개발용 스크린샷 — v42 1-6 상세 필러 박멸.
Temu 필러 설명으로 수집 → 편집 페이지 상세 영역 촬영. out=before/after.
BEFORE(필러 미차단): 상세에 'Temu에서 이 …을 확인하세요…' 노출.
AFTER(필러 차단): 상세 비움 + 'AI 상세 초안 생성' 버튼(자동 확정 금지).
"""
import sys, os, glob, threading, time, json, urllib.request
sys.path.insert(0, os.getcwd())

OUT = sys.argv[1] if len(sys.argv) > 1 else "after"
os.environ["SELLER_CONSOLE_AUTH"] = "0"
import src.api.extension_api as ext
ext._require_token = lambda scopes=None: {"user_id": "u1", "scopes": ["collect.write"]}
from src.seller_console import collect_history_store as ch
from src.seller_console import market_credentials as mc
ch._in_memory.clear()
mc.is_connected = lambda *a, **k: True

from src.order_webhook import app
def run(): app.run(port=5096, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

req = urllib.request.Request("http://127.0.0.1:5096/api/v1/collect/extension",
    data=json.dumps({"url": "https://www.temu.com/kr/g-777000111222333.html",
                     "title": "접이식 차량용 책상 · 폴딩 테이블",
                     "description": "Temu에서 이 올인홈 접이식 책상을 확인하세요. 가구 제품도 좋아할 수 있습니다.",
                     "price": "61144", "currency": "KRW"}).encode(),
    headers={"Content-Type": "application/json", "Authorization": "Bearer x"})
resp = json.loads(urllib.request.urlopen(req).read())
item_id = resp.get("item_id")
row = ch.list_items(seller_ids={"u1"})[0]
print("stored desc:", repr(json.loads(row.get("extra_json") or "{}").get("description")))

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 820, 'height': 900}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto(f"http://127.0.0.1:5096/seller/collect/preview/{item_id}", wait_until="networkidle")
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.wait_for_timeout(500)
    # 상세 설명 영역(라벨~textarea) 캡처
    loc = p.locator("#editDescription")
    if loc.count():
        box = loc.locator("xpath=ancestor::div[contains(@class,'mb-3')][1]")
        (box.first if box.count() else loc).screenshot(path=f"/tmp/shot_filler_{OUT}.png")
    b.close()
print("done", OUT)
