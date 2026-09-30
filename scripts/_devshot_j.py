"""J 캡처 — 폰 폭 390px. before(main) / after(브랜치) 같은 스크립트로.

  audit      이미지 수집 점검(after: 옵션·상품명 번역 카드 + 글자 모양 표)
  taudit     번역 정리 점검(after 전용 — before는 없는 화면)
  guideA     아이폰 설치 화면(after: 미확인 iOS 이름에 (캡처 참고))
  empty      결과 화면 — 공유·클립보드 둘 다 빈 채로 옴(after: 붙여넣기 거부 설정 경로 자리)
  drawer     편집 서랍 상단(after: 브랜드 표기 — 확인 배지)
  card       폰 카드(after: 브랜드 배지)
사용: python scripts/_devshot_j.py <before|after> <out_dir>
"""
import json
import os
import sys
import threading

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"
os.environ["OPTION_TRANSLATE_AUTO_OFF"] = "1"
os.environ.pop("DATABASE_URL", None)
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOT = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"


def main():
    from werkzeug.serving import make_server
    from playwright.sync_api import sync_playwright
    from src.order_webhook import app

    @app.before_request
    def _as_user():
        from flask import session
        session["user_id"] = "owner-shot"
        session["user_role"] = "admin"

    from src.seller_console import collect_history_store as S
    fx = json.load(open("tests/fixtures/ko_polish/recent48_2026-09-30.json", encoding="utf-8"))
    vals = fx["vrsuk_values"][:3] + ["莫奈色溜溜鸭"]
    e0 = {"idx": 0, "status": "done", "use": True, "url": "/seller/static/og-card.png", "text_area": 0.312,
          "band": "top", "lines": 18, "source_text": fx["vrsuk_image0"]["source_text"],
          "target_text": fx["vrsuk_image0"]["target_text"]}
    e1 = {"idx": 1, "status": "done", "use": True, "url": "/seller/static/icon-512.png", "text_area": 0.084,
          "band": "", "lines": 7, "source_text": "折叠如书 小巧收纳", "target_text": "책처럼 접힘 · 작게 수납"}
    base = {"price": "6995.00", "currency": "CNY",
            "images": ["/seller/static/icon-512.png", "/seller/static/og-card.png", "/seller/static/icon-192.png"],
            "options": [{"name": "颜色分类", "values": vals,
                         "values_ko": ["", "", "", "모네 컬러"]}],
            "skus": [{"spec": [v], "price": "6995.00", "currency": "CNY", "stock": 5} for v in vals],
            "enriched": True, "enrich_state": "done"}
    iid = S.append(source="extension", url="https://detail.tmall.com/item.htm?id=5511", seller_id="owner-shot",
                   title="LANXIAOJIE 빈백 소파 1인용", price="199.00", currency="CNY",
                   extra={**base, "title": "懒小姐懒人沙发可睡可躺单人现货", "title_en": "懒小姐懒人沙发可睡可躺单人现货",
                          "title_ko": "LANXIAOJIE 빈백 소파 1인용", "title_polish_before": "LANXIAOJIE 빈백 소파 1인용 재고 있음",
                          "brand_romanized": {"han": "懒小姐", "latin": "LANXIAOJIE", "field": "shop_name"},
                          "images_ko": [e0, e1]})
    S.append(source="extension", url="https://detail.tmall.com/item.htm?id=5512", seller_id="owner-shot",
             title="VRSUK 임스 라운지 의자", price="6995.00", currency="CNY",
             extra={**base, "title": "VRSUK{商务系列}简约伊姆斯躺椅油蜡皮Eames办公旋转升降现货单椅",
                    "title_ko": "VRSUK 심플 임스 리클라이너 오일 왁스 가죽 Eames 사무용 회전 승강 1인 의자",
                    "title_polish_before": "VRSUK{비즈니스 시리즈} 심플 이임스 리클라이너 오일 왁스 가죽 Eames 사무용 회전 승강 단일 의자 재고 있음"})

    srv = make_server("127.0.0.1", 5207, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.makedirs(OUT, exist_ok=True)
    B = "http://127.0.0.1:5207"
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            ctx.route("**/*", lambda r: r.continue_() if r.request.url.startswith(B) else r.abort())
            pg = ctx.new_page()

            def shot(key, sel=None):
                pg.wait_for_timeout(500)
                if os.path.exists(BOOT):
                    pg.add_style_tag(content=open(BOOT).read())
                pg.wait_for_timeout(250)
                path = f"{OUT}/j-{key}-{TAG}.png"
                if sel and pg.locator(sel).count():
                    pg.locator(sel).first.screenshot(path=path)
                else:
                    pg.screenshot(path=path, full_page=True)
                sw = pg.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                print(f"[{TAG}/{key}] status={st} scrollWidth={sw[0]} clientWidth={sw[1]} "
                      f"hscroll={'있음' if sw[0] > sw[1] else '없음'}")

            for key, url, sel in (("audit", "/seller/collect/image-audit", None),
                                  ("taudit", "/seller/collect/translate-audit", None),
                                  ("guideA", "/seller/guide/iphone", None),
                                  ("empty", "/seller/collect/share?v=2&src=clip&text=&clip=", None),
                                  ("drawer", f"/seller/collect/preview/{iid}", None),
                                  ("card", f"/seller/m/item/{iid}", "[data-role=m5-card]")):
                r = pg.goto(B + url)
                st = r.status if r else "?"
                shot(key, sel)
            br.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
