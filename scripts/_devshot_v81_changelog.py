"""개발용 스크린샷 — v81 STEP7 변경 가시성(체인지로그 페이지 + 콘솔 '이번 업데이트' 배너)."""
import os, sys, glob, threading, time
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

from src.order_webhook import app
app.config["SECRET_KEY"] = "devshot-v81-cl"

def run(): app.run(port=5096, use_reloader=False)
threading.Thread(target=run, daemon=True).start()
time.sleep(2)

ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})

from playwright.sync_api import sync_playwright
exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
with sync_playwright() as pw:
    px = os.environ.get("HTTPS_PROXY"); o = {"executable_path": exe}
    if px: o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
    b = pw.chromium.launch(**o)
    ctx = b.new_context(viewport={"width": 1040, "height": 900}, ignore_https_errors=True)
    ctx.add_cookies([{"name": "session", "value": cookie, "domain": "127.0.0.1", "path": "/"}])
    p = ctx.new_page()
    # 체인지로그 페이지
    p.goto("http://127.0.0.1:5096/seller/changelog", wait_until="networkidle")
    p.wait_for_timeout(500)
    p.screenshot(path="/tmp/shot_v81_changelog.png", full_page=True)
    # 대시보드 상단 배너(강제 노출: seen 초기화)
    p.goto("http://127.0.0.1:5096/seller/dashboard", wait_until="networkidle")
    p.evaluate("try{localStorage.removeItem('kgp_cl_seen');var el=document.getElementById('kgpUpdateBanner');if(el)el.hidden=false;}catch(e){}")
    p.wait_for_timeout(300)
    banner = p.query_selector("#kgpUpdateBanner")
    if banner:
        banner.screenshot(path="/tmp/shot_v81_banner.png")
        print("배너 텍스트:", (banner.inner_text() or "").replace("\n", " ")[:120])
    b.close()
print("캡처: /tmp/shot_v81_changelog.png · /tmp/shot_v81_banner.png")
