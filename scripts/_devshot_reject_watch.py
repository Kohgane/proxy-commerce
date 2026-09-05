"""개발용 스크린샷 — 반려 감시 대상 목록(읽기 전용).

3벌: 실데이터 / 0건 / 대장 못 읽음. **0건과 '못 읽음'이 화면에서 갈리는지**가 요점이다.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
OUT_DIR = "docs/screens/reject-watch"
SIZE = (1920, 940)

ROWS = [
    {"sid": "16369251981", "title": "ALPAKA 에어 슬링 크로스백", "account": "gogane",
     "market_url": "https://www.coupang.com/vp/products/1"},
    {"sid": "16369251982", "title": "ystudio 클래식 황동 볼펜", "account": "gogane",
     "market_url": "https://www.coupang.com/vp/products/2"},
    {"sid": "16369251983", "title": "", "account": "gogane", "market_url": ""},
]


def _html(queue_result):
    from src.order_webhook import app
    app.jinja_env.cache.clear()
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"
        with patch("src.db.market_registrations_pg.watch_queue", **queue_result):
            page = c.get("/seller/sourcing/reject-watch").get_data(as_text=True)
    inline = ""
    if os.path.exists(BOOTSTRAP):
        inline += "<style>" + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    inline += "<style>" + open("src/static/app.css", encoding="utf-8").read() + "</style>"
    for extra in EXTRA_CSS:
        if os.path.exists(extra):
            inline += "<style>" + open(extra, encoding="utf-8").read() + "</style>"
    return page.replace("</head>", inline + "</head>", 1)


def main():
    from playwright.sync_api import sync_playwright

    os.makedirs(OUT_DIR, exist_ok=True)
    shots = [
        ("실데이터", {"return_value": ROWS}),
        ("0건", {"return_value": []}),
        ("못읽음", {"side_effect": RuntimeError("boom")}),
    ]
    print("=== 반려 감시 목록 실측 ===")
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        for label, kw in shots:
            path = f"/tmp/_rw_{label}.html"
            open(path, "w", encoding="utf-8").write(_html(kw))
            pg = br.new_page(viewport={"width": SIZE[0], "height": SIZE[1]})
            pg.goto(f"file://{path}")
            pg.wait_for_timeout(600)
            a = pg.evaluate("""() => ({
              rows: document.querySelectorAll('.op-card-body tbody tr').length,
              empty: !!document.querySelector('.op-empty'),
              off: !!document.querySelector('.op-off'),
              textarea: (document.getElementById('sids') || {}).value || '',
              bodyScrollX: document.documentElement.scrollWidth > innerWidth + 1,
            })""")
            pg.screenshot(path=f"{OUT_DIR}/reject-watch-{label}.png")
            pg.close()
            print(f"  {label}: 행 {a['rows']} · 빈상태 {a['empty']} · 미연결표기 {a['off']} · "
                  f"textarea 실값 {a['textarea']!r} · 가로 스크롤 "
                  f"{'있음' if a['bodyScrollX'] else '없음 ✓'}")
        br.close()
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
