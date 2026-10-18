"""Y12-B(오너 2026-10-17) — 대기함 결정 캡처: 수집 실패(손댈 것 / 재수집 대기) · 지우기 제안 넘김.

인메모리에 세 상품을 심는다(밖으로 호출 없음):
- VRSUK — 운영 DB 10-17 실측 지우기 제안(나가는 사진 8장: 상세 21·24·26 · 옵션 사진 5~9, 제안 글자 그대로)
- 옛 수집 — 가격·갤러리 둘 다 못 읽은 완전 수집(운영 12건과 같은 모양 · 자동 재수집 없음)
- 공유 초안 — 온바운드 자동 수집 실패 · PC 고가수집기 보강 큐 대기(운영 12건과 같은 모양)
사용: python scripts/_devshot_y12b.py before|after (before는 머지 전 main 워크트리에서 돌린다)
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
OUT = os.path.join(sys.argv[2] if len(sys.argv) > 2 else "docs/screens/y12b", TAG)
os.makedirs(OUT, exist_ok=True)

FIX = json.load(open("tests/fixtures/y11o_vrsuk_risk.json", encoding="utf-8"))
FIX.pop("_doc", None)
DET = FIX.get("detail_images") or []
# 운영 DB 10-17 실측 — 나가는 사진의 AI 지우기 제안 글자(텐센트 글자)
SUGGEST = {("detail_images_ko", 21): ["는", "ym"],
           ("detail_images_ko", 24): ["그리고 나의 집은 더 넓게", "그것이 너인가? 그것이 나인가", "내 집과 세상을 내게", "내 집을 설계하세요"],
           ("detail_images_ko", 26): ["VRSUK의 반대편", "두이 타흐트 21", "하디드", "그게 너야?"],
           ("sku_images_ko", 5): ["디센", "세카로,", "_아마 스쿼트 매스터스", "포장 내부의 소나무 연"],
           ("sku_images_ko", 6): ["디시즈", "세코크", ", 탐스 큐매트리스", "트라스엠", "공구에 나무가 있는 구"],
           ("sku_images_ko", 7): ["세코크", ".fam sqtMatt", "디카몬트", "트라스미", "리플러 냄비에 나무 연"],
           ("sku_images_ko", 8): ["정품 보장", "20년 품질 보증", "세콜로, 탐 스쿼트 매", "디시엠트", "트라스미"],
           ("sku_images_ko", 9): ["디안", "세콜로, 탐 스쿼트매트", "트라에미", "포르리에에서의 소나무"]}
FIX["skus"] = [{"sku_id": f"s{i}", "image": DET[i % len(DET)], "props": f"옵션 {i + 1}"} for i in range(10)]
FIX["sku_images_ko"] = []
for (key, idx), texts in SUGGEST.items():
    rows = FIX.setdefault(key, [])
    e = next((x for x in rows if int(x.get("idx", -1)) == idx), None)
    if e is None:
        e = {"idx": idx, "kind": "sku" if key == "sku_images_ko" else "detail"}
        rows.append(e)
    # 캡처용 썸네일 = 그 장 수집 원본(같은 그림) — 번역본 주소는 운영 Cloudinary라 여기서 못 받는다
    e.update(use=True, status="done", url=DET[idx % len(DET)])
    e["polish"] = {"at": "2026-10-16T16:39:43+00:00", "version": "edit:1", "outbound": True, "suggest_erase": len(texts),
                   "rows": [{"id": f"t{i}", "tgt": t, "ko": t, "from": "tencent", "suggest_erase": True} for i, t in enumerate(texts)]}
UPLOADED = [{"at": "2026-10-15T15:38:55+00:00", "market": "coupang:gogane", "account": "gogane", "product_id": "16415921785",
             "market_label": "쿠팡 — 고가네", "review": {"state": "approved", "status_raw": "승인완료", "checked_at": "2026-10-17T12:55:00+00:00"}},
            {"at": "2026-10-15T15:38:55+00:00", "market": "coupang:woojoo", "account": "woojoo", "product_id": "16415921921",
             "market_label": "쿠팡 — 우주대행", "review": {"state": "approved", "status_raw": "승인완료", "checked_at": "2026-10-17T17:10:20+00:00"}}]
VRSUK = dict(FIX, uploaded=UPLOADED, title_ko="VRSUK 비즈니스 시리즈 심플 리클라이너 오일 왁스 가죽 사무용 회전 승강 1인 의자")
BARE = {"title": "Vintage brass desk lamp", "source_url": "https://www.example-shop.jp/item/88231"}
WAIT = {"mode": "share", "enrich_state": "pending", "gate_ready": True, "price": "189", "title": "实木餐椅 北欧 简约",
        "auto_enrich": {"state": "manual", "kind": "provider_fail", "reason": "공급자 응답 없음", "route": "onebound",
                        "at": "2026-10-12T03:12:00+00:00"}}

from src.db import image_translate_queue_pg as Q
STATE = {}
Q.state_get = lambda k: STATE.get(k)
Q.state_set = lambda k, v: STATE.__setitem__(k, v)
Q.counts = lambda item_id="": {"queued": 0, "running": 0}
Q.day_count = lambda k: 17
from src.db import market_registrations_pg as _L
_L.enabled = lambda: False
from src.seller_console import listing_status as MS
MS.query = lambda rec, **k: dict(rec.get("review") or {}, label=(rec.get("review") or {}).get("status_raw"))

from src.seller_console import collect_history_store as ch
ch._pg_backend = lambda: None
ch._in_memory.clear()
ids = {}
for key, url, title, price, ex, at in (
        ("vrsuk", "https://item.taobao.com/item.htm?id=748639898871", VRSUK["title_ko"], "6995", VRSUK, "2026-09-27T11:05:20+00:00"),
        ("bare", "https://www.example-shop.jp/item/88231", "Vintage brass desk lamp", "", BARE, "2026-08-13T02:40:00+00:00"),
        ("wait", "https://item.taobao.com/item.htm?id=812345678901", "实木餐椅 北欧 简约", "189", WAIT, "2026-10-12T03:11:00+00:00")):
    iid = ch.append(source="extension" if key != "wait" else "share", url=url, seller_id="u1", title=title, price=price,
                    currency="CNY", extra=json.loads(json.dumps(ex, ensure_ascii=False)))
    for r in ch._in_memory:
        if r.get("id") == iid:
            r["collected_at"] = at
    ids[key] = iid

from src.order_webhook import app
PORT = 5122
threading.Thread(target=lambda: app.run(port=PORT, use_reloader=False), daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
BASE = f"http://127.0.0.1:{PORT}"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]


def _style(p):
    for bs in ("node_modules/bootstrap/dist/css/bootstrap.min.css", "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css",
               "/home/user/proxy-commerce/node_modules/bootstrap/dist/css/bootstrap.min.css"):
        if os.path.exists(bs):
            p.add_style_tag(path=bs)
            break
    p.wait_for_timeout(600)


def dump(name, text):
    lines = [ln.strip() for ln in (text or "").split("\n") if ln.strip()]
    with open(os.path.join(OUT, f"{TAG}-{name}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"== {name}: {len(lines)}줄")


def dash(b, name):
    for wname, vw in (("desktop", {'width': 1280, 'height': 900}), ("mobile", {'width': 390, 'height': 844})):
        c2 = b.new_context(viewport=vw, ignore_https_errors=True, is_mobile=(wname == "mobile"))
        c2.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        pg = c2.new_page()
        pg.goto(BASE + "/seller/", wait_until="networkidle"); _style(pg); pg.wait_for_timeout(800)
        pg.evaluate("document.querySelectorAll('details.hb-card').forEach(d => d.open = true)")
        pg.wait_for_timeout(300)
        w = pg.locator("[data-role=home-bundles]").first
        w.screenshot(path=os.path.join(OUT, f"{TAG}-{name}-{wname}.png"))
        dump(f"{name}-{wname}", w.inner_text())
        c2.close()


def drawer(ctx, name, wname, after_load=None):
    pg = ctx.new_page()
    pg.goto(BASE + f"/seller/collect/preview/{ids['vrsuk']}?drawer=1", wait_until="networkidle"); _style(pg); pg.wait_for_timeout(1200)
    if after_load:
        after_load(pg)
    box = pg.locator("[data-role=erase-suggest]").first
    tgt = box if box.count() else pg.locator(".op-card").first
    tgt.screenshot(path=os.path.join(OUT, f"{TAG}-{name}-{wname}.png"))
    dump(f"{name}-{wname}", tgt.inner_text())
    pg.close()


with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    opts = {'executable_path': exe}
    if px:
        opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**opts)
    # 1. 대시보드(묶음 펼침)
    dash(b, "1-dashboard")
    ctxs = {}
    for wname, vw in (("desktop", {'width': 1100, 'height': 1000}), ("mobile", {'width': 390, 'height': 844})):
        c = b.new_context(viewport=vw, ignore_https_errors=True, is_mobile=(wname == "mobile"))
        c.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        ctxs[wname] = c
    # 2. 드로어 맨 위(VRSUK — 지우기 제안 8장)
    for wname, c in ctxs.items():
        drawer(c, "2-drawer-erase", wname)
    # 3. 재수집 대기 상품 드로어 맨 위 한 줄
    for wname, c in ctxs.items():
        pg = c.new_page()
        pg.goto(BASE + f"/seller/collect/preview/{ids['wait']}?drawer=1", wait_until="networkidle"); _style(pg); pg.wait_for_timeout(800)
        tgt = pg.locator(".op-card").first
        tgt.screenshot(path=os.path.join(OUT, f"{TAG}-3-drawer-refetch-{wname}.png"))
        dump(f"3-drawer-refetch-{wname}", (pg.locator("[data-role=item-flags]").first.inner_text()
                                          if pg.locator("[data-role=item-flags]").count() else tgt.inner_text()[:400]))
        pg.close()
    if TAG == "after":
        # 4. 사진 하나 「넘김」 → 넘긴 제안 1(펼침)
        def _skip_one(pg):
            pg.locator("[data-role=erase-skip]").first.click()
            pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1200); _style(pg)
            pg.evaluate("document.querySelectorAll('[data-role=erase-skipped]').forEach(d => d.open = true)")
            pg.wait_for_timeout(300)
        drawer(ctxs["mobile"], "4-drawer-after-skip-one", "mobile", _skip_one)
        drawer(ctxs["desktop"], "4-drawer-after-skip-one", "desktop",
               lambda pg: (pg.evaluate("document.querySelectorAll('[data-role=erase-skipped]').forEach(d => d.open = true)"), pg.wait_for_timeout(300)))

        # 5. 「전부 넘김」 → 손댈 것에서 VRSUK가 빠짐(수집 실패 1만 남음)
        def _skip_all(pg):
            pg.locator("[data-role=erase-skip-all]").first.click()
            pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1200); _style(pg)
            pg.evaluate("document.querySelectorAll('[data-role=erase-skipped]').forEach(d => d.open = true)")
            pg.wait_for_timeout(300)
        drawer(ctxs["desktop"], "5-drawer-after-skip-all", "desktop", _skip_all)
        dash(b, "6-dashboard-after-skip-all")
        # 원본·나가는 사진 불변 증거(넘김 전후 같은 주소)
        ex = json.loads(ch.get(ids["vrsuk"], seller_ids={"u1"})["extra_json"])
        lines = []
        for (key, idx), _t in SUGGEST.items():
            e = next(x for x in ex[key] if int(x.get("idx", -1)) == idx)
            lines.append(f"{key}[{idx}] url 그대로={e['url'] == DET[idx % len(DET)]} · 넘김 글자 {len((e.get('erase_skip') or {}).get('texts') or [])}")
        lines.append(f"detail_images 원본 그대로={ex['detail_images'] == DET}")
        dump("7-pixels-untouched", "\n".join(lines))
    for c in ctxs.values():
        c.close()
    b.close()
os._exit(0)
