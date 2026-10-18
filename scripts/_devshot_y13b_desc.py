"""Y13-B(런북 2호 대조 BLACKHOLES 301c02cd) — 상세 설명: 옵션 요약 줄 브랜드 조각·라틴 값 · 가게 UI 줄.

저장 초안(운영 10-10 13:34 stub 실측)을 인메모리에 심고 ① 드로어 상세 탭 「마켓 전송 미리보기」를 찍고
② 등록 빌더가 내는 상세(`apply_outbound_text`)를 글자로 남긴다. ②의 한자 줄 번역은 텐센트 대신 고정 사전으로 대신한다
(밖으로 호출 없음 — 운영 사전검증이 「원문 2칸 자동 번역」으로 옮긴 그 두 줄, 운영 Y7-N 주석의 번역문).
사용: python scripts/_devshot_y13b_desc.py before|after [OUT] (before는 머지 전 main 워크트리에서)
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
OUT = os.path.join(sys.argv[2] if len(sys.argv) > 2 else "docs/screens/y13b", TAG)
os.makedirs(OUT, exist_ok=True)

DRAFT = ("BLACKHOLES 블랙홀 미니 벽등, 영화 굿즈, 장식 모델, 피규어, 우주\n\n■ 옵션·상세\n"
         "· 사이즈는 【BLACKHOLES】 한 가지예요.\n· 색상은 Yellow light, White light 2가지 중에서 고를 수 있어요.\n\n"
         "■ 원문 상세\n沉默流浪汉\n平均2天内发货\n\n■ 배송·구매대행 안내\n"
         "· 해외 구매대행 상품으로, 주문 후 현지 배송·통관을 거쳐 발송됩니다.\n"
         "· 모니터·조명 환경에 따라 실제 색상과 차이가 있을 수 있습니다.\n"
         "· 정확한 사이즈·소재는 위 옵션·상세 정보를 확인해 주세요.\n· 교환·반품은 판매 마켓과 구매대행 정책을 따릅니다.")
BH = {"title": "BLACKHOLES 블랙홀 미니 벽등, 영화 굿즈, 장식 모델, 피규어, 우주",
      "title_ko": "BLACKHOLES 블랙홀 미니 벽등, 영화 굿즈, 장식 모델, 피규어, 우주",
      "title_en": "【BLACKHOLES】黑洞小夜灯星际穿越电影周边摆件装饰模型手办宇宙", "price": "69.90", "currency": "CNY",
      "options": [{"name": "颜色分类", "values": ["Yellow light", "White light"]}],
      "description": DRAFT, "description_ko": DRAFT, "detail_auto": {"text": DRAFT, "v": 2, "provider": "stub"},
      "images": ["/seller/static/icon-1024.png"]}
FIXED = {"沉默流浪汉": "침묵의 방랑자", "平均2天内发货": "평균 2일 이내 발송"}

from src.db import image_translate_queue_pg as Q
Q.state_get = lambda k: {}
Q.state_set = lambda k, v: None
Q.counts = lambda item_id="": {"queued": 0, "running": 0}
from src.db import market_registrations_pg as _L
_L.enabled = lambda: False
from src.seller_console import collect_history_store as ch
ch._pg_backend = lambda: None
ch._in_memory.clear()
iid = ch.append(source="share", url="https://item.taobao.com/item.htm?id=1077964821879", seller_id="u1",
                title=BH["title_ko"], price="69.90", currency="CNY", extra=json.loads(json.dumps(BH, ensure_ascii=False)))

# ② 등록 빌더가 내는 상세(번역은 고정 사전)
from src.uploaders import detail_translate as DT


def _fake_outbound(text):
    lines = [FIXED.get(ln.strip(), ln) for ln in str(text).split("\n")]
    n = sum(1 for ln in str(text).split("\n") if ln.strip() in FIXED)
    return {"text": "\n".join(lines), "translated": n, "failed": 0, "why": "", "page_ui_removed": 0}


DT.outbound = _fake_outbound
from src.seller_console.upload_dispatcher import apply_outbound_text
out = apply_outbound_text(dict(BH))
with open(os.path.join(OUT, f"{TAG}-outbound-description.txt"), "w", encoding="utf-8") as f:
    f.write("[쿠팡·네이버 공통 상세 — description]\n" + out["description"] + "\n\n[네이버 자동 초안 — detail_auto.text]\n"
            + str((out.get("detail_auto") or {}).get("text") or "") + "\n")
print(out["description"])

from src.order_webhook import app
PORT = 5133
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
        pg.evaluate("window.kgpEtab && window.kgpEtab('detail')")
        pg.wait_for_timeout(600)
        d = pg.locator("[data-role=market-desc-preview]").first
        d.evaluate("e => e.open = true")
        d.scroll_into_view_if_needed()
        d.screenshot(path=os.path.join(OUT, f"{TAG}-desc-preview-{wname}.png"))
        with open(os.path.join(OUT, f"{TAG}-desc-preview-{wname}.txt"), "w", encoding="utf-8") as f:
            f.write(d.inner_text() + "\n")
        c.close()
    b.close()
os._exit(0)
