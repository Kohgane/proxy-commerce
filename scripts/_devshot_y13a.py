"""Y13-A(오너 2026-10-18 15:43~15:46) — 2호 사전검증 캡처: BLACKHOLES 옵션 · 피샹리 상세 사진 판정 사유.

인메모리에 두 상품을 심는다(밖으로 호출 없음):
- BLACKHOLES(운영 301c02cd 실측) — 옵션 축 하나(颜色分类: Yellow light · White light), SKU 스펙 두 칸(「【BLACKHOLES】」 + 색)
- 피샹리(운영 6f9c7ddf 실측 10-03 기록) — 상세 1번 `//` 주소 ValueError · D3 「그릴 줄이 없습니다」 · 응답 이미지 없음 ·
  번역됨 · 24번 s.gif Data 오류. 사진 주소는 로컬 정적 그림(여기선 alicdn에 못 닿는다 — 판정 글자를 보는 캡처)
사용: python scripts/_devshot_y13a.py before|after (before는 머지 전 main 워크트리에서 돌린다)
"""
import glob
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
TAG = sys.argv[1] if len(sys.argv) > 1 else "before"
OUT = os.path.join(sys.argv[2] if len(sys.argv) > 2 else "docs/screens/y13a", TAG)
os.makedirs(OUT, exist_ok=True)

BLACKHOLES = {
    "title": "BLACKHOLES 블랙홀 미니 벽등, 영화 굿즈, 장식 모델, 피규어, 우주",
    "title_ko": "BLACKHOLES 블랙홀 미니 벽등, 영화 굿즈, 장식 모델, 피규어, 우주",
    "title_en": "【BLACKHOLES】黑洞小夜灯星际穿越电影周边摆件装饰模型手办宇宙",
    "price": "69.90", "currency": "CNY", "options_translated": True, "option_name_overrides": {"大小": "모델"},
    "options": [{"name": "颜色分类", "values": ["Yellow light", "White light"]}],
    "skus": [{"spec": ["【BLACKHOLES】", "Yellow light"], "price": "69.90", "stock": 200, "sku_id": "6129730953948",
              "currency": "CNY", "stock_text": "有货", "reference_price": "49.90", "sell_price_krw": 21900},
             {"spec": ["【BLACKHOLES】", "White light"], "price": "69.90", "stock": 200, "sku_id": "6129730953949",
              "currency": "CNY", "stock_text": "有货", "reference_price": "49.90", "sell_price_krw": 21900}],
    "images": ["/seller/static/icon-1024.png"],
}
PIC = "/seller/static/icon-1024.png"
FISH_DET = ["//img.alicdn.com/imgextra/i3/6000000007737/O1CN010wC6NJ271b2e20Ib4_!!6000000007737-0-shopmanager.jpg_1200x1200q30.jpg_.webp",
            PIC + "?p=2", PIC + "?p=3", PIC + "?p=4", PIC + "?p=7", "https://g.alicdn.com/s.gif"]
FISH = {
    "title": "菲尚丽家 单人沙发", "title_ko": "피샹리 가정용 1인용 소파 의자, 디자이너 거실 발코니 휴식용 빈백 소파",
    "price": "1999", "currency": "CNY", "images": [PIC], "detail_images": FISH_DET,
    "detail_images_ko": [
        {"idx": 0, "kind": "detail", "status": "failed", "vendor": "tencent", "error_class": "FetchFailed",
         "error_message": "이미지를 내려받지 못했습니다(ValueError)", "at": "2026-10-03T17:10:12+00:00"},
        {"idx": 1, "kind": "detail", "status": "failed", "vendor": "d3", "error_class": "RenderFailed",
         "error_message": "그릴 줄이 없습니다(원본 그대로)", "at": "2026-10-03T17:10:16+00:00"},
        {"idx": 2, "kind": "detail", "status": "failed", "vendor": "tencent", "error_class": "EmptyImage",
         "error_message": "응답에 번역 이미지가 없습니다", "at": "2026-10-03T17:10:18+00:00"},
        {"idx": 3, "kind": "detail", "status": "failed", "vendor": "d3", "error_class": "RenderFailed",
         "error_message": "그릴 줄이 없습니다(원본 그대로)", "at": "2026-10-03T17:10:40+00:00"},
        {"idx": 4, "kind": "detail", "status": "done", "vendor": "d3", "url": PIC + "?ko=7", "use": True,
         "at": "2026-10-03T17:12:49+00:00"},
        {"idx": 5, "kind": "detail", "status": "failed", "vendor": "tencent", "error_class": "TencentCloudSDKException",
         "error_code": "InvalidParameterValue.Data", "error_message": "输入Data无效，请参考Data参数说明。", "at": "2026-10-03T17:21:11+00:00"},
    ],
}

