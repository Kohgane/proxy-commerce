"""V41-2 캡처 — 대시보드 1480·390(시드 상품 6건 · 손댈 것 포함). 인자: 출력 폴더, 접두, 포트."""
import sys, os, threading, time, glob, json
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"; os.environ["SECRET_KEY"] = "devshot"
out, pre, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
from src.order_webhook import app
from src.seller_console import collect_history_store as CH
try: CH._in_memory.clear()
except Exception: pass
seed = [("실크 원피스 흐르는 듯 우아한 민소매 여름 신상", "1058", "CNY"), ("접이식 차량용 노트북 책상 트레이", "89.9", "CNY"),
        ("무선 블루투스 헤드셋 노이즈캔슬링", "199", "CNY"), ("3in1 맥세이프 자석 충전 거치대", "129", "CNY"),
        ("충전식 LED 스탠드 침대 머리맡 집게등", "66", "CNY"), ("스마트워치 호환 충전 거치대 무선 이어폰 수납", "58", "CNY")]
for i, (t, pr, cur) in enumerate(seed):
    try:
        iid = CH.append(source="extension", url=f"https://item.taobao.com/item.htm?id=80000{i}", title=t, image=f"https://picsum.photos/seed/{i+10}/200",
                        price=pr, currency=cur, seller_id="default")
        if isinstance(iid, tuple): iid = iid[0]
        if i < 4:   # 손댈 것: 가격 확인 필요 표시
            CH.update(iid, seller_ids={"default"}, extra_json=json.dumps({"price_status": "needs_check", "attention": ["가격 확인 필요"]}, ensure_ascii=False))
    except Exception as e:
        print("seed fail", e)
threading.Thread(target=lambda: app.run(port=port, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
bs = next((p for p in ["/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"] if os.path.exists(p)), None)
def shot(p, path, name, full=False):
    p.goto(f"http://127.0.0.1:{port}{path}", wait_until="networkidle")
    if bs: p.add_style_tag(path=bs)
    p.wait_for_timeout(500); p.screenshot(path=f"{out}/{pre}-{name}.png", full_page=full); print(name)
with sync_playwright() as pw:
    px = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"); opts = {"executable_path": exe}
    if px: opts["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
    b = pw.chromium.launch(**opts)
    ctx = b.new_context(viewport={"width": 1480, "height": 900}, ignore_https_errors=True); p = ctx.new_page()
    shot(p, "/seller/dashboard", "d-dashboard")
    m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, ignore_https_errors=True); q = m.new_page()
    shot(q, "/seller/dashboard", "m-dashboard"); shot(q, "/seller/dashboard", "m-dashboard-full", full=True)
    b.close()
