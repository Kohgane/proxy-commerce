"""F49-T 5부 캡처 — 수집 이력 목록: 타오바오 목록 타일 수집 → 상세 보강(갤러리 1/5 · 상세 0) 뒤 행 배지.

before(main): 보강이 돌면 「보강 완료」만(이미지가 모자라도). after: 「이미지 부족 · 갤러리 1/5장 · 상세 이미지 0장」.
사용: python scripts/_devshot_f49t5.py <before|after> <out_dir>
"""
import os
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def main():
    from unittest.mock import patch
    from playwright.sync_api import sync_playwright
    import src.api.extension_api as ext
    from src.order_webhook import app
    import scripts._devshot_f51 as base
    seller = "u-shot-5"
    os.makedirs(OUT, exist_ok=True)
    with patch.object(ext, "_require_token", lambda scopes=None: {"user_id": seller}):
        with app.test_client() as c:
            d = c.post("/api/v1/collect/extension", json={
                "url": "https://item.taobao.com/item.htm?id=617129397971", "title": "随行盾 苹果手表充电支架",
                "price": "29.9", "currency": "CNY", "mode": "simple", "translate": False,
                "images": ["https://img.alicdn.com/list0.jpg"]}).get_json()
            iid = d["item_id"]
            c.post("/api/v1/collect/enrich", json={"item_id": iid, "gallery": ["https://img.alicdn.com/g1.jpg"],
                                                  "detail_images": [], "gallery_expected": 5,
                                                  "field_sources": {"images": "ice_context"}})
            with c.session_transaction() as s:
                s["user_id"] = seller
            html = c.get("/seller/collect/history").get_data(as_text=True)
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        open(f"/tmp/_5_{TAG}.html", "w").write(base._inline(html))
        pg = br.new_page(viewport={"width": 1200, "height": 900})
        pg.goto(f"file:///tmp/_5_{TAG}.html")
        pg.wait_for_timeout(300)
        row = pg.locator("tbody tr").first
        row.screenshot(path=f"{OUT}/f49t5-list-row-{TAG}.png")
        txt = row.inner_text()
        br.close()
    print(f"[{TAG}] 행:", " ".join(txt.split())[:200])


if __name__ == "__main__":
    main()
