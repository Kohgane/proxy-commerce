"""개발용 스크린샷 — 디자인 v3 Stage 6-f: 상품 수집(manual_collect).

**캡처 계약(오너):** 0데이터 / 실데이터 / 390px 3벌, **원본 해상도 단독**(축소 병치 금지).
여기에 하나 더: **미리보기 펼침** — 이 화면은 그때 카드 둘이 더 열린다(추출 결과·마켓 선택).
정적 렌더에는 JS가 없으니 `#previewCard`의 `d-none`을 벗겨 그 상태를 재현한다.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
OUT_DIR = "docs/screens/v40s6f"
DESKTOP = (1920, 940)
MOBILE = (390, 844)

AUDIT = """() => {
  const vw = innerWidth;
  const inline = [...document.querySelectorAll('[style]')]
    .filter(e => /#[0-9a-fA-F]{3,8}|rgba?\\(/.test(e.getAttribute('style') || '')).length;
  const small = [...document.querySelectorAll(
      '.mc-page .op-card-head .btn, .mc-page .op-card-foot .btn, .mc-page .mc-chip, .mc-page .form-control')]
    .filter(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.height < 44; }).length;
  // 화면당 강조 — 단계 CTA만 채운 버튼이어야 한다(칩은 이동 수단).
  const filled = [...document.querySelectorAll('.btn-primary, .btn-cta')]
    .filter(e => e.getBoundingClientRect().height > 0).map(e => (e.textContent || '').trim().slice(0, 12));
  return {
    vw, vh: innerHeight,
    pageHeight: document.documentElement.scrollHeight,
    bodyScrollX: document.documentElement.scrollWidth > vw + 1,
    styleTags: document.querySelectorAll('style:not([data-devshot])').length,
    inlineHardcoded: inline,
    smallTargets: small,
    cards: document.querySelectorAll('.op-card').length,
    chips: document.querySelectorAll('.mc-chip').length,
    marketCols: (() => { const g = document.querySelector('.mc-markets');
      return g ? getComputedStyle(g).gridTemplateColumns.split(' ').length : 0; })(),
    disabledTile: (() => { const e = document.querySelector('.mc-market:has(input:disabled)');
      return e ? getComputedStyle(e).cursor : '—'; })(),
    filled,
    v2cards: document.querySelectorAll('.console-card, .console-step-card').length,
    oldToast: !!document.getElementById('uploadToast'),
  };
}"""


def _ctx(ready: bool):
    """`ready=False`면 아직 아무 마켓도 연동 안 된 계정(0데이터에 해당)."""
    markets = [
        {"code": "coupang", "label": "쿠팡", "country": "KR", "currency": "KRW", "is_ready": ready},
        {"code": "smartstore", "label": "스마트스토어", "country": "KR", "currency": "KRW", "is_ready": ready},
        {"code": "elevenst", "label": "11번가", "country": "KR", "currency": "KRW", "is_ready": False},
        {"code": "woocommerce", "label": "우커머스", "country": "KR", "currency": "KRW", "is_ready": ready},
    ]
    oneclick = [
        {"name": "타오바오", "url": "https://world.taobao.com", "domain": "taobao.com"},
        {"name": "티몰", "url": "https://www.tmall.com", "domain": "tmall.com"},
        {"name": "1688", "url": "https://www.1688.com", "domain": "1688.com"},
        {"name": "테무", "url": "https://www.temu.com", "domain": "temu.com"},
        {"name": "알리익스프레스", "url": "https://ko.aliexpress.com", "domain": "aliexpress.com"},
        {"name": "아마존", "domain": "amazon.com", "countries": [
            {"name": "미국", "url": "https://www.amazon.com", "currency": "USD"},
            {"name": "일본", "url": "https://www.amazon.co.jp", "currency": "JPY"},
            {"name": "독일", "url": "https://www.amazon.de", "currency": "EUR"}]},
    ]
    return {
        "page": "collect",
        "oneclick_markets": oneclick,
        "my_sources": ([{"name": "요시다카반", "url": "https://www.yoshidakaban.com",
                         "domain": "yoshidakaban.com"}] if ready else []),
        "marketplace_cards": markets,
        "locale_options": ["ko-KR", "en-US", "ja-JP", "zh-CN"],
        "localization_configured": ready,
        "api_status": [{"status": "active" if ready else "inactive"}],
        "_user_role": "seller",
    }


def _render(path, ctx, *, preview: bool):
    from flask import render_template

    from src.order_webhook import app
    app.jinja_env.cache.clear()
    with app.test_request_context("/seller/collect"):
        html = render_template("manual_collect.html", **ctx)
    if preview:
        # 런타임에 extractProduct()가 벗기는 것을 정적으로 재현 — 안 하면 카드 둘이 안 보인다.
        html = html.replace('<div id="previewCard" class="d-none">', '<div id="previewCard">')
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
        ("0데이터", _ctx(False), DESKTOP, False),
        ("실데이터", _ctx(True), DESKTOP, False),
        ("미리보기", _ctx(True), DESKTOP, True),
        ("390", _ctx(True), MOBILE, False),
    ]
    print("=== Stage 6-f 실측 (AFTER 단독 · 원본 해상도) ===")
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        for label, ctx, size, preview in shots:
            path = f"/tmp/_s6f_{label}.html"
            _render(path, ctx, preview=preview)
            pg = br.new_page(viewport={"width": size[0], "height": size[1]})
            pg.goto(f"file://{path}")
            pg.wait_for_timeout(700)
            a = pg.evaluate(AUDIT)
            pg.screenshot(path=f"{OUT_DIR}/collect-{label}.png")     # 원본 해상도 · 축소 0
            pg.close()
            print(f"  {label} {a['vw']}×{a['vh']}: 높이 {a['pageHeight']} · 가로 스크롤 "
                  f"{'있음 ✗' if a['bodyScrollX'] else '없음 ✓'} · 카드 {a['cards']} · "
                  f"칩 {a['chips']} · 마켓 {a['marketCols']}열")
            print(f"      style태그 {a['styleTags']} · 인라인 하드코딩 {a['inlineHardcoded']} · "
                  f"44px 미만 {a['smallTargets']} · v2카드 {a['v2cards']} · 옛토스트 {a['oldToast']} · "
                  f"미연동 커서 {a['disabledTile']}")
            print(f"      채운 버튼 {len(a['filled'])}: {a['filled']}")
        br.close()
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
