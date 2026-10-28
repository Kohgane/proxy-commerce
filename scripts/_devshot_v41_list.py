"""V41-3 캡처 — 수집한 상품 목록 1480·390. 인자: 출력 폴더, 접두, 포트."""
import sys, os, threading, time, glob, json
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"; os.environ["SECRET_KEY"] = "devshot"
out, pre, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(out, exist_ok=True)
from src.order_webhook import app
from src.seller_console import collect_history_store as CH
try: CH._in_memory.clear()
except Exception: pass
seed = [("SPORTLINK 3in1 스마트워치 호환 충전 거치대 무선 이어폰 수납 스탠드", "58"), ("3-in-1 맥세이프 호환 자석 충전식 스마트폰 거치대 무선 충전 거치대", "129"),
        ("검은색 애벌레 소파, 빈백 1인용 휴식 의자, 오리지널, 소형 주택 발코니 거실용", "1058"), ("발판, 소파 발판, 사무실 발판, 보강용 발판", "89"),
        ("BLACKHOLES 블랙홀 미니 벽돌, 벽화 굿즈, 장식 모델, 피규어, 우주", "199"), ("1인 회전 라운지 소파 의자 거실 디자이너 체어", "666")]
for i, (t, pr) in enumerate(seed):
    iid = CH.append(source="extension", url=f"https://item.taobao.com/item.htm?id=81000{i}", title=t, image=f"https://picsum.photos/seed/{i+20}/200", price=pr, currency="CNY", seller_id="default")
    iid = iid[0] if isinstance(iid, tuple) else iid
    up = []
    if i % 3 == 0: up = [{"market": "coupang:gogane", "account": "gogane", "product_id": f"1643{i}", "at": "2026-10-28T03:00:00+00:00", "review": {"state": "approved", "label": "승인완료"}},
                         {"market": "smartstore:chezgoga", "account": "chezgoga", "product_id": f"1383{i}", "channel_product_no": f"1383{i}", "at": "2026-10-28T03:00:00+00:00", "review": {"state": "approved", "label": "판매중"}}]
    if i % 3 == 1: up = [{"market": "coupang:woojoo", "account": "woojoo", "product_id": f"1644{i}", "at": "2026-10-28T03:00:00+00:00", "review": {"state": "rejected", "label": "승인반려"}}]
    if up: CH.update(iid, seller_ids={"default"}, extra_json=json.dumps({"uploaded": up}, ensure_ascii=False))
threading.Thread(target=lambda: app.run(port=port, use_reloader=False), daemon=True).start(); time.sleep(2)
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
bs = next((p for p in ["/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"] if os.path.exists(p)), None)
def shot(p, path, name):
    p.goto(f"http://127.0.0.1:{port}{path}", wait_until="networkidle")
    if bs: p.add_style_tag(path=bs)
    p.wait_for_timeout(600); p.screenshot(path=f"{out}/{pre}-{name}.png"); print(name)
with sync_playwright() as pw:
    px = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"); opts = {"executable_path": exe}
    if px: opts["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
    b = pw.chromium.launch(**opts)
    p = b.new_context(viewport={"width": 1480, "height": 900}, ignore_https_errors=True).new_page(); shot(p, "/seller/collect/history", "d-list")
    q = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, ignore_https_errors=True).new_page(); shot(q, "/seller/collect/history", "m-list")
    b.close()
