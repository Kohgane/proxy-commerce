"""개발용 스크린샷 — 디자인 v3 Stage 6-e: 주문 관리.

**캡처 계약(오너):** 0데이터 / 실데이터 / 390px 3벌, **원본 해상도 단독**(축소 병치 금지).
여기에 하나 더: **503(서비스 미가용)** — 이 화면은 그때 조판이 달라진다(경보 줄이 뜬다).
"""
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
OUT_DIR = "docs/screens/v40s6e"
DESKTOP = (1920, 940)
MOBILE = (390, 844)

AUDIT = """() => {
  const vw = innerWidth;
  const inline = [...document.querySelectorAll('[style]')]
    .filter(e => /#[0-9a-fA-F]{3,8}|rgba?\\(/.test(e.getAttribute('style') || '')).length;
  // 44px 규율은 **카드 밖·헤더** 조작 요소에만 — 표 안 행 액션은 밀도가 기능이다.
  const chrome = [...document.querySelectorAll(
      '.od-page .op-card-head .btn, .od-page .op-card-foot .btn, .od-filter .form-select, .od-filter .form-control')]
    .filter(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.height < 44; }).length;
  const dot = s => { const e = document.querySelector(s);
    return e ? getComputedStyle(e, '::after').backgroundColor + '/' + getComputedStyle(e, '::after').display : '—'; };
  return {
    vw, vh: innerHeight,
    pageHeight: document.documentElement.scrollHeight,
    bodyScrollX: document.documentElement.scrollWidth > vw + 1,
    styleTags: document.querySelectorAll('style:not([data-devshot])').length,
    inlineHardcoded: inline,
    smallChrome: chrome,
    cards: document.querySelectorAll('.op-card').length,
    stats: document.querySelectorAll('.od-stat').length,
    statCols: (() => { const g = document.querySelector('.od-stats');
      return g ? getComputedStyle(g).gridTemplateColumns.split(' ').length : 0; })(),
    newDot: dot('.od-stat.is-on'),
    alertDot: dot('.od-stat.is-alert'),
    footButtons: document.querySelectorAll('.op-card-foot .btn').length,
    healthStrip: !!document.querySelector('.pc-status-warning'),
    rows: document.querySelectorAll('tbody tr').length,
    primary: [...document.querySelectorAll('.btn-primary, .btn-cta')]
      .filter(e => e.getBoundingClientRect().height > 0).length,
  };
}"""


def _order(i):
    st = ["new", "paid", "preparing", "shipped", "delivered", "returned"][i % 6]
    mp = ["coupang", "smartstore", "11st"][i % 3]
    return {
        "marketplace": mp, "order_id": f"CP-{2600 + i}", "status": st,
        "placed_at": f"2026-09-0{i % 5 + 1}T09:2{i % 6}:00",
        "items": [{"title": ["ALPAKA 에어 슬링 크로스백", "ystudio 클래식 황동 볼펜",
                             "PopSockets 그립톡 스탠드", "ULANZI 미니 삼각대 확장 키트"][i % 4]}]
                 + ([{"title": "추가 구성품"}] if i % 4 == 0 else []),
        "total_krw": [38900, 126000, 19500][i % 3],
        "courier": "CJ대한통운" if st in ("shipped", "delivered") else "",
        "tracking_no": f"6{i:09d}" if st in ("shipped", "delivered") else "",
        "source_info": ({"linked": True, "source_url": "https://www.amazon.com/dp/B0TEST",
                         "copy_text": "주문정보", "sourced": i % 3 == 0} if i % 5 else None),
    }


def _ctx(n, healthy=True, returns=3):
    return {
        "page": "orders",
        "orders": [_order(i) for i in range(n)],
        "kpi": {"today_new": 12 if n else 0, "pending_ship": 5 if n else 0,
                "shipped": 31 if n else 0, "returned_exchanged": returns if n else 0},
        "filters": {}, "ops_health": {"service_available": healthy},
        "courier_catalog": [{"code": "cj", "name": "CJ대한통운"}],
    }


def _render(path, ctx):
    from flask import render_template

    from src.order_webhook import app
    app.jinja_env.cache.clear()
    with app.test_request_context("/seller/orders"):
        html = render_template("orders.html", **ctx)
    inline = ""
    if os.path.exists(BOOTSTRAP):
        inline += '<style data-devshot>' + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    inline += '<style data-devshot>' + open("src/static/app.css", encoding="utf-8").read() + "</style>"
    for extra in EXTRA_CSS:
        if os.path.exists(extra):
            inline += '<style data-devshot>' + open(extra, encoding="utf-8").read() + "</style>"
    open(path, "w", encoding="utf-8").write(html.replace("</head>", inline + "</head>", 1))


def main():
    from playwright.sync_api import sync_playwright

    os.makedirs(OUT_DIR, exist_ok=True)
    shots = [
        ("0데이터", _ctx(0), DESKTOP),
        ("실데이터", _ctx(14), DESKTOP),
        ("반품0", _ctx(14, returns=0), DESKTOP),      # 0이면 주황 점이 꺼지는지
        ("503", _ctx(14, healthy=False), DESKTOP),
        ("390", _ctx(14), MOBILE),
    ]
    print("=== Stage 6-e 실측 (AFTER 단독 · 원본 해상도) ===")
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        for label, ctx, size in shots:
            path = f"/tmp/_s6e_{label}.html"
            _render(path, ctx)
            pg = br.new_page(viewport={"width": size[0], "height": size[1]})
            pg.goto(f"file://{path}")
            pg.wait_for_timeout(700)
            a = pg.evaluate(AUDIT)
            pg.screenshot(path=f"{OUT_DIR}/orders-{label}.png")
            pg.close()
            print(f"  {label} {a['vw']}×{a['vh']}: 높이 {a['pageHeight']} · 가로 스크롤 "
                  f"{'있음 ✗' if a['bodyScrollX'] else '없음 ✓'} · 카드 {a['cards']} · "
                  f"수치 {a['stats']}({a['statCols']}열) · 표 {a['rows']}행")
            print(f"      style태그 {a['styleTags']} · 인라인 하드코딩 {a['inlineHardcoded']} · "
                  f"chrome 44px 미만 {a['smallChrome']} · 푸터 버튼 {a['footButtons']} · "
                  f"강조 {a['primary']} · 503줄 {a['healthStrip']}")
            print(f"      신호점 신규={a['newDot']} 반품={a['alertDot']}")
        br.close()
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
