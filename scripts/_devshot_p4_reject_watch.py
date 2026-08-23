"""개발용 스크린샷 — 등록 파이프 P4: 반려 감시(조회·분류·알림).

BEFORE(sid 입력) vs AFTER(분류표: 이미지규격→재등록·상표권→삭제·옵션값→값대체·애플 iPhone보류/삼성유효·미분류).
_account_creds + get_status_histories 몽키패치로 쿠팡 자격·네트워크 없이 렌더.
"""
import os, sys, glob, threading, time
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

import src.pipeline.coupang_replicate as CR
CR._account_creds = lambda account: ("demo-ak", "demo-sk", "A01381223")

import src.uploaders.coupang_uploader as CU
_HIST = {
    "111": {"data": [{"statusName": "승인반려", "comment": "대표 이미지 규격 부적합(해상도 부족)"}]},
    "222": {"data": [{"statusName": "승인반려", "comment": "상표권 침해 소지 — 브랜드 권리 확인 필요"}]},
    "333": {"data": [{"statusName": "승인반려", "comment": "옵션값 정보가 누락되었습니다"}]},
    "444": {"data": [{"statusName": "승인반려", "comment": "애플 카테고리 사전승인 대상 — 아이폰15 케이스"}]},
    "555": {"data": [{"statusName": "승인반려", "comment": "애플 카테고리 사전승인 대상 — 갤럭시 S24용"}]},
    "666": {"data": [{"statusName": "승인반려", "comment": "담당자 검토 결과 반려되었습니다"}]},
}
CU.CoupangUploader.get_status_histories = lambda self, sid: _HIST.get(str(sid), {"data": []})

from src.order_webhook import app
app.jinja_env.auto_reload = True
app.jinja_env.cache = {}

def run(): app.run(port=5098, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]

def shot(path, post=False):
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY')
        opts = {'executable_path': exe}
        if px: opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**opts)
        ctx = b.new_context(viewport={'width': 1000, 'height': 950}, ignore_https_errors=True,
                            service_workers='block')
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5098/seller/sourcing/reject-watch", wait_until="networkidle")
        if post:
            p.fill("#sids", "111\n222\n333\n444\n555\n666")
            p.click("form[action='/seller/sourcing/reject-watch'] button[type=submit]")
            p.wait_for_load_state("networkidle")
            p.wait_for_timeout(700)
        if os.path.exists(_bs):
            p.add_style_tag(path=_bs)
        p.wait_for_timeout(400)
        (p.query_selector("main") or p).screenshot(path=path)
        b.close()

shot("/tmp/p4_before.png", post=False)
shot("/tmp/p4_after.png", post=True)

from PIL import Image, ImageDraw
def fit(p, w=540):
    im = Image.open(p).convert("RGB"); r = w/im.width
    return im.resize((w, int(im.height*r)))
a, bmg = fit("/tmp/p4_before.png"), fit("/tmp/p4_after.png")
band = 30
H = max(a.height, bmg.height) + band + 8
canvas = Image.new("RGB", (a.width + bmg.width + 24, H), "white")
d = ImageDraw.Draw(canvas)
d.text((8, 8), "BEFORE — 반려 sid 입력", fill=(150, 60, 60))
d.text((a.width + 20, 8), "AFTER — 분류표(3유형 처방·애플 iPhone보류/삼성유효·상태문구=미분류)", fill=(17, 154, 142))
canvas.paste(a, (8, band)); canvas.paste(bmg, (a.width + 20, band))
os.makedirs("docs/screens/regpipe", exist_ok=True)
canvas.save("docs/screens/regpipe/p4-reject-watch.png")
print("saved docs/screens/regpipe/p4-reject-watch.png")
