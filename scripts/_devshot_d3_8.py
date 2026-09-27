"""D3-8 캡처 — 드로어 「이미지 번역」 탭 상단 자동 번역 줄(상태 3종).

★ 공급사(Tencent)·렌더는 **테스트 대역**이다(이 샌드박스엔 키·GPU 없음) — 큐·상한·일시정지·저장은 실제 코드.
  ① 정상: 오늘 5/200장  ② 상한(=4로 낮춤): 오늘 4/4장 · 번역 대기 2장 · KST 자정 뒤  ③ 실패 20장 → 일시정지 + 「재개」
사용: python scripts/_devshot_d3_8.py <out_dir>
"""
import base64
import json
import os
import sys

OUT = sys.argv[1]
sys.argv = [sys.argv[0], "d38", OUT]   # _devshot_f51 모듈이 argv[1..2]를 읽는다
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
os.environ["IMAGE_TRANSLATE_AUTO_SYNC"] = "1"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")


def main():
    from unittest.mock import patch
    from playwright.sync_api import sync_playwright
    import scripts._devshot_f51 as base
    import src.api.extension_api as ext
    from src.db import image_translate_queue_pg as q
    from src.order_webhook import app
    from src.services import image_translate_bench as bench
    from src.services import image_translate_tencent as tc
    os.makedirs(OUT, exist_ok=True)
    fail = set()

    def _tc(url="", **k):
        if url in fail:
            return {"ok": False, "vendor": "tencent", "error_class": "TencentCloudSDKException",
                    "error_message": "FailedOperation.RequestTimeout", "ms": 5}
        return {"ok": True, "vendor": "tencent", "ms": 7, "lines": [{"source": "三合一", "target": "", "box": [0, 0, 9, 9]}]}

    def _render(raw, lines, tokens=(), gen_remove=False):
        return {"ok": True, "image_bytes": PNG, "axes": {"F": {"score": 0.4}}, "rows": [{"source": "三合一", "render_text": "3in1"}],
                "gen_remove": {"ok": True, "image_bytes": PNG, "axes": {"F": {"score": 0.7}}, "inpainter": "gen_remove"}}

    shots = []
    with patch.object(tc, "is_configured", lambda: True), patch.object(tc, "translate_image", _tc), \
            patch.object(tc, "fetch_image", lambda url: (PNG, "")), patch.object(bench, "_render_d3_for", _render):
        for tag, cap, n_fail, g in (("1-normal", "200", 0, 3), ("2-cap", "4", 0, 6), ("3-paused", "200", 20, 22)):
            q.reset_for_tests()
            os.environ["IMAGE_TRANSLATE_DAILY_CAP"] = cap
            fail.clear()
            fail.update({f"https://img.alicdn.com/g{i}.jpg" for i in range(n_fail)})
            seller = f"u-shot-d38-{tag}"
            with patch.object(ext, "_require_token", lambda scopes=None, s=seller: {"user_id": s}):
                with app.test_client() as c:
                    iid = c.post("/api/v1/collect/extension", json={
                        "url": "https://item.taobao.com/item.htm?id=617129397971", "title": "随行盾", "price": "29.9",
                        "currency": "CNY", "mode": "simple", "images": ["https://img.alicdn.com/l.jpg"], "translate": False}).get_json()["item_id"]
                    c.post("/api/v1/collect/enrich", json={"item_id": iid, "gallery_expected": g,
                                                          "gallery": [f"https://img.alicdn.com/g{i}.jpg" for i in range(g)],
                                                          "detail_images": ["https://img.alicdn.com/d0.jpg"],
                                                          "field_sources": {"images": "ice_context"}})
                    with c.session_transaction() as s:
                        s["user_id"] = seller
                    html = c.get(f"/seller/collect/preview/{iid}?drawer=1").get_data(as_text=True)
                    st = c.get(f"/seller/image-translate/auto?item={iid}").get_json()
            shots.append((tag, html, st, iid))
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        for tag, html, st, iid in shots:
            page = base._inline(html)
            open(f"/tmp/_d38_{tag}.html", "w").write(page)
            pg = br.new_page(viewport={"width": 760, "height": 900})
            body = json.dumps(st)
            pg.route("**/seller/image-translate/auto*", (lambda b: (lambda r: r.fulfill(status=200, content_type="application/json", body=b)))(body))
            pg.goto(f"file:///tmp/_d38_{tag}.html")
            pg.evaluate("() => { if (typeof kgpEtab === 'function') kgpEtab('imgko'); }")
            pg.wait_for_timeout(300)
            pg.locator('[data-role="imgko-auto"]').first.screenshot(path=f"{OUT}/d3-8-auto-{tag}.png")
            print(f"[{tag}] 상태:", {k: st.get(k) for k in ("today", "cap", "queued", "waiting_cap", "paused", "failed_since_resume")})
        br.close()


if __name__ == "__main__":
    main()
