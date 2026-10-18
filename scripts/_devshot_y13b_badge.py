"""Y13-A 10(오너 16:41) — 「세/셰」: 플리츠 실데이터(운영 ae9cee70 — 제목·4마켓 등록 기록)로 목록 한 줄 390px 렌더.
제목 말줄임이 뱃지 옆에서 「…여름 세」로 끊기는지 · 뱃지 약자가 「셰」인지 잰다(글자 단위 위치 측정 + 캡처)."""
import glob, json, os, sys, threading, time
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
OUT = "docs/screens/y13b"; os.makedirs(OUT, exist_ok=True)
TITLE = "플리츠 미니멀 여성 여름 세트, 디자인 감각이 돋보이는 언밸런스 컷팅 주름 스커트 + 반팔 상의"
UP = [{"market": "coupang", "market_label": "쿠팡", "product_id": "16401838524", "at": "2026-10-02T03:00:00+00:00",
       "review": {"state": "approved", "status_raw": "승인완료"}},
      {"market": "coupang:woojoo", "account": "woojoo", "market_label": "쿠팡 — 우주대행", "product_id": "16410000001",
       "at": "2026-10-09T03:00:00+00:00", "review": {"state": "approved", "status_raw": "승인완료"}},
      {"market": "smartstore:chezgoga", "account": "chezgoga", "market_label": "스마트스토어 — 셰고가", "product_id": "13742360000",
       "channel_product_no": "13803530000", "at": "2026-10-10T12:00:00+00:00", "review": {"state": "approved", "status_raw": "판매중"}},
      {"market": "smartstore:gocosmos", "account": "gocosmos", "market_label": "스마트스토어 — 고코스모스", "product_id": "13742367344",
       "channel_product_no": "13803531537", "at": "2026-10-10T12:11:33+00:00"}]
from src.db import image_translate_queue_pg as Q
ST = {}
Q.state_get = lambda k: ST.get(k) or {}
Q.state_set = lambda k, v: ST.__setitem__(k, v)
from src.seller_console import collect_history_store as ch
ch._pg_backend = lambda: None
ch._in_memory.clear()
iid = ch.append(source="extension", url="https://item.taobao.com/item.htm?id=1", seller_id="u1", title=TITLE, price="129", currency="CNY",
                extra={"title_ko": TITLE, "uploaded": UP, "images": ["/seller/static/icon-1024.png"], "price": "129"})
from src.order_webhook import app
PORT = 5133
threading.Thread(target=lambda: app.run(port=PORT, use_reloader=False), daemon=True).start(); time.sleep(2)
cookie = app.session_interface.get_signing_serializer(app).dumps({"user_id": "u1", "user_email": "d@goga.kr", "user_role": "admin"})
from playwright.sync_api import sync_playwright
exe = glob.glob('/opt/pw-browsers/chromium-*/chrome-linux*/chrome')[0]
with sync_playwright() as pw:
    px = os.environ.get('HTTPS_PROXY')
    b = pw.chromium.launch(executable_path=exe, **({'proxy': {'server': px, 'bypass': '127.0.0.1,localhost'}} if px else {}))
    res = {}
    for w in (390, 360, 1280):
        c = b.new_context(viewport={'width': w, 'height': 800}, is_mobile=w < 500)
        c.add_cookies([{'name': 'session', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
        pg = c.new_page(); pg.goto(f"http://127.0.0.1:{PORT}/seller/collect/history?days=3650", wait_until="networkidle")
        for bs in ("node_modules/bootstrap/dist/css/bootstrap.min.css",):
            if os.path.exists(bs): pg.add_style_tag(path=bs)
        pg.wait_for_timeout(800)
        row = pg.locator(f"tr[data-item-id='{iid}']").first
        row.screenshot(path=f"{OUT}/badge-row-{w}.png")
        res[w] = pg.evaluate("""(id) => {
          const tr = document.querySelector(`tr[data-item-id='${id}']`);
          const a = tr.querySelector('.ch-title-1'); const r = a.getBoundingClientRect();
          // 보이는 마지막 글자: 글자마다 Range 사각형이 제목 칸 오른쪽 끝(말줄임 자리 제외) 안에 있나
          const t = a.firstChild; let last = -1; const rg = document.createRange();
          const cell = a.closest('td').getBoundingClientRect();
          for (let i = 0; i < t.length; i++) { rg.setStart(t, i); rg.setEnd(t, i + 1); const b = rg.getBoundingClientRect();
            if (b.right <= cell.right - 12 && b.width > 0) last = i; }
          const shorts = [...tr.querySelectorAll('.mk-badge .mk-short')].filter(s => getComputedStyle(s).display !== 'none').map(s => s.textContent);
          const fulls = [...tr.querySelectorAll('.mk-badge .mk-full')].filter(s => getComputedStyle(s).display !== 'none').map(s => s.textContent);
          return {visible_title_tail: t.data.slice(Math.max(0, last - 6), last + 1), overflow: a.scrollWidth > a.clientWidth,
                  badge_short: shorts, badge_full: fulls};
        }""", iid)
        c.close()
    b.close()
json.dump(res, open(f"{OUT}/badge-measure.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(res, ensure_ascii=False))
os._exit(0)
