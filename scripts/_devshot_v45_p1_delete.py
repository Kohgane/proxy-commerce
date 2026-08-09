"""개발용 스크린샷 — v45 P1 벌크 삭제 부분 실패 근본 수리(판정 재현).

판정: 20건 전체선택 삭제 → 1회에 전부 소멸 → 새로고침·페이지 왕복 후에도 0건.
 - before: 20건 목록(전체선택 체크)
 - 삭제: /seller/collect/bulk-delete 1회 호출 → 응답 deleted=20, deleted_ids 20개
 - after: 새로고침 → 목록 0건(빈 상태). 페이지 왕복(재조회)해도 0건 유지(부활 0).
"""
import sys, os, glob, threading, time, json, urllib.request
sys.path.insert(0, os.getcwd())

os.environ["SELLER_CONSOLE_AUTH"] = "0"
from src.seller_console import collect_history_store as ch
import src.seller_console.views as views
views._seller_identities = lambda: {"u1"}
views._seller_id = lambda: "u1"
ch._in_memory.clear()
ids = [ch.append(source="extension", url=f"https://temu.com/g-{i:015d}.html",
                 title=f"상품 {i+1:02d} — 린넨 3인 소파", price=str(61000 + i * 300),
                 currency="KRW", seller_id="u1")
       for i in range(20)]

from src.order_webhook import app
def run(): app.run(port=5099, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

def shoot(page, out, check_all=False):
    page.goto("http://127.0.0.1:5099/seller/collect/history", wait_until="networkidle")
    if os.path.exists(_bs):
        page.add_style_tag(path=_bs)
    page.wait_for_timeout(400)
    if check_all:
        page.evaluate("document.querySelectorAll('.row-chk').forEach(c=>{c.checked=true});"
                      "if(window.refreshSelCount)refreshSelCount();")
        page.wait_for_timeout(200)
    page.screenshot(path=f"/tmp/shot_v45p1_{out}.png", full_page=True)

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    _px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    _opts = {'executable_path': exe}
    if _px:
        _opts['proxy'] = {'server': _px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**_opts)
    ctx = b.new_context(viewport={'width': 1040, 'height': 900}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    shoot(p, "before", check_all=True)   # 20건 전체선택

    # 20건 전체선택 삭제 — 1회 호출
    req = urllib.request.Request("http://127.0.0.1:5099/seller/collect/bulk-delete",
        data=json.dumps({"item_ids": ids}).encode(),
        headers={"Content-Type": "application/json", "Cookie": "session=" + cookie})
    resp = json.loads(urllib.request.urlopen(req).read())
    print("delete resp: ok=%s deleted=%s deleted_ids=%d" % (
        resp.get("ok"), resp.get("deleted"), len(resp.get("deleted_ids") or [])))

    # 페이지 왕복(재조회) 여러 번 — 부활 0 확인
    for k in range(3):
        c = json.loads(urllib.request.urlopen(
            urllib.request.Request("http://127.0.0.1:5099/seller/collect/history/count",
                                   headers={"Cookie": "session=" + cookie})).read())
        print(f"poll {k+1}: total={c.get('total')}")
    shoot(p, "after")    # 0건(빈 상태, 부활 0)
    b.close()

# 합성: before(20건 전체선택) | after(0건)
from PIL import Image, ImageDraw
bef = Image.open("/tmp/shot_v45p1_before.png").convert("RGB")
aft = Image.open("/tmp/shot_v45p1_after.png").convert("RGB")
W = 1040
def cap(im, h=720):
    r = W / im.width
    im2 = im.resize((W, int(im.height * r)))
    return im2.crop((0, 0, W, min(h, im2.height)))
bef, aft = cap(bef), cap(aft)
band = 40
canvas = Image.new("RGB", (W, band + bef.height + band + aft.height + 20), "white")
d = ImageDraw.Draw(canvas)
d.text((16, 12), "BEFORE — 20건 전체선택 (삭제 대상)", fill=(26, 23, 20))
canvas.paste(bef, (0, band))
y = band + bef.height + 10
d.text((16, y + 8), "AFTER — 1회 삭제 → 0건 (새로고침·재조회 3회에도 부활 0)", fill=(17, 154, 142))
canvas.paste(aft, (0, y + band))
os.makedirs("docs/screens/v45", exist_ok=True)
canvas.save("docs/screens/v45/p1-bulk-delete.png")
print("saved docs/screens/v45/p1-bulk-delete.png")
