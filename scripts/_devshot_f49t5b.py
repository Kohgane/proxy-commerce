"""F49-T 5부-b 캡처 — 이미지 수집 점검(/seller/collect/image-audit).

오너 실측과 같은 모양으로 채운다: A 34(옛 목록 카드 — 보강 축 없음·시도 0·simple) + D 14(갤러리 ≥ 2).
before(main): 라우트가 JSON만 돌려준다. after: 요약 4칸 + 표 + 「상세 보강 다시 실행」, 누른 뒤 진행률.
사용: python scripts/_devshot_f49t5b.py <before|after> <out_dir>
"""
import html as _html
import json
import os
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
SELLER = "u-shot-5b"
TITLES = ["随行盾 苹果手表充电支架", "适用苹果手表 磁吸底座", "Ultra2 手表架 铝合金", "Airpods 耳机收纳架",
          "三合一 无线充电 支架", "带理线器 桌面收纳"]


def _seed():
    from src.seller_console import collect_history_store as S
    ids = {"A": [], "D": []}
    for i in range(34):
        iid = S.append(source="extension", seller_id=SELLER, url=f"https://item.taobao.com/item.htm?id={700000000000 + i}",
                       title=f"{TITLES[i % len(TITLES)]} {i + 1:02d}", price="29.9", currency="CNY",
                       image="https://img.alicdn.com/list.jpg",
                       extra={"mode": "simple", "images": ["https://img.alicdn.com/list.jpg"], "price": "29.9"})
        ids["A"].append(iid[0] if isinstance(iid, tuple) else iid)
    for i in range(14):
        iid = S.append(source="extension", seller_id=SELLER, url=f"https://detail.tmall.com/item.htm?id={710000000000 + i}",
                       title=f"{TITLES[i % len(TITLES)]} 상세 {i + 1:02d}", price="39.9", currency="CNY",
                       image="https://img.alicdn.com/g0.jpg",
                       extra={"mode": "full", "enriched": True, "enrich_state": "done", "price": "39.9",
                              "images": [f"https://img.alicdn.com/g{k}.jpg" for k in range(5)],
                              "field_sources": {"images": "ice_context"}})
        ids["D"].append(iid[0] if isinstance(iid, tuple) else iid)
    return ids


def main():
    from unittest.mock import patch
    from playwright.sync_api import sync_playwright
    import src.api.extension_api as ext
    from src.order_webhook import app
    import scripts._devshot_f51 as base
    os.makedirs(OUT, exist_ok=True)
    ids = _seed()
    pages = {}
    with patch.object(ext, "_require_token", lambda scopes=None: {"user_id": SELLER}):
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = SELLER
            r = c.get("/seller/collect/image-audit")
            if TAG == "before" or "json" in (r.content_type or ""):
                body = json.dumps(r.get_json(), ensure_ascii=False, indent=2)
                pages["page"] = ("<html><body style='margin:0;background:#fff'><pre style='font:13px/1.45 monospace;"
                                 "padding:16px;white-space:pre-wrap'>" + _html.escape(body) + "</pre></body></html>")
            else:
                pages["page"] = base._inline(r.get_data(as_text=True))
                d = c.post("/seller/collect/image-audit/requeue", json={"cases": ["A", "C"]}).get_json()
                print(f"[{TAG}] 되돌림 {len(d['requeued'])}건 · 남음 {d['left']}")
                for n, iid in enumerate(d["requeued"][:12]):          # 확장이 12건을 채운 시점
                    c.post("/api/v1/collect/enrich", json={
                        "item_id": iid, "gallery": [f"https://img.alicdn.com/r{n}_{k}.jpg" for k in range(4)],
                        "detail_images": [f"https://img.alicdn.com/rd{n}.jpg"], "gallery_expected": 4,
                        "field_sources": {"images": "ice_context"}})
                pages["progress"] = base._inline(c.get("/seller/collect/image-audit").get_data(as_text=True))
                print(f"[{TAG}] 진행:", c.get("/seller/collect/image-audit?format=json").get_json()["requeued"])
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        for key, html in pages.items():
            path = f"/tmp/_5b_{TAG}_{key}.html"
            open(path, "w").write(html)
            for vw, vh, suf in ((1280, 1000, ""), (390, 844, "-mobile")):
                if suf and key != "page":
                    continue
                pg = br.new_page(viewport={"width": vw, "height": vh})
                pg.goto(f"file://{path}")
                pg.wait_for_timeout(400)
                pg.screenshot(path=f"{OUT}/f49t5b-{key}-{TAG}{suf}.png")
                if not suf:
                    txt = pg.inner_text("body")
                    print(f"[{TAG}/{key}]", " ".join(txt.split())[:260])
                pg.close()
        br.close()


if __name__ == "__main__":
    main()
