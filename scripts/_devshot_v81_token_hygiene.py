"""개발용 스크린샷 — v81 STEP2 토큰 위생(안정 재사용 + 90일 유휴 만료).

판정: 파일 3회 연속 발급 → 활성 토큰 1개(신규 남발 0) + 토큰 페이지 '유휴 만료' 배지.
인메모리 경로(PG 불필요).
"""
import os, sys, glob, threading, time
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

from src.auth import personal_tokens as pt
pt._in_memory.clear(); pt._token_cache.clear()

from src.order_webhook import app
app.config["SECRET_KEY"] = "devshot-v81"

# ── 판정 1: 파일 3회 연속 발급 → 활성 토큰 1개 ──
c = app.test_client()
with c.session_transaction() as s:
    s["user_id"] = "u1"; s["user_email"] = "demo@goga.kr"
for _ in range(3):
    r = c.post("/seller/bookmarklet/file", data={"translate": "1"})
    assert r.status_code == 200, r.status_code
active = [t for t in pt.list_tokens("u1") if not t.get("revoked")]
print("판정1 — 파일 3회 발급 후 활성 토큰:", len(active), "(기대 1)")

# ── 판정 2: 유휴 만료 배지 — 하나는 활성, 하나는 120일 미사용 ──
now = datetime.now(timezone.utc)
# 활성 토큰(방금 발급된 것) 그대로 두고, 유휴 토큰 하나 추가
pt.generate_token(user_id="u1", scopes=["collect.write"])
idle = pt.generate_token(user_id="u1", scopes=["catalog.read"])
row = next(x for x in pt._in_memory if x["token_hash"] == idle["token_hash"])
row["created_at"] = (now - timedelta(days=120)).isoformat()
row["last_used_at"] = ""
marks = [(t["token_hash_prefix"], t["idle_expired"]) for t in pt.list_tokens("u1")]
print("판정2 — list_tokens idle 표기:", marks)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

def run(): app.run(port=5094, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
    if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**o)
    ctx = b.new_context(viewport={'width': 980, 'height': 900}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto("http://127.0.0.1:5094/seller/me/tokens", wait_until="networkidle")
    if os.path.exists(_bs): p.add_style_tag(path=_bs)
    p.wait_for_timeout(500)
    p.screenshot(path="/tmp/shot_v81_token.png", full_page=True)
    b.close()

print("캡처: /tmp/shot_v81_token.png")
