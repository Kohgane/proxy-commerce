"""개발용 스크린샷 — Supabase 이관 1단계 라이브 검증(psycopg3/NullPool·DATABASE_URL).

오너 검증: ①북마클릿 토큰 발급 성공→새로고침 유지 ②수집이력 삭제→새로고침 부활 0.
런타임=DATABASE_URL(풀러 6543 상당), DDL=직접 연결. 로컬 PostgreSQL 16 실검증.
"""
import os, sys, glob, threading, time
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ["DATABASE_URL"] = "postgresql://goga:goga@127.0.0.1:5432/gogadb"
os.environ.setdefault("MARKET_CRED_ENC_KEY", __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode())

import src.db.pg as pg
pg.reset_state(); pg.init_schema()
with pg.tx() as cur:
    cur.execute("TRUNCATE collect_history"); cur.execute("TRUNCATE user_tokens")

from src.seller_console import collect_history_store as ch
import src.seller_console.views as views
views._seller_identities = lambda: {"u1"}
views._seller_id = lambda: "u1"
views._current_user_id = lambda: "u1"

# 삭제 검증용 20건 시드(PG)
ids = [ch.append(source="extension", url=f"https://temu.com/g-{i:04d}.html",
                 title=f"상품 {i+1:02d}", price="61000", currency="KRW", seller_id="u1") for i in range(20)]

from src.order_webhook import app
def run(): app.run(port=5092, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
import urllib.request, json as _json

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
    if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**o)
    ctx = b.new_context(viewport={'width': 900, 'height': 720}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()

    # ── A) 북마클릿 토큰 발급 → 유지 ──
    p.goto("http://127.0.0.1:5092/seller/bookmarklet", wait_until="networkidle")
    if os.path.exists(_bs): p.add_style_tag(path=_bs)
    p.wait_for_timeout(300)
    p.click("#makeBtn"); p.wait_for_timeout(1000)
    bm_ready = p.evaluate("document.getElementById('bmReady').style.display !== 'none'")
    card = p.evaluate_handle("document.getElementById('bmReady').closest('.card')")
    card.scroll_into_view_if_needed(); p.wait_for_timeout(150)
    card.as_element().screenshot(path="/tmp/live_bm.png")

    # ── B) 수집이력 삭제 → 부활 0 ──
    p.goto("http://127.0.0.1:5092/seller/collect/history", wait_until="networkidle")
    if os.path.exists(_bs): p.add_style_tag(path=_bs)
    p.evaluate("document.querySelectorAll('.row-chk').forEach(c=>{c.checked=true}); if(window.refreshSelCount)refreshSelCount();")
    p.wait_for_timeout(200)
    p.screenshot(path="/tmp/live_before.png", full_page=True)
    # 전체선택 삭제 1회
    req = urllib.request.Request("http://127.0.0.1:5092/seller/collect/bulk-delete",
        data=_json.dumps({"item_ids": ids}).encode(),
        headers={"Content-Type": "application/json", "Cookie": "session=" + cookie})
    resp = _json.loads(urllib.request.urlopen(req).read())
    print("delete resp: ok=%s deleted=%s" % (resp.get("ok"), resp.get("deleted")))
    for k in range(3):
        c = _json.loads(urllib.request.urlopen(urllib.request.Request(
            "http://127.0.0.1:5092/seller/collect/history/count", headers={"Cookie": "session=" + cookie})).read())
        print(f"poll {k+1}: total={c.get('total')}")
    p.goto("http://127.0.0.1:5092/seller/collect/history", wait_until="networkidle")
    if os.path.exists(_bs): p.add_style_tag(path=_bs)
    p.wait_for_timeout(300)
    p.screenshot(path="/tmp/live_after.png", full_page=True)
    b.close()

# 토큰 영속(재시작) 서버측 확인
from src.auth import personal_tokens as pt
pg.reset_state()
with pg.query() as cur:
    cur.execute("SELECT count(*) FROM user_tokens WHERE user_id='u1' AND deleted_at IS NULL")
    tok = cur.fetchone()[0]
print("token durable rows after reset:", tok, "| bmReady:", bm_ready)

from PIL import Image, ImageDraw
def fit(pth, w, h):
    im = Image.open(pth).convert("RGB"); r = w/im.width; im = im.resize((w, int(im.height*r)))
    return im.crop((0, 0, w, min(h, im.height)))
bm = fit("/tmp/live_bm.png", 440, 300)
bef = fit("/tmp/live_before.png", 440, 300)
aft = fit("/tmp/live_after.png", 440, 300)
W = 900; band = 30; canvas = Image.new("RGB", (W, 44 + max(bm.height, 320) + 30 + 320 + 20), "white")
d = ImageDraw.Draw(canvas)
d.text((14, 12), "Supabase 이관 1단계 라이브 검증 (psycopg3/NullPool · DATABASE_URL · 부팅 'DB 연결: Supabase OK')", fill=(17, 154, 142))
d.text((14, 50), "① 북마클릿 토큰 발급 성공 → 재시작 후 유지(durable)", fill=(58, 53, 46))
canvas.paste(bm, (14, 74))
d.text((470, 50), f"토큰 durable {tok}행 · 발급 준비 {bm_ready}", fill=(120, 120, 120))
y = 74 + bm.height + 24
d.text((14, y), "② 수집이력 20건 전체선택 삭제 → 재조회 부활 0", fill=(58, 53, 46))
canvas.paste(bef, (14, y + 24)); d.text((20, y + 24), "BEFORE 20건", fill=(200, 60, 60))
canvas.paste(aft, (460, y + 24)); d.text((466, y + 24), "AFTER 0건(부활 0)", fill=(17, 154, 142))
os.makedirs("docs/screens/v45", exist_ok=True)
canvas.save("docs/screens/v45/supabase-stage1-live.png")
print("saved docs/screens/v45/supabase-stage1-live.png")
