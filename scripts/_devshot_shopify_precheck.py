"""Shopify 캐너리 사전 점검 캡처 — 수행방패(중국어 원문 제목) 드로어의 제목 칸 + Shopify 사전검증 결과.

before(main): 영문 상품명 칸 없음 · 사전검증은 닿는지만 봄(중국어 제목이 통과).
after: 영문 상품명 칸(중국어 원문은 채우지 않음) · 사전검증이 「영문 제목 없음」으로 먼저 멈춤 → 칸을 채우면 통과.
사용: python scripts/_devshot_shopify_precheck.py <before|after> <out_dir>
"""
import html as _h
import json
import os
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
os.environ["SHOPIFY_SHOP"] = "catdyy-p0.myshopify.com"
os.environ["SHOPIFY_ACCESS_TOKEN"] = "dummy-for-capture"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
ZH = "随行盾(SPORTLINK)适用于苹果手表充电支架applewatch7/9底座S8无线iwatch新款Ultra2手表架Airpods耳机架"


def main():
    from unittest.mock import patch
    from playwright.sync_api import sync_playwright
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    from src.seller_console import upload_dispatcher as U
    import scripts._devshot_f51 as base
    seller = "u-shot-shopify"
    iid = S.append(source="extension", seller_id=seller, url="https://detail.tmall.com/item.htm?id=617129397971",
                   title=ZH, price="29.90", currency="CNY", image="https://img.alicdn.com/a.jpg",
                   extra={"title": ZH, "title_en": ZH, "price": "29.90", "currency": "CNY"})
    iid = iid[0] if isinstance(iid, tuple) else iid
    os.makedirs(OUT, exist_ok=True)
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = seller
        drawer = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
    d = U.UploadDispatcher()
    rows = []
    with patch.object(U, "market_reach", lambda m: {"ok": True, "ms": 42, "detail": "HTTP 200"}):
        for label, extra in (("수집된 그대로(중국어 원문)", {}), ("영문 상품명을 채운 뒤", {"title_en": "Apple Watch Charging Stand, Aluminum"})):
            pd = {"title": "수행방패 애플워치 충전 거치대", "title_en": ZH, "title_original": ZH, "price": "29.90",
                  "currency": "CNY", "images": [], **extra}
            r = d._prevalidate_market(pd, "shopify")
            rows.append((label, r.ok, r.error_code or "", r.message))
    table = "".join(f"<tr><td>{_h.escape(a)}</td><td>{'통과' if ok else '멈춤'}</td><td><code>{_h.escape(code)}</code></td>"
                    f"<td>{_h.escape(msg)}</td></tr>" for a, ok, code, msg in rows)
    pv = ("<html><body style='font:14px/1.5 sans-serif;padding:20px;background:#FBF8F1'><h3 style='margin:0 0 8px'>"
          f"Shopify 사전검증 — 수행방패 ({TAG})</h3><table border=1 cellpadding=8 style='border-collapse:collapse;background:#fff'>"
          "<tr><th>입력</th><th>결과</th><th>코드</th><th>문장</th></tr>" + table + "</table></body></html>")
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        open(f"/tmp/_sp_{TAG}.html", "w").write(base._inline(drawer))
        pg = br.new_page(viewport={"width": 760, "height": 900})
        pg.goto(f"file:///tmp/_sp_{TAG}.html")
        pg.wait_for_timeout(500)
        sec = pg.locator('.kgp-esec[data-etab="basic"]').first
        sec.screenshot(path=f"{OUT}/shopify-title-field-{TAG}.png")
        if TAG == "after":
            pg.fill("#editTitleEn", "Apple Watch 充电支架")
            pg.dispatch_event("#editTitleEn", "input")
            sec.screenshot(path=f"{OUT}/shopify-title-field-cjk-warn-{TAG}.png")
        open(f"/tmp/_sp_pv_{TAG}.html", "w").write(pv)
        p2 = br.new_page(viewport={"width": 1100, "height": 260})
        p2.goto(f"file:///tmp/_sp_pv_{TAG}.html")
        p2.screenshot(path=f"{OUT}/shopify-prevalidate-{TAG}.png")
        br.close()
    for r in rows:
        print(f"[{TAG}]", r)


if __name__ == "__main__":
    main()
