"""M1 캡처 — 375px 모바일 뷰. 같은 스크립트를 main 워크트리(before)와 작업 트리(after)에서 돌린다.

장면(오너 브리프 M1 1~4):
  env   쿠팡 출고지·반품지가 빈 채로 사전검증·등록 → 편집 화면의 결과 칸(실제 라우트·실제 렌더 함수)
  ext   서버가 못 여는 타오바오 초안 → 「확장으로 열기」 칸(모바일 UA)
  hint  현지화 locale 고르는 칸의 「Ctrl/Cmd + 클릭」 안내
  loc   현지화 결과가 `unchanged` + 상세설명 빈 칸

쿠팡 API는 부르지 않는다 — 출고지·반품지가 비면 **전송 전에** 막히는 경로라 네트워크가 필요 없다.

사용: python scripts/_devshot_m1.py <before|after> <out_dir>
"""
import json
import os
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ.pop("DATABASE_URL", None)
os.environ["COUPANG_IMAGE_SCREEN"] = "0"
for k in list(os.environ):
    if k.startswith("COUPANG_"):
        os.environ.pop(k)
# API 자격은 있고 출고지·반품지만 비었다 — 오너 실측 모양(「환경변수를 Wing 배송정보 값으로…」가 뜬 상태)
os.environ.update({"COUPANG_ACCESS_KEY": "ak", "COUPANG_SECRET_KEY": "sk", "COUPANG_VENDOR_ID": "A0001"})

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
MOBILE_UA = ("Mozilla/5.0 (Linux; Android 14; SM-S918N) AppleWebKit/537.36 (KHTML, like Gecko) "
             "Chrome/128.0.0.0 Mobile Safari/537.36")


def _inline(html):
    css = ""
    if os.path.exists(BOOTSTRAP):
        css += "<style>" + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    css += "<style>" + open("src/static/app.css", encoding="utf-8").read() + "</style>"
    for e in EXTRA_CSS:
        if os.path.exists(e):
            css += "<style>" + open(e, encoding="utf-8").read() + "</style>"
    js = "<script>" + open("src/seller_console/static/seller.js", encoding="utf-8").read() + "</script>"
    html = html.replace('<script src="/seller/static/seller.js"></script>', js)
    return html.replace("</head>", css + "</head>", 1)


def main():
    import contextlib
    from unittest.mock import patch
    from playwright.sync_api import sync_playwright
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    from src.seller_console.upload_dispatcher import UploadDispatcher

    os.makedirs(OUT, exist_ok=True)
    product = {"title": "卫生间厕纸盒 双位纸巾架", "price": 24000, "currency": "KRW", "sku": "1064346880857",
               "images": ["https://img.example/1.jpg"], "description": "상세", "origin": "중국",
               "source_url": "https://detail.tmall.com/item.htm?id=1064346880857"}
    item_id = S.append(url=product["source_url"], title=product["title"], price="24000",
                       currency="KRW", source="extension", seller_id="default",
                       extra={"images": product["images"]})
    if isinstance(item_id, tuple):
        item_id = item_id[0]
    with patch("urllib.request.urlopen", lambda *a, **k: contextlib.nullcontext()), \
            patch("time.sleep", lambda s: None):
        disp = UploadDispatcher().dispatch(product, ["coupang"]).to_dict()
        with app.test_client() as c:
            with c.session_transaction() as s:
                s["user_id"] = "default"
            pre = c.post("/seller/collect/prevalidate",
                         json={"product": product, "markets": ["coupang"]}).get_json()["results"]
            prev_html = c.get(f"/seller/collect/preview/{item_id}").get_data(as_text=True)
            mc_html = c.get("/seller/collect").get_data(as_text=True)
    print(f"[{TAG}] prevalidate:", json.dumps(pre, ensure_ascii=False)[:500])
    print(f"[{TAG}] dispatch:", json.dumps(disp["results"], ensure_ascii=False)[:500])

    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        ctx = br.new_context(viewport={"width": 375, "height": 812}, user_agent=MOBILE_UA,
                             device_scale_factor=2, is_mobile=True, has_touch=True)

        # ① env — 편집 화면의 사전검증·등록 결과(실제 렌더 함수)
        path = f"/tmp/_m1_prev_{TAG}.html"
        open(path, "w", encoding="utf-8").write(_inline(prev_html))
        pg = ctx.new_page()
        pg.goto(f"file://{path}")
        pg.wait_for_timeout(400)
        pg.evaluate("""([pre, disp]) => {
          renderPrevalidateResults(pre);
          renderUploadResults({ok: true, result: disp});
          const box = document.createElement('div');
          box.id = 'm1shot';
          box.style.cssText = 'padding:16px;background:var(--paper,#fff)';
          box.innerHTML = '<h6 class="pc-overline">사전검증</h6>'
            + document.getElementById('prevalidateResults').innerHTML
            + '<h6 class="pc-overline mt-3">등록 결과</h6>'
            + document.getElementById('uploadResults').innerHTML;
          document.body.innerHTML = '';
          document.body.appendChild(box);
        }""", [pre, disp])
        pg.wait_for_timeout(200)
        pg.locator("#m1shot").screenshot(path=f"{OUT}/m1-env-{TAG}.png")
        pg.close()

        # ②③④ 수집 화면 — 실제 페이지 JS를 모바일 UA로
        path = f"/tmp/_m1_mc_{TAG}.html"
        open(path, "w", encoding="utf-8").write(_inline(mc_html))
        pg = ctx.new_page()
        pg.route("https://*/**", lambda r: r.fulfill(status=204, body=""))
        pg.goto(f"file://{path}")
        pg.wait_for_timeout(400)
        pg.evaluate("""() => {
          currentDraft = {title: '卫生间厕纸盒 双位纸巾架', price: '175.50', currency: 'CNY', images: []};
          renderPreview(currentDraft, 'share_draft');
          kgpShowExtOpen({open_url: 'https://detail.tmall.com/item.htm?id=1064346880857', item_id: 'demo1'});
          localizedDrafts = {'ko-KR': {status: 'unchanged', language: 'ko',
                                       title: '욕실 휴지함 2단 휴지걸이', description: ''}};
          renderLocalizedPreview();
        }""")
        pg.wait_for_timeout(300)
        pg.locator("#extOpenBox").screenshot(path=f"{OUT}/m1-ext-{TAG}.png")
        pg.locator("#targetLocales").locator("xpath=..").screenshot(path=f"{OUT}/m1-hint-{TAG}.png")
        pg.locator("#localizedPreview").screenshot(path=f"{OUT}/m1-loc-{TAG}.png")
        sw = pg.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        print(f"[{TAG}] collect page scrollWidth/clientWidth:", sw)
        pg.close()
        br.close()
    print("saved", OUT)


if __name__ == "__main__":
    main()
