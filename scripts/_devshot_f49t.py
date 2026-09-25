"""F49-T 캡처 — before(수리 전 트리)/after(이 브랜치) 같은 스크립트.

① 수집 화면: 티몰 URL 붙여넣기 → 실제 `/seller/collect/preview` 응답으로 화면 렌더 →
   (after) 「확장으로 열기」 · 초안이 채워진 뒤의 실제 `/seller/collect/<id>/state` 응답을 화면이 그린 모습
② 드로어: 확장이 page_diag를 실어 보낸 수집 행 → 실제 드로어 렌더(수집 로그 펼침)
사용: python _devshot_f49t.py <before|after> <out_dir>
"""
import json
import os
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOT = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
TMALL = "https://detail.tmall.com/item.htm?id=617129397971"
SELLER = "u-f49-shot"


def _inline(html):
    css = ("<style>" + open(BOOT).read() + "</style>") if os.path.exists(BOOT) else ""
    css += "<style>" + open("src/static/app.css").read() + "</style>"
    for e in ("src/seller_console/static/seller.css", "src/seller_console/static/console.css"):
        css += "<style>" + open(e).read() + "</style>"
    js = "<script>" + open("src/seller_console/static/seller.js").read() + "</script>"
    html = html.replace('<script src="/seller/static/seller.js"></script>', js)
    return html.replace("</head>", css + "</head>", 1)


def main():
    from unittest.mock import patch
    from playwright.sync_api import sync_playwright
    from src.order_webhook import app
    import src.api.extension_api as ext
    os.makedirs(OUT, exist_ok=True)

    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = SELLER
        page_html = c.get("/seller/collect").get_data(as_text=True)
        pv = c.post("/seller/collect/preview", json={"url": TMALL, "translate": False}).get_json()
        iid = pv.get("item_id")
        # 확장이 그 페이지를 열어 채운 뒤(실제 /enrich 라우트) — page_diag는 확장이 재는 모양 그대로.
        diag = {"url": TMALL, "wall": "", "nav": {"status": 200, "redirects": 1,
                "requested": "https://item.taobao.com/item.htm?id=617129397971"},
                "lazy": {"total": 14, "pending": 9}, "sel": {"gallery": 5, "detail": 14, "options": 6, "title": 1},
                "errors": []}
        with patch.object(ext, "_require_token", lambda scopes=None: {"user_id": SELLER}):
            c.post("/api/v1/collect/enrich", json={"item_id": iid, "gallery": ["https://img.alicdn.com/a.jpg"],
                                                    "price": "24", "currency": "CNY", "page_diag": diag})
        state = c.get(f"/seller/collect/{iid}/state")
        state = state.get_json() if state.status_code == 200 else None
        # 드로어 — page_diag가 실린 행
        from src.seller_console import collect_history_store as S
        extra = {"title": "SPORTLINK 随行盾", "price": "24", "currency": "CNY",
                 "images": ["https://img.alicdn.com/a.jpg"], "page_diag": diag}
        did = S.append(url=TMALL, title="SPORTLINK 随行盾", price="24", currency="CNY",
                       source="extension", seller_id=SELLER, extra=extra)
        did = did[0] if isinstance(did, tuple) else did
        drawer_html = c.get(f"/seller/collect/preview/{did}").get_data(as_text=True)

    print(f"[{TAG}] preview keys:", sorted(pv.keys()))
    print(f"[{TAG}] open_url:", pv.get("open_url", "(없음)"))
    print(f"[{TAG}] state:", json.dumps(state, ensure_ascii=False)[:300] if state else "(라우트 없음)")

    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        # ① 수집 화면
        open(f"/tmp/_f49_collect_{TAG}.html", "w").write(_inline(page_html))
        pg = br.new_page(viewport={"width": 1200, "height": 900})
        pg.goto(f"file:///tmp/_f49_collect_{TAG}.html")
        pg.wait_for_timeout(300)
        pg.evaluate("""([pv, st]) => {
          document.getElementById('productUrl').value = pv._url;
          try { currentDraft = pv.draft || {}; renderPreview(currentDraft, pv.source || 'taobao'); } catch (e) {}
          if (typeof kgpShowExtOpen === 'function') kgpShowExtOpen(pv);
          if (st && typeof kgpWatchItem === 'function') {
            // 화면의 폴링 함수가 **실제 상태 응답**을 받았을 때 그리는 모습.
            window.fetch = async () => ({ json: async () => st });
            kgpWatchItem(pv.item_id);
          }
        }""", [{**pv, "_url": TMALL}, state])
        pg.wait_for_timeout(600)
        anchor = "#extOpenBox" if pg.locator("#extOpenBox").count() else "#errorAlert"
        pg.evaluate("(a) => { const el = document.querySelector(a); if (el) { el.parentElement.style.padding = '16px'; } }", anchor)
        pg.locator(anchor).locator("xpath=..").screenshot(path=f"{OUT}/f49t-collect-{TAG}.png")
        pg.close()
        # ② 드로어 수집 로그
        open(f"/tmp/_f49_drawer_{TAG}.html", "w").write(_inline(drawer_html))
        pg = br.new_page(viewport={"width": 900, "height": 1200})
        pg.goto(f"file:///tmp/_f49_drawer_{TAG}.html")
        pg.wait_for_timeout(300)
        pg.evaluate("() => document.querySelectorAll('details').forEach(d => d.open = true)")
        log = pg.locator("details.kgp-inset").first
        log.screenshot(path=f"{OUT}/f49t-drawer-{TAG}.png")
        br.close()
    print(f"[{TAG}] saved")


if __name__ == "__main__":
    main()