from src.db import image_translate_queue_pg as Q
STATE = {}
Q.state_get = lambda k: STATE.get(k) or {}              # 운영 state_get 계약 = 늘 dict(없으면 {})
Q.state_set = lambda k, v: STATE.__setitem__(k, v)
Q.counts = lambda item_id="": {"queued": 0, "running": 0}
Q.day_count = lambda k: 17
from src.db import market_registrations_pg as _L
_L.enabled = lambda: False

from src.seller_console import collect_history_store as ch
ch._pg_backend = lambda: None
ch._in_memory.clear()
ids = {}
for key, url, ex in (("bh", "https://item.taobao.com/item.htm?id=1077964821879", BLACKHOLES),
                     ("fish", "https://detail.tmall.com/item.htm?id=851803804374", FISH)):
    ids[key] = ch.append(source="extension", url=url, seller_id="u1", title=ex["title_ko"], price=ex["price"], currency="CNY",
                         extra=json.loads(json.dumps(ex, ensure_ascii=False)))

from src.order_webhook import app
PORT = 5131
threading.Thread(target=lambda: app.run(port=PORT, use_reloader=False), daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
BASE = f"http://127.0.0.1:{PORT}"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]


def _style(p):
    for bs in ("node_modules/bootstrap/dist/css/bootstrap.min.css", "/home/user/proxy-commerce/node_modules/bootstrap/dist/css/bootstrap.min.css"):
        if os.path.exists(bs):
            p.add_style_tag(path=bs)
            break
    p.wait_for_timeout(600)


def dump(name, text):
    lines = [ln.strip() for ln in (text or "").split("\n") if ln.strip()]
    with open(os.path.join(OUT, f"{TAG}-{name}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"== {name}: {len(lines)}줄")


def shot(ctx, iid, sel, name, wname, before_shot=None):
    pg = ctx.new_page()
    pg.goto(BASE + f"/seller/collect/preview/{iid}?drawer=1", wait_until="networkidle"); _style(pg); pg.wait_for_timeout(1200)
    if before_shot:
        before_shot(pg)
    tgt = pg.locator(sel).first
    if not tgt.count():
        dump(f"{name}-{wname}", f"(없음: {sel})")
        pg.close()
        return
    tgt.scroll_into_view_if_needed()
    tgt.screenshot(path=os.path.join(OUT, f"{TAG}-{name}-{wname}.png"))
    dump(f"{name}-{wname}", tgt.inner_text())
    pg.close()


def _open_tab(tab):
    def f(pg):
        pg.evaluate(f"(function(){{var b=document.querySelector('[data-etab=\"{tab}\"]')||document.querySelector('[onclick*=\"kgpEtab(\\'{tab}\\'\"]');"
                    f"if(window.kgpEtab) window.kgpEtab('{tab}'); else if(b) b.click();}})()")
        pg.wait_for_timeout(700)
    return f


with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    opts = {'executable_path': exe}
    if px:
        opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**opts)
    for wname, vw in (("desktop", {'width': 1280, 'height': 1000}), ("mobile", {'width': 390, 'height': 844})):
        c = b.new_context(viewport=vw, ignore_https_errors=True, is_mobile=(wname == "mobile"))
        c.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        # 1. BLACKHOLES — 옵션 탭 SKU 조합표(나가는 값)
        shot(c, ids["bh"], "[data-role=sku-table]", "1-blackholes-sku", wname, _open_tab("options"))
        # 2. 피샹리 — 상세 사진 판정표(장마다 사유)
        shot(c, ids["fish"], "[data-role=detail-plan-grid]", "2-fishangli-detail-plan", wname, _open_tab("detail"))
        c.close()
    b.close()
# 3. 같은 재료로 마켓 빌더가 내는 값(사전검증·등록 공통) — 화면 밖 근거
from src.uploaders import coupang_options as CO
lines = []
try:
    from src.seller_console.upload_dispatcher import drop_brand_option_slots as _dbs
    pd = _dbs(BLACKHOLES)
except Exception:                                                  # before(main)엔 없다
    pd = BLACKHOLES
plan = CO.plan_sku_items([{"attributeTypeName": "색상", "required": "MANDATORY"}], pd)
lines.append("쿠팡 SKU 라벨: " + " · ".join(it["label"] for it in plan.get("items") or []))
lines += ["쿠팡 보류: " + h for h in plan.get("holds") or []] or ["쿠팡 보류: 없음"]
dump("3-coupang-plan", "\n".join(lines))
os._exit(0)
