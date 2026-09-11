"""개발용 스크린샷 — 디자인 v3 Stage 6-l: 꼬리 화면 일괄(cs* · pricing*).

꼬리는 화면 수가 많아 화면마다 컨텍스트를 손으로 꾸미지 않는다 — **실제 라우트를 태워** 받은
HTML에 CSS를 인라인해 찍는다(빈 상태가 기본값인 화면이 대부분이라 그게 실제 첫인상이기도 하다).

계측은 두 갈래다.
* **기계**: 가로 스크롤·인라인 하드코딩·44px 미만·v2 잔재·집 없는 클래스.
* **눈**: 6-l ①에서 배운 것 — 뚜렷한 차이 0.86%가 "미세" 등급인데 화면은 깨져 있었다.
  그래서 군마다 최소 한 장은 사람이 본다. 이 스크립트는 그 재료만 만든다.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
OUT_DIR = "docs/screens/v40s6l"
DESKTOP = (1920, 940)

ROUTES = [
    ("seller-cs-inbox", "/seller/cs/inbox"),
    ("seller-cs-stats", "/seller/cs/stats"),
    ("seller-cs-faq", "/seller/cs/faq"),
    ("seller-cs-sla", "/seller/cs/sla"),
    ("seller-cs-quality", "/seller/cs/quality"),
    ("seller-cs-mobile", "/seller/cs/mobile"),
    ("seller-pricing", "/seller/pricing"),
    ("seller-pricing-rules", "/seller/pricing/rules"),
    ("seller-pricing-competitors", "/seller/pricing/competitors"),
    ("seller-pricing-history", "/seller/pricing/history"),
    ("seller-pricing-fx-impact", "/seller/pricing/fx-impact"),
    # 3군(guide+기타) — `/collect/preview/<id>`·`/collect/receiver`처럼 인자·POST가 필요한 건 제외.
    ("seller-about", "/seller/about"),
    ("seller-analytics", "/seller/analytics"),
    ("seller-api-status", "/seller/api-status"),
    ("seller-billing", "/seller/billing"),
    ("seller-bookmarklet", "/seller/bookmarklet"),
    ("seller-collect-history", "/seller/collect/history"),
    ("seller-discovery", "/seller/discovery"),
    ("seller-discovery-keywords", "/seller/discovery/keywords"),
    ("seller-extension", "/seller/extension"),
    ("seller-guide-business", "/seller/guide/business"),
    ("seller-guide-sources", "/seller/guide/sources"),
    ("seller-keywords", "/seller/keywords"),
    ("seller-me", "/seller/me"),
    ("seller-messaging", "/seller/messaging"),
    ("seller-notifications", "/seller/notifications"),
    ("seller-orders", "/seller/orders"),
    ("seller-pccc", "/seller/customs/pccc"),
    ("seller-tokens", "/seller/me/tokens"),
    ("seller-settlement", "/seller/settlement"),
    ("seller-sourcing-monitor", "/seller/sourcing/monitor"),
    ("seller-word-rules", "/seller/listing/word-rules"),
]

AUDIT = """() => {
  const vw = innerWidth;
  const inline = [...document.querySelectorAll('[style]')]
    .filter(e => /#[0-9a-fA-F]{3,8}|rgba?\\(|\\d+px/.test(e.getAttribute('style') || '')).length;
  const small = [...document.querySelectorAll('main .btn, main .form-control, main .form-select')]
    .filter(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.height < 44; }).length;
  const filled = [...document.querySelectorAll('.btn-primary, .btn-cta')]
    .filter(e => e.getBoundingClientRect().height > 0).map(e => (e.textContent || '').trim().slice(0, 10));
  // 경계를 잃은 고스트 — 6-l에서 머리 액션 줄이 글자 무더기로 읽힌 그 증상.
  const borderless = [...document.querySelectorAll('.btn-ghost')]
    .filter(e => e.getBoundingClientRect().height > 0 &&
                 getComputedStyle(e).borderTopWidth === '0px').length;
  return {
    vw, vh: innerHeight,
    pageHeight: Math.max(document.documentElement.scrollHeight,
                         ...[...document.querySelectorAll('main')].map(m => m.getBoundingClientRect().bottom)),
    bodyScrollX: document.documentElement.scrollWidth > vw + 1,
    inlineHardcoded: inline,
    smallTargets: small,
    cards: document.querySelectorAll('.op-card').length,
    v2: document.querySelectorAll(
      '[class*="btn-outline-"], [class*="text-bg-"], .badge.bg-primary, .badge.bg-secondary, ' +
      '.badge.bg-info, .badge.bg-success, .badge.bg-warning, .badge.bg-danger, .bg-light').length,
    ghostBorderless: borderless,
    filled,
  };
}"""


def _page_html(client, url: str) -> str:
    res = client.get(url, follow_redirects=True)
    html = res.get_data(as_text=True)
    inline = ""
    if os.path.exists(BOOTSTRAP):
        inline += '<style data-devshot>' + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    inline += '<style data-devshot>' + open("src/static/app.css", encoding="utf-8").read() + "</style>"
    for extra in EXTRA_CSS:
        if os.path.exists(extra):
            inline += '<style data-devshot>' + open(extra, encoding="utf-8").read() + "</style>"
    return html.replace("</head>", inline + "</head>", 1), res.status_code


def main():
    from playwright.sync_api import sync_playwright

    from src.order_webhook import app
    app.jinja_env.cache.clear()

    suffix = sys.argv[1] if len(sys.argv) > 1 else "after"
    only = sys.argv[2] if len(sys.argv) > 2 else ""
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = [r for r in ROUTES if not only or r[0].startswith(only)]

    print(f"=== Stage 6-l 실측 ({suffix}) ===")
    with app.test_client() as client:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            for name, url in rows:
                html, code = _page_html(client, url)
                path = f"/tmp/_s6l_{name}.html"
                open(path, "w", encoding="utf-8").write(html)
                pg = br.new_page(viewport={"width": DESKTOP[0], "height": DESKTOP[1]})
                pg.goto(f"file://{path}")
                pg.wait_for_timeout(500)
                a = pg.evaluate(AUDIT)
                # **전체 페이지**로 찍는다. 뷰포트(1920×940)만 찍으면 접힌 아래가 대조에서 통째로 빠진다 —
                # 실측: 32장 중 13장이 940보다 길어(북마클릿 1980) 화면 대부분이 안 재어지고 있었다.
                # 합격 좌표계는 여전히 1920 폭이고, 세로는 내용이 정한다.
                pg.screenshot(path=f"{OUT_DIR}/{name}-{suffix}.png", full_page=True)
                pg.close()
                print(f"  {name:30s} HTTP {code} · 높이 {int(a['pageHeight']):5d} · 가로스크롤 "
                      f"{'있음 ✗' if a['bodyScrollX'] else '없음 ✓'} · 카드 {a['cards']:2d} · v2 {a['v2']:2d} · "
                      f"인라인 {a['inlineHardcoded']:2d} · 44px미만 {a['smallTargets']:2d} · "
                      f"선없는고스트 {a['ghostBorderless']:2d} · 채운버튼 {a['filled']}")
            br.close()
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
