"""Y12-A(오너 2026-10-17) — 화면 정리 전 캡처: 첫화면(수집 목록)·상품 드로어·마켓 등록본 블록·팝업·다듬기/OCR 결과줄.

VRSUK 운영값(테스트 픽스처 y11o + 10-17 운영 DB의 등록 기록·갱신 기록)을 인메모리에 심고, 마켓 상태 조회는 DB 기록 그대로 돌려준다
(밖으로 호출 없음). 화면마다 PNG + 「보이는 글자」 목록(txt). 사용: python scripts/_devshot_y12a.py before|after
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
OUT = os.path.join("docs", "screens", "y12a", *([TAG] if TAG == "after" else []))
os.makedirs(OUT, exist_ok=True)

FIX = json.load(open("tests/fixtures/y11o_vrsuk_risk.json", encoding="utf-8"))
FIX.pop("_doc", None)
UPLOADED = [
    {"at": "2026-10-15T15:38:55+00:00", "market": "coupang:gogane", "account": "gogane", "product_id": "16415921785",
     "external_url": "https://www.coupang.com/vp/products/16415921785", "market_label": "쿠팡 — 고가네", "price": {},
     "review": {"link": "https://www.coupang.com/vp/products/9778941170", "label": "승인", "state": "approved", "comment": "",
                "checked_at": "2026-10-16T16:39:18+00:00", "status_raw": "승인완료"}},
    {"at": "2026-10-15T15:38:55+00:00", "market": "coupang:woojoo", "account": "woojoo", "product_id": "16415921921",
     "external_url": "https://www.coupang.com/vp/products/16415921921", "market_label": "쿠팡 — 우주대행", "price": {},
     "review": {"link": "https://www.coupang.com/vp/products/9778941170", "label": "승인", "state": "approved", "comment": "",
                "checked_at": "2026-10-16T14:58:15+00:00", "status_raw": "승인완료"}},
    {"at": "2026-10-15T19:19:41+00:00", "market": "smartstore:chezgoga", "account": "chezgoga", "product_id": "13752236154",
     "channel_product_no": "13813465384", "external_url": "https://smartstore.naver.com/chezgoga/products/13813465384",
     "market_label": "스마트스토어 — 셰고가", "price": {}, "sent": {},
     "name_fix": {"at": "2026-10-16T05:51:57+00:00", "ok": True, "before": "[해외직구] VRSUK{비즈니스 시리즈} 심플 리클라이너 오일 왁스 가죽 사무용 회전 승강 1인 의자",
                  "after": "[해외직구] VRSUK 비즈니스 시리즈 심플 리클라이너 오일 왁스 가죽 사무용 회전 승강 1인 의자", "status_type": "SALE"},
     "detail_sync": {"at": "2026-10-17T05:10:17+00:00", "ok": True, "hash": "3040fb2999e7f23e", "same": False, "images": 21},
     "review": {"link": "https://smartstore.naver.com/chezgoga/products/13813465384", "label": "판매중", "state": "approved",
                "comment": "", "checked_at": "2026-10-16T14:58:46+00:00", "status_raw": "SALE"}},
    {"at": "2026-10-15T19:19:41+00:00", "market": "smartstore:gocosmos", "account": "gocosmos", "product_id": "13752236263",
     "channel_product_no": "13813465493", "external_url": "https://smartstore.naver.com/main/products/13813465493",
     "market_label": "스마트스토어 — 고코스모스", "price": {}, "sent": {},
     "detail_sync": {"at": "2026-10-17T05:10:25+00:00", "ok": True, "hash": "3040fb2999e7f23e", "same": False, "images": 21},
     "review": {"link": "https://smartstore.naver.com/main/products/13813465493", "label": "판매중", "state": "approved",
                "comment": "", "checked_at": "2026-10-16T10:12:09+00:00", "status_raw": "SALE"}},
]
SYNC = {m: {"at": "2026-10-17T05:10:21+00:00", "ok": True, "hash": "50a09f3009f8db4a", "error": "", "lines": 37, "state": "승인완료",
            "tries": 0, "market_status": 200} for m in ("coupang:gogane", "coupang:woojoo")}
# 운영 DB 10-17 장별 다듬기 기록(숫자·사유만) — (종류, idx, AI 호출, 캐시, 바뀐 상자, 길어서, 지우기 제안, 버림 사유들)
_A, _S, _O = "작은 장식 글자 — 원본 되살림", "원문으로 되돌림 — 원본 되살림", "원문으로 되돌리기는 다시 그리지 않음(텐센트 글자 유지)"
_L = "길어서 유지(상자에 안 들어감)"
POLISH = [("images_ko", 0, 1, 4, 4, 0, 0, []), ("detail_images_ko", 2, 1, 0, 2, 0, 0, []),
          ("detail_images_ko", 3, 0, 34, 1, 0, 16, []), ("detail_images_ko", 4, 0, 24, 7, 0, 12, ["금지어·과장(88VIP)", _A, _A, _A, _S, _A]),
          ("detail_images_ko", 5, 0, 4, 2, 0, 2, []), ("detail_images_ko", 6, 0, 3, 1, 0, 1, []),
          ("detail_images_ko", 7, 1, 0, 3, 0, 0, ["없던 상표 이름(Eames)"]), ("detail_images_ko", 9, 0, 11, 5, 0, 0, []),
          ("detail_images_ko", 10, 0, 18, 4, 0, 5, [_A]), ("detail_images_ko", 11, 0, 6, 4, 0, 0, []),
          ("detail_images_ko", 12, 0, 8, 5, 0, 0, [_S]), ("detail_images_ko", 13, 0, 19, 2, 0, 1, [_A]),
          ("detail_images_ko", 14, 0, 23, 5, 2, 0, [_O, _L, _L]), ("detail_images_ko", 15, 0, 3, 0, 0, 0, []),
          ("detail_images_ko", 16, 2, 0, 11, 0, 0, []), ("detail_images_ko", 17, 0, 14, 1, 0, 6, []),
          ("detail_images_ko", 18, 1, 0, 1, 0, 0, []), ("detail_images_ko", 19, 1, 0, 2, 0, 0, []),
          ("detail_images_ko", 20, 1, 0, 4, 2, 0, [_L, _L]), ("detail_images_ko", 21, 1, 14, 10, 0, 2, [_A, _A]),
          ("detail_images_ko", 22, 0, 5, 2, 0, 0, [_O, _O]), ("detail_images_ko", 23, 0, 5, 3, 1, 0, [_L, _S, _A, _A]),
          ("detail_images_ko", 24, 0, 10, 4, 0, 4, [_A, _A, _A]), ("detail_images_ko", 26, 0, 5, 1, 0, 4, [_A])]
for _k, _i, _c, _ca, _ch, _tl, _se, _w in POLISH:
    _ents = {int(e.get("idx", -1)): e for e in FIX.get(_k) or [] if isinstance(e, dict)}
    _e = _ents.get(_i) or {"idx": _i, "status": "done", "use": True}
    _e["polish"] = {"at": "2026-10-17T05:00:35+00:00", "calls": _c, "cached": _ca, "changed": _ch, "too_long": _tl,
                    "suggest_erase": _se, "why": "", "rows": [{"why": w} for w in _w]}
    _ents[_i] = _e
    FIX[_k] = [_ents[x] for x in sorted(_ents)]
# 운영 DB 10-17 실측 다듬기 시각·버전(장별) — 마지막 실행 = 상세 13번 한 장(10-17 05:00) → 「바뀐 장 1」
_REAL = {("images_ko", 0): ("2026-10-15T06:39:18+00:00", "edit:1")}
for _i, _t in ((2, "10-15T06:39:26"), (3, "10-15T06:39:28"), (5, "10-15T06:39:32"), (6, "10-15T06:39:35"), (7, "10-15T06:39:40"),
               (9, "10-15T06:39:43"), (11, "10-15T06:39:49"), (16, "10-15T06:40:37"), (17, "10-15T06:40:41"), (18, "10-15T06:40:47"),
               (19, "10-15T06:40:52"), (20, "10-15T06:40:59"), (14, "10-16T14:56:14"), (22, "10-16T14:56:19"), (4, "10-16T16:39:26"),
               (10, "10-16T16:39:31"), (13, "10-16T16:39:35"), (15, "10-16T16:39:38"), (21, "10-16T16:39:43"), (23, "10-16T16:39:49"),
               (24, "10-16T16:39:52"), (26, "10-16T16:39:55"), (12, "10-17T05:00:35")):
    _REAL[("detail_images_ko", _i)] = (f"2026-{_t}+00:00", None if _i in (3, 15) else "edit:1")
for _k in ("images_ko", "detail_images_ko"):
    for _e in FIX.get(_k) or []:
        _r = _REAL.get((_k, int(_e.get("idx", -1))))
        if _r and isinstance(_e.get("polish"), dict):
            _e["polish"]["at"] = _r[0]
            if _r[1]:
                _e["polish"]["version"] = _r[1]
EXTRA = dict(FIX, uploaded=UPLOADED, coupang_detail_sync=SYNC,
             title_ko="VRSUK{비즈니스 시리즈} 심플 리클라이너 오일 왁스 가죽 사무용 회전 승강 1인 의자")

# ── 운영 DB 상태를 흉내 내는 app_state(다듬기·OCR 결과 · 갱신 큐) ─────────────────────────────────────────────
from src.db import image_translate_queue_pg as Q
STATE = {
    "imgpolish:item:it-vrsuk": {"running": False, "n": 11, "done": 11, "why": "", "at": "2026-10-17T05:00:44+00:00"},
    "coupang_detail_refresh:queue": {"rows": [{"item_id": "it-vrsuk", "market": "coupang:gogane", "sid": "16415921785",
                                               "account": "gogane", "reason": "다듬은 버전", "at": "2026-10-17T05:00:44+00:00",
                                               "tries": 0, "raw": ""}]},
}
from src.services import ocr_compare_diag as D
STATE[D.item_key("it-vrsuk")] = {"item": "it-vrsuk", "at": "2026-10-17T05:00:42+00:00", "count": {"han": 0, "send": 0, "none": 1, "unknown": 0},
                                 "pages": [{"kind": "detail", "idx": 0, "no": 1, "verdict": "none", "why": "", "url": "https://img.alicdn.com/x.jpg"}]}
Q.state_get = lambda k: STATE.get(k)
Q.state_set = lambda k, v: STATE.__setitem__(k, v)
Q.counts = lambda item_id="": {"queued": 0, "running": 0}
Q.day_count = lambda k: 17   # 캡처용: 오늘 쓴 것 n

# ── 마켓 조회는 DB 기록 그대로(밖으로 호출 없음) ─────────────────────────────────────────────────────────────
from src.seller_console import listing_status as MS


def _fake(rec):
    rv = rec.get("review") or {}
    return {"state": rv.get("state") or "approved", "label": rv.get("status_raw") if rec["market"].startswith("coupang") else rv.get("label"),
            "status_raw": rv.get("status_raw") or "", "comment": "", "link": rv.get("link") or "", "error": "",
            "checked_at": "2026-10-17T05:10:18+00:00"}


MS._coupang = _fake
MS._naver = _fake

from src.seller_console import collect_history_store as ch
ch._in_memory.clear()
ch._in_memory.append({"id": "it-vrsuk", "seller_id": "u1", "source": "extension", "url": "https://item.taobao.com/item.htm?id=748639898871",
                      "domain": "item.taobao.com", "title": EXTRA["title_ko"], "image_url": (FIX.get("images") or [""])[0],
                      "price": "6995.00", "currency": "CNY", "status": "ok", "preview_url": "", "collected_at": "2026-09-27T11:05:20+00:00",
                      "extra_json": json.dumps(EXTRA, ensure_ascii=False)})

# 등록 대장(복제 등록분) — 운영 DB 실측 반려 줄 1건(Fellow Stagg, 10-17 조회) 그대로. 다른 대장 집계는 미연결로 둔다.
from src.db import market_registrations_pg as _L
_STAGG = {"marketplace": "coupang", "account": "gogane", "product_id": "16359486080", "sid": "16359486080",
          "title": "Fellow Stagg EKG Pro 구즈넥 주전자, 컬러 LCD, 스테인리스 스틸", "status": "rejected",
          "reject_kind": "unknown", "reject_comment": "판매자(A01381223) 임시저장",
          "checked_at": "2026-08-29T17:03:13+00:00"}
_L.enabled = lambda: True
_L.recent_rejected = lambda **k: [dict(_STAGG)]
_L.watch_queue = lambda **k: []

from src.order_webhook import app
PORT = 5121
threading.Thread(target=lambda: app.run(port=PORT, use_reloader=False), daemon=True).start()
time.sleep(2)
ser = app.session_interface.get_signing_serializer(app)
cookie = ser.dumps({"user_id": "u1", "user_email": "demo@goga.kr", "user_name": "데모 셀러", "user_role": "admin"})
BASE = f"http://127.0.0.1:{PORT}"

from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]


def _style(p):
    for bs in ("node_modules/bootstrap/dist/css/bootstrap.min.css", "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"):
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
    ctx = b.new_context(viewport={'width': 1280, 'height': 1000}, ignore_https_errors=True)
    ctx.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    p = ctx.new_page()
    # 1. 첫화면(수집 상품 목록)
    p.goto(BASE + "/seller/collect/history", wait_until="networkidle"); _style(p)
    tgt = p.locator("table").first
    tgt.screenshot(path=os.path.join(OUT, f"{TAG}-1-list-row.png"))
    dump("1-list-row", tgt.inner_text())
    # 4. 팝업(목록 칩 눌러서)
    titles = [x.get_attribute("title") or "" for x in p.locator("table [title]").all()]
    dump("1-list-row-hover", "\n".join(t for t in titles if t))
    chip = p.locator("[data-role='mk-chip']").first
    if chip.count():
        chip.click(); p.wait_for_timeout(1500)
        p.wait_for_timeout(2500)
        pop = p.locator("#kgpMarketStatus").first
        if pop.count():
            pop.screenshot(path=os.path.join(OUT, f"{TAG}-4-popup.png"))
            dump("4-popup", pop.inner_text())
    # 2·3. 드로어(편집 화면 drawer 모드) — 맨 위 + 마켓 등록본 블록
    p2 = ctx.new_page()
    p2.goto(BASE + "/seller/collect/preview/it-vrsuk?drawer=1", wait_until="networkidle"); _style(p2)
    p2.wait_for_timeout(1500)
    p2.screenshot(path=os.path.join(OUT, f"{TAG}-2-drawer-top.png"))
    dump("2-drawer-top", p2.locator("body").inner_text()[:6000])
    p2.wait_for_timeout(2500)
    blk = p2.locator("[data-auto-status]").first
    if blk.count():
        blk.screenshot(path=os.path.join(OUT, f"{TAG}-3-market-block.png"))
        dump("3-market-block", blk.inner_text())
    # 5-b. 쿠팡 노출 탭(다듬기·OCR 버튼과 결과줄이 보이는 자리)
    tab = p2.locator("[data-etab-btn='exposure'], button:has-text('쿠팡 노출')").first
    if tab.count():
        tab.click(); p2.wait_for_timeout(6000)
        cpx = p2.locator("[data-role='cpx-body'], .cpx").first
        if cpx.count():
            cpx.screenshot(path=os.path.join(OUT, f"{TAG}-5-exposure-tab.png"))
            dump("5-exposure-tab", cpx.inner_text())
    # 6. 대시보드(첫화면) · 7. 상품목록 — 데스크톱(1280) + 모바일(390) 전체
    for wname, vw in (("desktop", {'width': 1280, 'height': 1000}), ("mobile", {'width': 390, 'height': 844})):
        c2 = b.new_context(viewport=vw, ignore_https_errors=True, is_mobile=(wname == "mobile"))
        c2.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        pg = c2.new_page()
        for nm, path in (("6-dashboard", "/seller/"), ("7-list", "/seller/collect/history"), ("8-diagnostics", "/seller/diagnostics")):
            pg.goto(BASE + path, wait_until="networkidle"); _style(pg); pg.wait_for_timeout(1500)
            pg.screenshot(path=os.path.join(OUT, f"{TAG}-{nm}-{wname}.png"), full_page=True)
            main = pg.locator("main, .console-main, #main").first
            dump(f"{nm}-{wname}", (main if main.count() else pg.locator("body")).inner_text())
            if nm == "6-dashboard":                               # 묶음 펼침(눌러서 펼침) 상태도 한 장
                pg.evaluate("document.querySelectorAll('details.hb-card').forEach(d => d.open = true)")
                pg.wait_for_timeout(300)
                pg.screenshot(path=os.path.join(OUT, f"{TAG}-{nm}-open-{wname}.png"), full_page=True)
                dump(f"{nm}-open-{wname}", (main if main.count() else pg.locator("body")).inner_text())
        c2.close()
    b.close()

# 5. 다듬기·OCR 결과줄(드로어 버튼이 받아 그대로 보이는 줄)
cl = app.test_client()
with cl.session_transaction() as s:
    s.update({"user_id": "u1", "user_email": "demo@goga.kr", "user_role": "admin"})
lines = []
for path in ("/seller/collect/it-vrsuk/image-polish", "/seller/collect/it-vrsuk/ocr-recheck"):
    r = cl.get(path)
    lines.append(f"{path.rsplit('/', 1)[1]}: {(r.get_json() or {}).get('line')}")
from src.services import coupang_detail_refresh as CDR
lines.append("쿠팡 갱신 줄(gogane): " + CDR.sync_line(EXTRA, "coupang:gogane", "it-vrsuk"))
dump("5-result-lines", "\n".join(lines))
os._exit(0)
