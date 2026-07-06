"""개발용 스크린샷 — 한/영 분리 표시(6): 언어 토글 단일언어 + 원문 뱃지."""
import os, sys, glob, threading, time
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

import src.seller_console.collect_history_store as ch
ch._in_memory[:] = []
# 번역된 상품 + 미번역 상품(원문 뱃지 대상)
ch.append(source="extension", url="https://x.com/g-a", title="접이식 차량용 책상", seller_id="u1",
          extra={"title": "Folding Car Desk", "title_en": "Folding Car Desk", "title_ko": "접이식 차량용 책상"})
ch.append(source="extension", url="https://x.com/g-b", title="Yoshida Porter Tote", seller_id="u1",
          extra={"title": "Yoshida Porter Tote", "title_en": "Yoshida Porter Tote", "title_ko": "Yoshida Porter Tote"})

from src.order_webhook import app
threading.Thread(target=lambda: app.run(port=5100, use_reloader=False), daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모", "user_role": "admin"})
_bs = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux/chrome')[0]

def shot(lang, path):
    with sync_playwright() as pw:
        px = os.environ.get('HTTPS_PROXY'); o = {'executable_path': exe}
        if px: o['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
        b = pw.chromium.launch(**o)
        ctx = b.new_context(viewport={'width': 760, 'height': 620}, ignore_https_errors=True)
        ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'},
                         {'name': 'kgp_lang', 'value': lang, 'domain': '127.0.0.1', 'path': '/'}])
        p = ctx.new_page()
        p.goto("http://127.0.0.1:5100/seller/collect/history", wait_until="networkidle")
        if os.path.exists(_bs): p.add_style_tag(path=_bs)
        p.wait_for_timeout(500)
        titles = p.eval_on_selector_all(".cardcell-title a", "els=>els.map(e=>e.textContent.trim())")
        badges = len(p.query_selector_all(".cardcell-title .badge"))
        wonmun = p.evaluate("[...document.querySelectorAll('.cardcell-title .badge')].filter(b=>b.textContent.includes('원문')).length")
        tbl = p.query_selector("table")
        (tbl or p).screenshot(path=path)
        b.close()
        return {"titles": titles, "wonmun_badges": wonmun}

ko = shot("ko", "/tmp/lang_ko.png")
en = shot("en", "/tmp/lang_en.png")
print("ko:", ko); print("en:", en)

from PIL import Image, ImageDraw
im_ko = Image.open("/tmp/lang_ko.png").convert("RGB")
im_en = Image.open("/tmp/lang_en.png").convert("RGB")
W = max(im_ko.width, im_en.width) + 24
band = 78; gap = 30
H = band + im_ko.height + gap + im_en.height + 12
cv = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(cv)
teal, muted, orange = (17,154,142), (120,120,120), (245,130,31)
d.text((16,12), "한/영 분리 표시(6) — UI 언어 토글에 맞는 언어만 표시 + '원문' 뱃지(섞기 금지)", fill=teal)
d.text((16,34), f"KO 토글: {ko['titles']}  ·  원문 뱃지 {ko['wonmun_badges']}개(미번역 'Yoshida…')", fill=muted)
d.text((16,54), f"EN 토글: {en['titles']}  ·  원문 뱃지 {en['wonmun_badges']}개(en=원문 소스)", fill=muted)
d.text((10, band-4), "▼ 한국어(ko) 토글 — 번역본 표시 · 미번역은 원문+뱃지", fill=orange)
cv.paste(im_ko, (0, band))
y2 = band + im_ko.height + gap
d.text((10, y2-22), "▼ EN 토글 — 원문(영문)만 · 한국어 안 섞임", fill=orange)
cv.paste(im_en, (0, y2))
os.makedirs("docs/screens/v45", exist_ok=True); cv.save("docs/screens/v45/lang-split.png")
print("saved docs/screens/v45/lang-split.png")
