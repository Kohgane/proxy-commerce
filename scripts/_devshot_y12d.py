"""Y12-D(오너 2026-10-18) — 백필 후속 캡처(1280·390): 재수집 대기 「n일째」 · 7일 넘으면 「수집기 안 돎」 · 수집 실패 「다시 수집」·「버리기」 · 버린 상품 드로어 「되살리기」.

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
OUT = os.path.join(sys.argv[2] if len(sys.argv) > 2 else "docs/screens/y12d", TAG)
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
UPLOADED_OLD = [{"at": "2026-10-15T15:38:55+00:00", "market": "coupang:gogane", "account": "gogane", "product_id": "16415921785",
             "market_label": "쿠팡 — 고가네", "review": {"state": "approved", "status_raw": "승인완료", "checked_at": "2026-10-17T12:55:00+00:00"}},
            {"at": "2026-10-15T15:38:55+00:00", "market": "coupang:woojoo", "account": "woojoo", "product_id": "16415921921",
             "market_label": "쿠팡 — 우주대행", "review": {"state": "approved", "status_raw": "승인완료", "checked_at": "2026-10-17T17:10:20+00:00"}}]
# 운영 DB 10-18 실측 등록 기록(VRSUK 4마켓 · 플리츠 4마켓 — 옛 `coupang` = 고가네 16401838524)
UPLOADED = UPLOADED_OLD + [
    {"at": "2026-10-15T19:19:41+00:00", "market": "smartstore:chezgoga", "account": "chezgoga", "product_id": "13752236154",
     "channel_product_no": "13813465384", "market_label": "스마트스토어 — 셰고가",
     "review": {"state": "approved", "status_raw": "SALE", "label": "판매중", "checked_at": "2026-10-16T14:58:46+00:00"}},
    {"at": "2026-10-15T19:19:41+00:00", "market": "smartstore:gocosmos", "account": "gocosmos", "product_id": "13752236263",
     "channel_product_no": "13813465493", "market_label": "스마트스토어 — 고코스모스",
     "review": {"state": "approved", "status_raw": "SALE", "label": "판매중", "checked_at": "2026-10-16T10:12:09+00:00"}}]
PLEATS = [{"market": "coupang", "market_label": "쿠팡", "product_id": "16401838524", "at": "2026-10-02T09:54:59+00:00",
           "review": {"state": "approved", "checked_at": "2026-10-08T07:26:33+00:00"}},
          {"market": "coupang:woojoo", "market_label": "쿠팡 — 우주대행", "account": "woojoo", "product_id": "16407690349",
           "at": "2026-10-08T07:26:18+00:00", "review": {"state": "approved", "status_raw": "승인완료", "checked_at": "2026-10-10T13:57:15+00:00"}},
          {"market": "smartstore:chezgoga", "market_label": "스마트스토어 — 셰고가", "account": "chezgoga", "product_id": "13742149801",
           "at": "2026-10-10T09:09:11+00:00", "review": {"state": "approved", "status_raw": "SALE", "checked_at": "2026-10-10T15:33:01+00:00"}},
          {"market": "smartstore:gocosmos", "market_label": "스마트스토어 — 고코스모스", "account": "gocosmos", "product_id": "13742367344",
           "at": "2026-10-10T12:11:33+00:00"}]
VRSUK = dict(FIX, uploaded=UPLOADED, title_ko="VRSUK{비즈니스 시리즈} 심플 리클라이너 오일 왁스 가죽 사무용 회전 승강 1인 의자",
             coupang_detail_sync={m: {"at": "2026-10-17T05:10:21+00:00", "ok": True, "state": "승인완료"} for m in ("coupang:gogane", "coupang:woojoo")})
PLEATS_EX = {"title_ko": "플리츠 미니멀 여성 여름 세트, 디자인 감각이 돋보이는 언밸런스 컷팅", "price": "89", "images": [DET[0]], "uploaded": PLEATS}
BARE = {"title": "Vintage brass desk lamp", "source_url": "https://www.example-shop.jp/item/88231"}
from datetime import datetime as _dt, timedelta as _td, timezone as _tz
_ago = lambda d: (_dt.now(_tz.utc) - _td(days=d)).isoformat()
WAIT = {"mode": "share", "enrich_state": "pending", "gate_ready": True, "price": "189", "title": "实木餐椅 北欧 简约",
        "auto_enrich": {"state": "manual", "kind": "provider_fail", "reason": "공급자 응답 없음", "route": "onebound", "at": _ago(2)}}
STALE = {"mode": "share", "enrich_state": "pending", "gate_ready": True, "price": "56", "title": "北欧 落地灯 客厅",
         "auto_enrich": {"state": "manual", "kind": "provider_fail", "reason": "공급자 응답 없음", "route": "onebound", "at": _ago(21)}}

from src.db import image_translate_queue_pg as Q
STATE = {}
Q.state_get = lambda k: STATE.get(k) or {}
Q.state_set = lambda k, v: STATE.__setitem__(k, v)
Q.counts = lambda item_id="": {"queued": 0, "running": 0}
# Y12-D 7: PC 수집기 마지막 신호 = 3시간 전 보강 폴링(1.5.160) — 끊긴 채 재수집 대기 → 손댈 것 「PC에서 콘솔 탭 열기」
STATE["ext_beat:u1"] = {"at": (_dt.now(_tz.utc) - _td(hours=3)).isoformat(), "version": "1.5.160", "source": "poll"}
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
        ("wait", "https://item.taobao.com/item.htm?id=812345678901", "实木餐椅 北欧 简约", "189", WAIT, "2026-10-12T03:11:00+00:00"),
        ("pleats", "https://item.taobao.com/item.htm?id=700000000001", PLEATS_EX["title_ko"], "89", PLEATS_EX, "2026-10-01T02:00:00+00:00"),
        ("chair", "https://item.taobao.com/item.htm?id=700000000002", "중력 밸런스 체어", "320", {"title_ko": "중력 밸런스 체어", "price": "320", "images": [DET[1]]}, "2026-10-12T05:00:00+00:00"),
        ("stale", "https://item.taobao.com/item.htm?id=700000000003", "北欧 落地灯 客厅", "56", STALE, "2026-09-26T05:00:00+00:00"),
        ("qa", "https://QA-TEST-persistence.example/1", "QA-TEST- 영속성 실증 마커", "", {"title": "QA-TEST- 영속성 실증 마커"}, "2026-08-13T02:00:00+00:00")):
    iid = ch.append(source="extension" if key != "wait" else "share", url=url, seller_id="u1", title=title, price=price,
                    currency="CNY", extra=json.loads(json.dumps(ex, ensure_ascii=False)))
    for r in ch._in_memory:
        if r.get("id") == iid:
            r["collected_at"] = at
    ids[key] = iid
for r in ch._in_memory:                                           # 시험 계정 행 — 오너 화면·전체 집계 어디에도 안 섞여야 한다
    if r.get("id") == ids.get("qa"):
        r["seller_id"] = "QA-TEST-seller"


from src.services import image_translate_auto as _A
from src.services import image_polish as _IP
_IP.today_count = lambda: 24                                    # 캡처용: 오늘 다듬기 n
from src.order_webhook import app
PORT = 5124
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


with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY')
    opts = {'executable_path': exe}
    if px:
        opts['proxy'] = {'server': px, 'bypass': '127.0.0.1,localhost'}
    b = pw.chromium.launch(**opts)
    for wname, vw in (("desktop", {'width': 1280, 'height': 900}), ("mobile", {'width': 390, 'height': 844})):
        c = b.new_context(viewport=vw, ignore_https_errors=True, is_mobile=(wname == "mobile"))
        c.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        pg = c.new_page()
        for nm, path in (("1-dashboard", "/seller/"), ("2-list", "/seller/collect/history?days=3650"),
                         ("7-list-mk-cell", "/seller/collect/history?mk=coupang%3Agogane&mst=sale&days=3650")):
            pg.goto(BASE + path, wait_until="networkidle"); _style(pg); pg.wait_for_timeout(1000)
            pg.evaluate("document.querySelectorAll('details.hb-card').forEach(d => d.open = true)")
            pg.screenshot(path=os.path.join(OUT, f"{TAG}-{nm}-{wname}.png"), full_page=True)
            main = pg.locator("[data-role=home-bundles]").first if nm == "1-dashboard" else pg.locator("main, .console-main, #main").first
            dump(f"{nm}-{wname}", (main if main.count() else pg.locator("body")).inner_text())
            if nm.startswith("2-list"):
                badges = pg.evaluate("Array.from(document.querySelectorAll('tr.ch-row')).map(r => (r.querySelector('.ch-title-1')||{}).textContent + ' | ' + Array.from(r.querySelectorAll('.mk-badge')).map(b => (b.getAttribute('data-slot')||b.getAttribute('data-market-status')||'') + ':' + (getComputedStyle(b.querySelector('.mk-short')||b).display==='none' ? (b.querySelector('.mk-full')||b).textContent : (b.querySelector('.mk-short')||b).textContent)).join(' '))")
                dump(f"2-list-badges-{wname}", "\n".join(badges))
        if TAG == "after":
            # 3. 수집 실패 줄 「버리기」 → 손댈 것에서 빠진 대시보드 · 4. 버린 상품 드로어(되살리기) · 5. 버린 상품 목록
            pg.goto(BASE + "/seller/", wait_until="networkidle"); _style(pg); pg.wait_for_timeout(600)
            btn = pg.locator(f"[data-role=hb-discard][data-id='{ids['bare']}']").first
            if btn.count():
                btn.click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(1200); _style(pg)
            w = pg.locator("[data-role=home-bundles]").first
            w.screenshot(path=os.path.join(OUT, f"{TAG}-3-dashboard-after-discard-{wname}.png"))
            dump(f"3-dashboard-after-discard-{wname}", w.inner_text())
            pg.goto(BASE + f"/seller/collect/preview/{ids['bare']}?drawer=1", wait_until="networkidle"); _style(pg); pg.wait_for_timeout(800)
            card = pg.locator(".op-card").first
            card.screenshot(path=os.path.join(OUT, f"{TAG}-4-drawer-discarded-{wname}.png"))
            dump(f"4-drawer-discarded-{wname}", pg.locator("[data-role=discard-line]").first.inner_text())
            pg.goto(BASE + "/seller/collect/history?discarded=1&days=3650", wait_until="networkidle"); _style(pg); pg.wait_for_timeout(800)
            pg.screenshot(path=os.path.join(OUT, f"{TAG}-5-list-discarded-{wname}.png"), full_page=True)
            dump(f"5-list-discarded-{wname}", pg.locator("main, .console-main, #main").first.inner_text())
            pg.goto(BASE + f"/seller/collect/preview/{ids['bare']}?drawer=1", wait_until="networkidle"); pg.wait_for_timeout(500)
            rb = pg.locator("[data-role=discard-btn][data-restore='1']").first
            if rb.count():                                        # 되살려 두고 다음 폭(390)도 같은 상태에서 찍는다
                rb.click(); pg.wait_for_load_state("networkidle"); pg.wait_for_timeout(800)
        c.close()
    b.close()
from src.seller_console import collect_history_store as _S
dump("6-unscoped-totals", f"셀러 안 정한 전체 수집 {_S.summary(days=3650)['total']}건 · 시험 계정 행 포함 여부 "
     f"{ids['qa'] in {r['id'] for r in _S.list_items(days=3650)}}")
os._exit(0)
