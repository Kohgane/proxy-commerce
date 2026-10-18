"""Y13-C(오너 2026-10-18 「2호 등록 직전」) — 캡처: 드로어 「등록 준비 완료」 줄 · 피샹리 배송 판정 · 옵션 축약 검사.

BLACKHOLES(운영 301c02cd 모양 — 사전검증 4마켓 통과 기록)와 피샹리(운영 6f9c7ddf 모양 — 상세 7번 규격표 글자)를 인메모리에 심고
① 드로어 위쪽(등록 준비 완료 줄)을 찍고 ② 피샹리 배송 판정 줄 · ③ 옵션 축약 검사 결과를 글자로 남긴다(밖으로 호출 없음).
사용: python scripts/_devshot_y13c.py before|after [OUT] (before는 머지 전 main 워크트리에서)
"""
import glob
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
TAG = sys.argv[1] if len(sys.argv) > 1 else "after"
OUT = os.path.join(sys.argv[2] if len(sys.argv) > 2 else "docs/screens/y13c", TAG)
os.makedirs(OUT, exist_ok=True)

MK = ["coupang:gogane", "coupang:woojoo", "smartstore:chezgoga", "smartstore:gocosmos"]
BH = {"title": "BLACKHOLES 블랙홀 미니 벽등, 영화 굿즈, 장식 모델, 피규어, 우주", "title_ko": "BLACKHOLES 블랙홀 미니 벽등, 영화 굿즈, 장식 모델, 피규어, 우주",
      "price": "69.90", "currency": "CNY", "images": ["/seller/static/icon-1024.png"],
      "pv_ready": {"ok": True, "markets": MK, "at": "2026-10-18T08:20:38+00:00", "job": "b485d656", "held": []}}
FISH_D6 = ("Parameter information 参数信息 名称/:利川转椅 填充/:3A级公仔棉 手工测量会有1-3cm的误差,请以实物为准! 菲尚 靠背宽80cm "
           "靠背高70cm 总高74cm 菲尚丽家 回朋 扶手高56cm 坐深55cm 菲尚丽家 坐高40cm 左右宽100cm 前后长114cm")

from src.db import image_translate_queue_pg as Q
Q.state_get = lambda k: {}
Q.state_set = lambda k, v: None
Q.counts = lambda item_id="": {"queued": 0, "running": 0}
from src.db import market_registrations_pg as _L
_L.enabled = lambda: False
from src.seller_console import collect_history_store as ch
ch._pg_backend = lambda: None
ch._in_memory.clear()
iid = ch.append(source="share", url="https://item.taobao.com/item.htm?id=1077964821879", seller_id="u1", title=BH["title_ko"],
                price="69.90", currency="CNY", extra=json.loads(json.dumps(BH, ensure_ascii=False)))

# ② 피샹리 배송 판정(같은 상품 · 같은 사진 글자)
lines = []
from src.seller_console import shipping_ratio as R
sofa = {"title_src": "菲尚丽家单人沙发椅设计师客厅阳台休闲懒人沙发可睡可躺舒适单椅", "title": "피샹리 1인용 소파 의자",
        "url": "https://detail.tmall.com/item.htm?id=851803804374", "price": "1999", "currency": "CNY", "photo_text": FISH_D6}
R._fx = lambda c: 107.94                      # 운영 사전검증 원가 215,766원 = 1999 × 107.94(그날 환율)
sz = R.read_size(sofa)
lines.append(f"[사진 규격 있음] 치수: {sz.get('dims_cm')} · 근거: {sz.get('basis') or '(없음)'}")
est = R.estimate(sofa)
lines.append(f"  판정: {est.get('state')} · {est.get('line')}")
if est.get("lcl"):
    lines.append(f"  LCL: {est['lcl'].get('cbm')}cbm (청구 {est['lcl'].get('qty')}cbm) → {est['lcl'].get('krw'):,}원")
nophoto = dict(sofa, photo_text="")
h = R.hold(nophoto)
lines.append(f"[사진 규격 없음] 보류: {(h or {}).get('short')} · {(h or {}).get('line')}")
# ③ 옵션 축약 검사 — 운영 10-18 08:21 버린 3건 모양
from src.services.ai_fix import short_guard
for ko, short in (("부조 직조 면마 + 고양이 발톱 가죽 검정색 프레임", "부조 면마+검정"),
                  ("리치 벨벳 그린 방석 + 고양이 스크래처 가죽 베이지색 프레임", "리치 벨벳 그린+베이지"),
                  ("실리콘가죽 아이보리 시트+스크래치방지가죽 베이지 프레임", "실리콘 아이보리+베이지")):
    lines.append(f"[축약 검사] {ko} → {short} : {short_guard(ko, short) or '통과'}")
with open(os.path.join(OUT, f"{TAG}-checks.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("\n".join(lines))

from src.order_webhook import app
PORT = 5135
threading.Thread(target=lambda: app.run(port=PORT, use_reloader=False), daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    opts = {'executable_path': exe}
    if px:
        opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**opts)
    for wname, vw in (("desktop", {'width': 1280, 'height': 1000}), ("mobile", {'width': 390, 'height': 844})):
        c = b.new_context(viewport=vw, ignore_https_errors=True, is_mobile=(wname == "mobile"))
        c.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        pg = c.new_page()
        pg.goto(f"http://127.0.0.1:{PORT}/seller/collect/preview/{iid}?drawer=1", wait_until="networkidle")
        for bs in ("node_modules/bootstrap/dist/css/bootstrap.min.css",
                   "/home/user/proxy-commerce/node_modules/bootstrap/dist/css/bootstrap.min.css"):
            if os.path.exists(bs):
                pg.add_style_tag(path=bs)
                break
        pg.wait_for_timeout(700)
        tabs = pg.locator(".kgp-etabs").first
        box = tabs.bounding_box()
        top = max(0, box["y"] - 160) if box else 0
        pg.screenshot(path=os.path.join(OUT, f"{TAG}-drawer-top-{wname}.png"),
                      clip={"x": 0, "y": top, "width": vw["width"], "height": 230})
        ready = pg.locator("[data-role=pv-ready]")
        with open(os.path.join(OUT, f"{TAG}-drawer-top-{wname}.txt"), "w", encoding="utf-8") as f:
            f.write((ready.first.inner_text() if ready.count() else "(등록 준비 완료 줄 없음)") + "\n")
        c.close()
    b.close()
os._exit(0)
