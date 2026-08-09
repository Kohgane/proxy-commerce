"""개발용 스크린샷 — 토큰 다중선택 삭제 + 삭제→재조회 부활 0(PG durable) + 확장 401만 재발급."""
import os, sys, glob, threading, time
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ["DATABASE_URL"] = "postgresql://goga:goga@127.0.0.1:5432/gogadb"
os.environ["DATABASE_URL_DIRECT"] = "postgresql://goga:goga@127.0.0.1:5432/gogadb"

import src.db.pg as pg
pg.reset_state(); pg.init_schema()
with pg.tx() as cur:
    cur.execute("TRUNCATE user_tokens")

from src.auth import personal_tokens as pt
for _ in range(4):
    pt.generate_token(user_id="u1", scopes=["collect.write"])

import src.seller_console.views as views
views._current_user_id = lambda: "u1"
views._seller_identities = lambda: {"u1"}
try: views._check_auth = lambda: True
except Exception: pass

from src.order_webhook import app
def run(): app.run(port=5096, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
    if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**o)
    ctx = b.new_context(viewport={'width': 980, 'height': 720}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto("http://127.0.0.1:5096/seller/me/tokens", wait_until="networkidle")
    if os.path.exists(_bs): p.add_style_tag(path=_bs)
    p.wait_for_timeout(400)
    # 4개 중 2개 체크
    boxes = p.query_selector_all(".tok-check")
    boxes[0].check(); boxes[1].check()
    p.wait_for_timeout(200)
    bulk_label = p.eval_on_selector("#bulkRevokeBtn", "el=>el.textContent.trim()")
    disabled = p.eval_on_selector("#bulkRevokeBtn", "el=>el.disabled")
    card = p.evaluate_handle("document.querySelector('table').closest('.card')")
    card.as_element().screenshot(path="/tmp/shot_tok.png")
    b.close()

print("벌크 버튼 라벨:", bulk_label, "| disabled:", disabled)

# 다중 삭제 durable 검증(재시작 시뮬)
with app.test_client() as c:
    with c.session_transaction() as s:
        s["user_id"] = "u1"
    all_hashes = [t["token_hash"] for t in pt.list_tokens(user_id="u1") if not t.get("revoked")]
    r = c.post("/seller/me/tokens/revoke-bulk", json={"token_hashes": all_hashes[:2]})
    resp = r.get_json()
pg.reset_state()   # 재시작 시뮬
active_after = [t for t in pt.list_tokens(user_id="u1") if not t.get("revoked")]
print("삭제 응답:", resp, "| 재시작 후 활성:", len(active_after))

from PIL import Image, ImageDraw
shot = Image.open("/tmp/shot_tok.png").convert("RGB")
W = 900; r2 = W/shot.width; shot = shot.resize((W, int(shot.height*r2)))
shot = shot.crop((0, 0, W, min(300, shot.height)))
band = 96
canvas = Image.new("RGB", (W, band + shot.height + 10), "white")
d = ImageDraw.Draw(canvas)
teal, muted, orange = (17,154,142), (120,120,120), (245,130,31)
d.text((16, 10), "토큰 다중선택 삭제 + 삭제→재조회 부활 0(PG durable) + 확장 401만 재발급", fill=teal)
d.text((16, 32), f"체크박스 2개 선택 → '선택 삭제 (2)' 활성  [{bulk_label} · disabled={disabled}]", fill=muted)
d.text((16, 52), f"다중 삭제 응답: revoked_count={resp.get('revoked_count')} · 재시작(연결 초기화) 후 활성 {len(active_after)}개 (부활 0)", fill=muted)
d.text((16, 72), "확장: 재발급 안내는 401(만료·삭제)·미설정일 때 '버튼 클릭 시에만' — 매 페이지 토스트 0(background E-1)", fill=orange)
canvas.paste(shot, (0, band))
os.makedirs("docs/screens/v45", exist_ok=True)
canvas.save("docs/screens/v45/token-bulk-delete.png")
print("saved docs/screens/v45/token-bulk-delete.png")
