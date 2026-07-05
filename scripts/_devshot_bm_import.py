"""개발용 스크린샷 — 북마클릿 파일 가져오기(크롬 ICON 속성) 방식.

드래그(지구본 경로) 폐기 → '내 북마클릿 파일 받기' → 서버가 토큰 발급(Supabase) 후 NETSCAPE
북마크 HTML(ICON=브릿지 base64 + 수집 코드) 다운로드. 검증: 실제 페이지(3단계 그림) + 실제 파일 파싱.
"""
import os, sys, glob, threading, time, base64, io, re
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ["DATABASE_URL"] = "postgresql://goga:goga@127.0.0.1:5432/gogadb"
os.environ["DATABASE_URL_DIRECT"] = "postgresql://goga:goga@127.0.0.1:5432/gogadb"

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
def run(): app.run(port=5094, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]
saved_file = {}
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
    if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**o)
    ctx = b.new_context(viewport={'width': 1000, 'height': 900}, ignore_https_errors=True, accept_downloads=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    p.goto("http://127.0.0.1:5094/seller/bookmarklet", wait_until="networkidle")
    if os.path.exists(_bs): p.add_style_tag(path=_bs)
    p.wait_for_timeout(400)
    # 파일 받기 클릭 → 다운로드 인터셉트
    with p.expect_download() as dl_info:
        p.click("#fileBtn")
    dl = dl_info.value
    path = dl.path()
    with open(path, "r", encoding="utf-8") as f:
        saved_file["body"] = f.read()
    saved_file["name"] = dl.suggested_filename
    p.wait_for_timeout(500)
    # 파일 받기 카드(파일 받기 버튼 + 3단계 그림)만 캡처
    card = p.evaluate_handle("document.getElementById('fileBtn').closest('.card')")
    card.scroll_into_view_if_needed(); p.wait_for_timeout(200)
    card.as_element().screenshot(path="/tmp/shot_bmimport.png")
    b.close()

body = saved_file["body"]
# 파싱: DOCTYPE / ICON base64 / HREF 수집코드
is_netscape = "NETSCAPE-Bookmark-file-1" in body
m = re.search(r'ICON="data:image/png;base64,([^"]+)"', body)
icon_b64 = m.group(1) if m else ""
has_collect = "/api/v1/collect/extension" in body
translate_true = "translate:true" in body
# 앵커 텍스트(북마크바에 뜨는 글자) — 제로폭만 있어야 '아이콘만'
am = re.search(r'ICON="[^"]+">(.*?)</A>', body)
anchor_text = am.group(1) if am else "?"
visible_chars = anchor_text.replace("​", "").strip()   # 제로폭 제거 후 보이는 글자
icon_only = (visible_chars == "")
# 아이콘 디코드
from PIL import Image, ImageDraw
icon_img = None
if icon_b64:
    icon_img = Image.open(io.BytesIO(base64.b64decode(icon_b64))).convert("RGBA")

# PG durable 토큰 확인
with pg.query() as cur:
    cur.execute("SELECT count(*) FROM user_tokens WHERE user_id='u1' AND deleted_at IS NULL")
    tok = cur.fetchone()[0]

# 합성: 좌 페이지 스크린샷 + 우 증명 패널
page = Image.open("/tmp/shot_bmimport.png").convert("RGB")
PW = 660; r = PW/page.width; page = page.resize((PW, int(page.height*r)))
page = page.crop((0, 0, PW, min(720, page.height)))
RW = 380
H = max(page.height, 720)
canvas = Image.new("RGB", (PW + RW, H + 52), "white")
d = ImageDraw.Draw(canvas)
ink, gold, teal, orange, muted = (26,23,20), (201,162,75), (17,154,142), (245,130,31), (120,120,120)
d.text((16, 12), "북마클릿 파일 가져오기(크롬 ICON 속성) — 드래그(지구본 경로) 폐기", fill=gold)
d.text((16, 30), "‘내 북마클릿 파일 받기’ → 토큰 발급(Supabase) → 고가수집기.html(ICON=브릿지 마크) 다운로드 → 크롬 가져오기", fill=muted)
canvas.paste(page, (0, 52))
x = PW + 16; y = 66
d.text((x, y), "다운로드 파일 검증", fill=teal); y += 22
d.text((x, y), f"파일명: {saved_file['name']}", fill=ink); y += 18
d.text((x, y), f"NETSCAPE-Bookmark-file-1: {is_netscape}", fill=ink); y += 18
d.text((x, y), f"수집 코드 baked: {has_collect}", fill=ink); y += 18
d.text((x, y), f"번역 ON 반영: {translate_true}", fill=ink); y += 18
d.text((x, y), f"앵커 보이는 글자: {'0(아이콘만)' if icon_only else repr(visible_chars)}", fill=ink); y += 26
d.text((x, y), "ICON 속성 = 브릿지 마크(base64)", fill=teal); y += 22
if icon_img:
    big = icon_img.resize((72, 72))
    canvas.paste(big, (x, y), big);
    d.text((x+84, y+8), "북마크에 붙는 아이콘", fill=ink)
    d.text((x+84, y+28), "(지구본 아님 · v8 브릿지)", fill=muted)
    d.text((x+84, y+48), "가져온 뒤 안 보이면", fill=muted)
    d.text((x+84, y+62), "한 번 클릭하면 고정", fill=orange)
    y += 90
y += 8
d.text((x, y), f"토큰 발급 durable(PG): {tok}행", fill=teal); y += 20
d.rectangle([x, y, x+RW-32, y+70], outline=gold, width=1)
d.text((x+10, y+10), "토큰 저장(Supabase 1단계) 선행 —", fill=orange)
d.text((x+10, y+26), "발급 실패면 파일도 안 만듦(정직).", fill=muted)
d.text((x+10, y+44), "확장이 메인 안내 유지 · 새 창 0.", fill=muted)
os.makedirs("docs/screens/v45", exist_ok=True)
canvas.save("docs/screens/v45/bm-import-file.png")
print(f"is_netscape={is_netscape} has_collect={has_collect} translate_true={translate_true} icon_only={icon_only} anchor_text={anchor_text!r} icon_bytes={len(icon_b64)} tok={tok} name={saved_file['name']}")
print("saved docs/screens/v45/bm-import-file.png")
