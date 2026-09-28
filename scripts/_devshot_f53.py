"""F53 캡처 — 수행방패 드로어의 쿠팡 상품명 + 쿠팡 사전검증 노트(로컬 Flask 서버에 실제 요청).

before(main): 쿠팡 상품명 칸 없음 — 쿠팡엔 `[해외직구] ` + 번역 문장 앞 50자가 간다.
after: 「쿠팡 상품명」 블록(자동 생성 — 확인 · 브랜드 위치) + 사전검증 노트.
사용: python scripts/_devshot_f53.py <before|after> <out_dir>
"""
import json
import os
import re
import sys
import threading

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
KO = ("수행 방패(SPORTLINK)는 애플 워치 충전 거치대 applewatch7 9용, S8 무선 iwatch 신형 Ultra2 시계 거치대, "
      "Airpods 이어폰 거치대")


def main():
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    from src.channel_sync._channel_bridge import to_collected
    from src.uploaders.coupang_uploader import CoupangUploader
    t = open("fixtures/realpages/diag/kgp-diagnostic-detail-tmall-com-item-htm-id-617129397971.html", encoding="utf-8").read()
    e = json.loads(re.search(r'<script type="application/json" id="kgp-diagnostic">(.*?)</script>', t, re.S).group(1))["extracted"]
    iid = S.append(source="extension", seller_id="default", url="https://detail.tmall.com/item.htm?id=617129397971",
                   title=KO, price="29.90", currency="CNY", image=(e["images"] or [""])[0],
                   extra={"title": KO, "title_ko": KO, "title_en": e["title"], "options": e["options"],
                          "skus": e["skus"], "category_code": "DIG", "price": "29.90", "currency": "CNY"})
    iid = iid[0] if isinstance(iid, tuple) else iid
    prep = CoupangUploader().prepare_product(to_collected({"title": KO, "title_ko": KO, "title_en": e["title"],
                                                           "options": e["options"], "sell_price_krw": 30000}))
    print(f"[{TAG}] 쿠팡에 갈 이름: {prep['title']!r} (source={prep.get('coupang_name_source', '(없음)')})")
    srv = make_server("127.0.0.1", 5199, app, threaded=True)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    os.makedirs(OUT, exist_ok=True)
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            pg = br.new_page(viewport={"width": 760, "height": 1000})
            pg.route("**/*", lambda r: r.continue_() if r.request.url.startswith("http://127.0.0.1:5199") else r.abort())
            pg.goto(f"http://127.0.0.1:5199/seller/collect/preview/{iid}?drawer=1", wait_until="domcontentloaded")
            pg.wait_for_timeout(1500)
            import scripts._devshot_f51 as base          # 샌드박스는 Bootstrap CDN을 막는다 — 로컬 CSS 주입
            if os.path.exists(base.BOOT):
                pg.add_style_tag(content=open(base.BOOT).read())
            try:
                pg.evaluate("() => { try { kgpEtab('basic'); } catch (e) {} }")
            except Exception:
                pass
            pg.wait_for_timeout(600)
            blk = pg.locator('[data-role="coupang-name"]')
            if blk.count():
                blk.first.scroll_into_view_if_needed()
                blk.first.screenshot(path=f"{OUT}/f53-coupang-name-{TAG}.png")
                print(f"[{TAG}] 블록:", " ".join(blk.first.inner_text().split())[:220])
            else:
                target = pg.locator('.kgp-esec[data-etab="basic"]').first
                target.scroll_into_view_if_needed()
                target.screenshot(path=f"{OUT}/f53-coupang-name-{TAG}.png")
                print(f"[{TAG}] 쿠팡 상품명 블록 없음")
            br.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
