"""개발용 스크린샷 — 디자인 v3 Stage 6-c: 수집한 상품 + 편집 드로어.

**캡처 계약(오너):** 0데이터 / 실데이터 / 390px 3벌, **원본 해상도 단독**(축소 병치 금지).
드로어는 iframe으로 실제 편집 화면을 얹는 구조라, 목록 위에 **실제 드로어 마크업**을 열어 찍는다.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
OUT_DIR = "docs/screens/v40s6c"
DESKTOP = (1920, 940)
MOBILE = (390, 844)

AUDIT = """() => {
  const px = v => Math.round(v);
  const vw = innerWidth, vh = innerHeight;
  const cards = [...document.querySelectorAll('.op-card')];
  const inline = [...document.querySelectorAll('[style]')]
    .filter(e => /#[0-9a-fA-F]{3,8}|rgba?\\(|\\d+px/.test(e.getAttribute('style') || '')).length;
  const small = [...document.querySelectorAll('.ch-page a.btn, .ch-page button, .ch-page select')]
    .filter(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.height < 44; }).length;
  return {
    vw, vh,
    pageHeight: document.documentElement.scrollHeight,
    bodyScrollX: document.documentElement.scrollWidth > vw + 1,
    cards: cards.length,
    styleTags: document.querySelectorAll('style').length,
    inlineHardcoded: inline,
    smallTargets: small,
    cols: (() => { const s = document.querySelector('.ch-page');
      return s ? getComputedStyle(s).gridTemplateColumns.split(' ').length : 0; })(),
    tiles: document.querySelectorAll('.op-tile').length,
    rows: document.querySelectorAll('.ch-card-table tbody tr').length,
    empty: !!document.querySelector('.console-empty-state'),
    toolbarInFoot: !!document.querySelector('.op-card-foot.pc-bulk-toolbar'),
  };
}"""


def _item(i):
    return {
        "id": f"itm{i:04d}",
        "title": ["ALPAKA 에어 슬링 크로스백", "ystudio 클래식 황동 볼펜", "PopSockets 그립톡 스탠드",
                  "ULANZI 미니 삼각대 확장 키트", "하베스트라벨 캔버스 토트"][i % 5],
        "url": f"https://www.amazon.com/dp/B0TEST{i:04d}",
        "domain": ["amazon.com", "rakuten.co.jp", "temu.com"][i % 3],
        "price": ["38,900", "126,000", "19,500"][i % 3],
        "currency": "KRW",
        "source": ["extension", "bookmarklet", "manual"][i % 3],
        "collected_at": "2026-09-03T09:2%d:00" % (i % 6),
        "status": "ok",
        "images": [""],
        "image": "",
        "uploaded_markets": ["쿠팡"] if i % 4 == 0 else [],   # 뷰가 주는 형태 = 문자열 리스트
        "extra": {},
    }


def _ctx(n):
    items = [_item(i) for i in range(n)]
    return {
        "page": "collect",
        "items": items,
        "summary": {"total": 396 if n else 0, "today": 12 if n else 0,
                    "domains": 7 if n else 0,
                    "by_source": {"extension": 240 if n else 0, "bookmarklet": 61 if n else 0,
                                  "manual": 48 if n else 0, "bulk": 47 if n else 0}},
        "filters": {"q": "", "domain": "", "source": "", "status": "", "group": "",
                    "sort": "newest", "days": 30, "per_page": 50},
        "domains": ["amazon.com", "rakuten.co.jp", "temu.com"],
        "groups": [],
        "pagination": {"total": 396 if n else 0, "page": 1, "pages": 8 if n else 1},
        "has_more": bool(n),
        "fastscroll": False,
        "hygiene_mode": False,
        "translation_free": {"remaining": 14, "limit": 20},
        "upload_markets": [{"market": "coupang", "label": "쿠팡", "pending": False}],
        "expected_ext_version": "1.5.35",
        "category_options": [],
    }


def _render(path, ctx):
    from flask import render_template

    from src.order_webhook import app
    app.jinja_env.cache.clear()
    with app.test_request_context("/seller/collect/history"):
        html = render_template("collect_history.html", **ctx)
    inline = ""
    if os.path.exists(BOOTSTRAP):
        inline += "<style>" + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    inline += "<style>" + open("src/static/app.css", encoding="utf-8").read() + "</style>"
    for extra in EXTRA_CSS:
        if os.path.exists(extra):
            inline += "<style>" + open(extra, encoding="utf-8").read() + "</style>"
    open(path, "w", encoding="utf-8").write(html.replace("</head>", inline + "</head>", 1))


def main():
    from playwright.sync_api import sync_playwright

    os.makedirs(OUT_DIR, exist_ok=True)
    shots = [("0데이터", _ctx(0), DESKTOP), ("실데이터", _ctx(24), DESKTOP), ("390", _ctx(24), MOBILE)]
    print("=== Stage 6-c 실측 (AFTER 단독 · 원본 해상도) ===")
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        for label, ctx, size in shots:
            path = f"/tmp/_s6c_{label}.html"
            _render(path, ctx)
            pg = br.new_page(viewport={"width": size[0], "height": size[1]})
            pg.goto(f"file://{path}")
            pg.wait_for_timeout(800)
            a = pg.evaluate(AUDIT)
            pg.screenshot(path=f"{OUT_DIR}/collect-history-{label}.png")     # 원본 해상도 · 축소 0
            pg.close()
            print(f"  {label} {a['vw']}×{a['vh']}: 높이 {a['pageHeight']} · 가로 스크롤 "
                  f"{'있음 ✗' if a['bodyScrollX'] else '없음 ✓'} · 격자 {a['cols']}열 · 카드 {a['cards']}")
            print(f"      <style> {a['styleTags']} · 인라인 하드코딩 {a['inlineHardcoded']} · "
                  f"44px 미만 {a['smallTargets']} · 타일 {a['tiles']} · 표 {a['rows']}행"
                  f"{' · 빈 상태 O' if a['empty'] else ''} · 툴바=푸터 {a['toolbarInFoot']}")
        br.close()
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
