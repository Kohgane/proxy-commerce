"""개발용 스크린샷 — v87-X2 업로드 화면(마켓 등록 모달) 에디토리얼 격상.

BEFORE(부트스트랩 badge bg-success/danger·alert-info/warning·text-primary 파랑) vs
AFTER(pc-badge 청록/적·pc-status·text-teal). collect_preview.html을 HEAD↔작업본 스왑,
같은 아이템으로 업로드 모달 Step1(마켓 선택)+사전검증 결과(renderPrevalidateResults 실호출) 렌더.
"""
import os, sys, glob, threading, time, subprocess, json
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

import src.seller_console.views as views
views._seller_identities = lambda: {"u1"}
views._seller_id = lambda: "u1"
from src.seller_console import collect_history_store as ch
from src.seller_console import market_credentials as mc
ch._in_memory.clear()
mc.is_connected = lambda *a, **k: True
iid = ch.append(source="extension", url="https://item.rakuten.co.jp/x/9/",
                title="TSUMUGI 천연목 레코드 보관함", price="61144", currency="KRW", seller_id="u1", extra={})

CP = "src/seller_console/templates/collect_preview.html"
NEW = open(CP, encoding="utf-8").read()
OLD = subprocess.check_output(["git", "show", "HEAD:" + CP]).decode("utf-8")

from src.order_webhook import app
app.jinja_env.auto_reload = True
app.jinja_env.cache = {}
def run(): app.run(port=5096, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "seller"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

PREVAL = [
  {"market": "coupang", "market_label": "쿠팡", "ok": True, "message": "필수 항목 충족 — 등록 가능"},
  {"market": "smartstore", "market_label": "스마트스토어", "ok": True, "message": "필수 항목 충족 — 등록 가능"},
  {"market": "elevenst", "market_label": "11번가", "ok": False, "message": "API 키 미설정",
   "hint": "마켓 연동에서 11번가 키를 입력하세요"},
]

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def shot(body, path):
    open(CP, "w", encoding="utf-8").write(body)
    app.jinja_env.cache = {}
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY')
        o = {'executable_path': exe}
        if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**o)
        ctx = b.new_context(viewport={'width': 720, 'height': 900}, ignore_https_errors=True)
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto(f"http://127.0.0.1:5096/seller/collect/preview/{iid}", wait_until="networkidle")
        if os.path.exists(_bs): p.add_style_tag(path=_bs)
        p.wait_for_timeout(400)
        p.evaluate("""(pv) => {
          // 부트스트랩 JS 번들 없이 모달 DOM만 노출(캡처용) — bootstrap.Modal 우회.
          const m = document.getElementById('uploadModal');
          m.classList.add('show'); m.style.cssText = 'display:block;position:static';
          m.querySelector('.modal-dialog').style.margin = '0';
          renderPrevalidateResults(pv);       // 사전검증 결과(통과/실패 뱃지 + pc-status) 실호출
          document.getElementById('stepPrevalidate').classList.remove('d-none');
          document.querySelector('.modal-body').style.background = '#fff';
          document.body.style.background = '#f5efe3';
        }""", PREVAL)
        p.wait_for_timeout(400)
        (p.locator(".modal-content").first).screenshot(path=path)
        b.close()

try:
    shot(OLD, "/tmp/up_before.png")
    shot(NEW, "/tmp/up_after.png")
finally:
    open(CP, "w", encoding="utf-8").write(NEW)

from PIL import Image, ImageDraw
def fit(p, w=440):
    im = Image.open(p).convert("RGB"); r = w / im.width
    return im.resize((w, int(im.height * r)))
a, bmg = fit("/tmp/up_before.png"), fit("/tmp/up_after.png")
band = 30
H = max(a.height, bmg.height) + band + 8
canvas = Image.new("RGB", (a.width + bmg.width + 24, H), "white")
d = ImageDraw.Draw(canvas)
d.text((8, 8), "BEFORE — badge bg-success/danger · alert-info/warning · text-primary", fill=(150, 60, 60))
d.text((a.width + 24, 8), "AFTER — pc-badge 청록/적 · pc-status · text-teal", fill=(40, 110, 100))
canvas.paste(a, (0, band + 8)); canvas.paste(bmg, (a.width + 24, band + 8))
out = sys.argv[1] if len(sys.argv) > 1 else "docs/screens/v87x2/x2-upload.png"
os.makedirs(os.path.dirname(out), exist_ok=True)
canvas.save(out)
print("saved", out)
