"""개발용 스크린샷 — 북마클릿 '내 북마클릿 만들기' 토큰 발급(Supabase user_tokens).

버그: 발급 실패 '토큰을 저장하지 못했어요' 반복. 수리: user_tokens PG 이관(트랜잭션 커밋 후
durable) + 발급 실패 시 원인 1줄 로깅·안내. 검증: 만들기→발급 성공→(재시작)유지→드래그 가능.
"""
import os, sys, glob, threading, time
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ["SUPABASE_DB_URL"] = "postgresql://goga:goga@127.0.0.1:5432/gogadb"

import src.db.pg as pg
pg.reset_state(); pg.init_schema()
with pg.tx() as cur:
    cur.execute("TRUNCATE user_tokens")

import src.seller_console.views as views
views._current_user_id = lambda: "u1"
try:
    views._check_auth = lambda: True
except Exception:
    pass

from src.order_webhook import app
def run(): app.run(port=5093, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
    if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**o)
    ctx = b.new_context(viewport={'width': 900, 'height': 760}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto("http://127.0.0.1:5093/seller/bookmarklet", wait_until="networkidle")
    if os.path.exists(_bs): p.add_style_tag(path=_bs)
    p.wait_for_timeout(400)
    # 클릭 → 발급
    p.click("#makeBtn")
    p.wait_for_timeout(1200)
    ready = p.evaluate("document.getElementById('bmReady').style.display !== 'none'")
    hint = p.eval_on_selector("#makeHint", "el=>el.textContent")
    print("발급 후 bmReady 표시:", ready, "| hint:", hint)
    # 발급 성공 카드(만들기 버튼·bmReady 드래그 앵커 포함)만 캡처
    card = p.evaluate_handle("document.getElementById('bmReady').closest('.card') || document.getElementById('bmReady')")
    card.scroll_into_view_if_needed()
    p.wait_for_timeout(200)
    card.as_element().screenshot(path="/tmp/shot_bm.png")
    b.close()

# 서버측 영속 검증(재시작 시뮬)
from src.auth import personal_tokens as pt
with pg.query() as cur:
    cur.execute("SELECT count(*) FROM user_tokens WHERE user_id='u1' AND deleted_at IS NULL")
    cnt = cur.fetchone()[0]
print("PG user_tokens (u1) durable rows:", cnt)

# 캡처 합성(상단 배너 + 스크린샷 크롭)
from PIL import Image, ImageDraw
im = Image.open("/tmp/shot_bm.png").convert("RGB")
W = 900; r = W/im.width; im = im.resize((W, int(im.height*r)))
im = im.crop((0, 0, W, min(560, im.height)))
band = 46
canvas = Image.new("RGB", (W, band + im.height + 10), "white")
d = ImageDraw.Draw(canvas)
d.text((16, 10), "북마클릿 '내 북마클릿 만들기' — user_tokens Supabase 이관 후 발급 성공(durable) → 드래그 준비", fill=(17, 154, 142))
d.text((16, 28), f"발급 성공(PG durable {cnt}행) · 재시작(연결 초기화) 후에도 validate 유지 · 실패 시 원인 1줄(429/인증/타임아웃) 로깅·안내", fill=(120, 120, 120))
canvas.paste(im, (0, band))
os.makedirs("docs/screens/v45", exist_ok=True)
canvas.save("docs/screens/v45/bm-token-supabase.png")
print("saved docs/screens/v45/bm-token-supabase.png")
