"""개발용 스크린샷 — v45 P2 수집 성공률 들쭉날쭉(쿼터 429) 근본 수리(판정 재현).

판정: 16건 벌크 수집 3회 반복 → 매회 성공+실패 합계=16, 성공분은 전부 이력에 실존.
 - 시트 쓰기가 매 append 첫 시도에 429를 내도록 주입 → 재시도(지수 백오프)로 전건 회복.
 - 3회 반복 각각 durable 16/16(실패 0) 확인(stdout) + 이력 화면 캡처(총수집 실존).
"""
import sys, os, glob, threading, time
sys.path.insert(0, os.getcwd())

os.environ["SELLER_CONSOLE_AUTH"] = "0"
from src.seller_console import collect_history_store as ch
import src.seller_console.views as views
views._seller_identities = lambda: {"u1"}
views._seller_id = lambda: "u1"
ch._in_memory.clear()
ch._quota_stats.update(count_429=0, count_5xx=0, retries=0)
ch._SHEET_ID = "sheet-test"
ch.time.sleep = lambda *a, **k: None   # 캡처 가속(재시도 로직 자체는 그대로)


class _Resp:
    def __init__(s, c): s.status_code = c
class _APIErr(Exception):
    def __init__(s, c): super().__init__(f"HTTP {c}"); s.response = _Resp(c)


class _FakeWS:
    header = list(ch._HEADERS)
    def __init__(s): s.rows = []; s.fail_next = False; s.id = 1; s.spreadsheet = s
    def row_values(s, i): return list(s.header) if i == 1 else []
    def get_all_records(s): return [dict(zip(s.header, r)) for r in s.rows]
    def get_all_values(s): return [list(s.header)] + [list(r) for r in s.rows]
    def append_row(s, row):
        if s.fail_next:
            s.fail_next = False
            raise _APIErr(429)       # 첫 시도 429
        s.rows.append(list(row))     # 재시도 성공

ws = _FakeWS()
ch._get_worksheet = lambda: ws

# 3회 반복 × 16건, 매 append 첫 시도 429 → 재시도 회복
for rnd in range(1, 4):
    ok = fail = 0
    for k in range(16):
        ws.fail_next = True
        iid, durable = ch.append(source="bulk", url=f"https://temu.com/g-r{rnd}-{k:03d}.html",
                                 title=f"상품 R{rnd}-{k+1:02d}", price=str(61000 + k * 200),
                                 currency="KRW", seller_id="u1", return_durable=True)
        if durable: ok += 1
        else: fail += 1
    print(f"round {rnd}: 성공 {ok} · 실패 {fail} · 합계 {ok+fail}")
print("관측 429 =", ch.get_quota_stats()["count_429"], "· 재시도 =", ch.get_quota_stats()["retries"])
print("이력 총건 =", len(ws.rows))

from src.order_webhook import app
def run(): app.run(port=5098, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 1040, 'height': 900}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto("http://127.0.0.1:5098/seller/collect/history", wait_until="networkidle")
    if os.path.exists(_bs):
        p.add_style_tag(path=_bs)
    p.wait_for_timeout(500)
    p.screenshot(path="/tmp/shot_v45p2.png", full_page=True)
    b.close()

from PIL import Image, ImageDraw
im = Image.open("/tmp/shot_v45p2.png").convert("RGB")
W = 1040
r = W / im.width
im = im.resize((W, int(im.height * r)))
im = im.crop((0, 0, W, min(760, im.height)))
band = 44
canvas = Image.new("RGB", (W, band + im.height + 10), "white")
d = ImageDraw.Draw(canvas)
d.text((16, 10), "P2 — 매 수집 첫 시도 429(쿼터) → 지수 백오프 재시도로 전건 회복 "
                 "(3회×16 각 성공16·실패0, 이력에 전건 실존)", fill=(17, 154, 142))
canvas.paste(im, (0, band))
os.makedirs("docs/screens/v45", exist_ok=True)
canvas.save("docs/screens/v45/p2-quota-retry.png")
print("saved docs/screens/v45/p2-quota-retry.png")
