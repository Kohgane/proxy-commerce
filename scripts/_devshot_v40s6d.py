"""개발용 스크린샷 — 디자인 v3 Stage 6-d: 마켓 3종(현황·연결·발급 가이드).

**캡처 계약(오너):** 0데이터 / 실데이터 / 390px 3벌, **원본 해상도 단독**(축소 병치 금지).
연결 화면은 드로어가 이 슬라이스의 Glass 표면이라 **열린 상태**로도 찍는다.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
OUT_DIR = "docs/screens/v40s6d"
DESKTOP = (1920, 940)
MOBILE = (390, 844)

AUDIT = """() => {
  const vw = innerWidth, vh = innerHeight;
  const inline = [...document.querySelectorAll('[style]')]
    .filter(e => /#[0-9a-fA-F]{3,8}|rgba?\\(|\\d+px/.test(e.getAttribute('style') || '')).length;
  const small = [...document.querySelectorAll('.mk-page a.btn, .mk-page button, .mk-page select, .mc-nav-item')]
    .filter(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.height < 44; }).length;
  // 화면당 강조(채운 primary) 개수 — v3 규율은 1개다(목록 반복 항목은 제외).
  const primary = [...document.querySelectorAll('.btn-primary, .btn-cta')]
    .filter(e => e.getBoundingClientRect().height > 0).length;
  const swatch = e => e ? getComputedStyle(e, '::after').backgroundColor : '';
  return {
    vw, vh,
    pageHeight: document.documentElement.scrollHeight,
    bodyScrollX: document.documentElement.scrollWidth > vw + 1,
    styleTags: document.querySelectorAll('style:not([data-devshot])').length,
    inlineHardcoded: inline,
    smallTargets: small,
    cards: document.querySelectorAll('.op-card').length,
    tiles: document.querySelectorAll('.mk-tile').length,
    tileCols: (() => { const g = document.querySelector('.mk-grid');
      return g ? getComputedStyle(g).gridTemplateColumns.split(' ').length : 0; })(),
    pendingDot: swatch(document.querySelector('.mk-tile[data-market-state="pending"]')),
    connectedDot: swatch(document.querySelector('.mk-tile[data-market-state="connected"]')),
    primaryButtons: primary,
    navCols: (() => { const w = document.querySelector('.mc-wrap');
      return w ? getComputedStyle(w).gridTemplateColumns : ''; })(),
    drawerOpen: !!document.querySelector('.mc-drawer.open'),
    svgHardcoded: [...document.querySelectorAll('svg [fill], svg [stroke]')]
      .filter(e => /^#/.test(e.getAttribute('fill') || e.getAttribute('stroke') || '')).length,
  };
}"""


def _hub(mp, label, country, cur, supported=True, active=0, total=0):
    return {"marketplace": mp, "label": label, "country": country, "currency": cur,
            "integration_supported": supported, "status_style": "secondary",
            "status_label": "연동 준비 중", "active": active, "total": total,
            "note": "", "last_synced_at": "2026-09-05 08:40" if total else None,
            "required_scopes": ["상품 등록", "주문 조회"],
            "required_env": [f"{mp.upper()}_ACCESS_KEY", f"{mp.upper()}_SECRET_KEY"],
            "check_locations": ["판매자센터 > API 관리"], "docs_path": f"docs/{mp}.md"}


def _row(i):
    st = ["active", "active", "out_of_stock", "error", "price_anomaly"][i % 5]
    return {"marketplace": ["coupang", "smartstore", "elevenst"][i % 3],
            "marketplace_label": ["쿠팡", "스마트스토어", "11번가"][i % 3],
            "product_id": f"163692{i:05d}", "sku": f"KGP-{i:04d}",
            "title": ["ALPAKA 에어 슬링 크로스백", "ystudio 클래식 황동 볼펜",
                      "PopSockets 그립톡 스탠드", "ULANZI 미니 삼각대 확장 키트"][i % 4],
            "state": st, "error_message": "카테고리 속성 누락" if st == "error" else "",
            "price_display": ["38,900원", "126,000원", "19,500원"][i % 3], "price_note": "",
            "country": "KR", "currency": "KRW", "region": "국내", "is_ready": i % 7 != 0,
            "last_synced_at": "2026-09-05 08:40"}


def _markets_ctx(n):
    hubs = [_hub("coupang", "쿠팡", "KR", "KRW", True, 182 if n else 0, 214 if n else 0),
            _hub("smartstore", "스마트스토어", "KR", "KRW", True, 96 if n else 0, 121 if n else 0),
            _hub("elevenst", "11번가", "KR", "KRW", True, 0, 0),
            _hub("shopee", "쇼피", "SG", "SGD", False)]
    mkts = [{"marketplace": "coupang", "label": "쿠팡", "country": "KR", "currency": "KRW",
             "region": "국내", "is_ready": True, "active": 182, "out_of_stock": 9,
             "error": 3, "total": 214, "source": "catalog"},
            {"marketplace": "smartstore", "label": "스마트스토어", "country": "KR",
             "currency": "KRW", "region": "국내", "is_ready": True, "active": 96,
             "out_of_stock": 2, "error": 0, "total": 121, "source": "catalog"},
            {"marketplace": "elevenst", "label": "11번가", "country": "KR", "currency": "KRW",
             "region": "국내", "is_ready": False, "active": 0, "out_of_stock": 0,
             "error": 0, "total": 0, "source": "catalog"}]
    return {"page": "markets",
            "market_data": {"is_mock": not n, "source": "catalog", "markets": mkts if n else [],
                            "fetched_at": "2026-09-05T08:40:00"},
            "market_hub_cards": hubs,
            "items": [_row(i) for i in range(n)],
            "marketplace_filters": [{"marketplace": m["marketplace"], "label": m["label"],
                                     "is_ready": m["is_ready"]} for m in mkts],
            "country_filters": ["KR"]}


def _render(path, template, ctx, route, open_drawer=False):
    from flask import render_template

    from src.order_webhook import app
    app.jinja_env.cache.clear()
    with app.test_request_context(route):
        html = render_template(template, **ctx)
    if template == "markets_connect.html":
        # 런타임 mcSelect()가 하는 일을 정적으로 재현 — 안 하면 우 상세가 통째로 빈다.
        html = html.replace('class="mc-nav-item mc-market-nav"',
                            'class="mc-nav-item mc-market-nav active"', 1)
        html = html.replace('class="mc-panel mc-market-col"',
                            'class="mc-panel mc-market-col active"', 1)
    if open_drawer:                     # 드로어 = 이 화면의 Glass 표면. 열린 상태를 찍는다.
        html = html.replace('class="mc-drawer"', 'class="mc-drawer open"')
        html = html.replace('class="mc-drawer-overlay"', 'class="mc-drawer-overlay open"')
        html = html.replace(
            '<form class="market-connect-form mc-drawer-form" data-market="coupang" '
            'autocomplete="off" style="display:none;">',
            '<form class="market-connect-form mc-drawer-form" data-market="coupang" '
            'autocomplete="off" data-shot="1">', 1)
    inline = ""
    if os.path.exists(BOOTSTRAP):
        inline += '<style data-devshot>' + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    inline += '<style data-devshot>' + open("src/static/app.css", encoding="utf-8").read() + "</style>"
    for extra in EXTRA_CSS:
        if os.path.exists(extra):
            inline += '<style data-devshot>' + open(extra, encoding="utf-8").read() + "</style>"
    if open_drawer:                     # 첫 폼만 보이게(런타임 JS가 하는 일을 정적으로 재현)
        inline += '<style data-devshot>.mc-drawer-form{display:none}.mc-drawer-form[data-shot]{display:block}</style>'
    open(path, "w", encoding="utf-8").write(html.replace("</head>", inline + "</head>", 1))


def _connect_ctx():
    from src.seller_console.views import _connect_ip_ctx
    from src.seller_console.market_guide import guide_map
    from src.seller_console.market_credentials import MARKET_CRED_FIELDS

    def _fields(mkt, filled):
        out = []
        for f in MARKET_CRED_FIELDS.get(mkt, [])[:8]:
            has = filled and not f.get("section")
            out.append({"label": f.get("label", f["env"]), "env": f["env"],
                        "secret": bool(f.get("secret")), "required": bool(f.get("required")),
                        "section": f.get("section", ""), "help": f.get("help", ""),
                        "has_value": has, "from_global": False,
                        "display": "••••1f4a" if has else ""})
        return out

    statuses = [
        {"market": "coupang", "label": "쿠팡", "connected": True,
         "has_seller_credentials": True, "fields": _fields("coupang", True)},
        {"market": "smartstore", "label": "스마트스토어", "connected": True,
         "has_seller_credentials": True, "fields": _fields("smartstore", True)},
        {"market": "elevenst", "label": "11번가", "connected": False,
         "has_seller_credentials": False, "fields": _fields("elevenst", False)},
        {"market": "woocommerce", "label": "우커머스", "connected": False,
         "has_seller_credentials": False, "fields": _fields("woocommerce", False)},
    ]
    ctx = {"page": "markets", "market_statuses": statuses, "single_market": False,
           "guide_map": guide_map()}
    ctx.update(_connect_ip_ctx())
    return ctx


def _guide_ctx():
    from src.seller_console.views import _connect_ip_ctx
    from src.seller_console.market_guide import get_guide
    ctx = {"page": "markets", "guide": get_guide()}
    ctx.update(_connect_ip_ctx())
    return ctx


def main():
    from playwright.sync_api import sync_playwright

    os.makedirs(OUT_DIR, exist_ok=True)
    shots = [
        ("markets-0데이터", "markets.html", _markets_ctx(0), "/seller/markets", DESKTOP, False),
        ("markets-실데이터", "markets.html", _markets_ctx(18), "/seller/markets", DESKTOP, False),
        ("markets-390", "markets.html", _markets_ctx(18), "/seller/markets", MOBILE, False),
        ("connect-실데이터", "markets_connect.html", _connect_ctx(), "/seller/markets/connect", DESKTOP, False),
        ("connect-드로어", "markets_connect.html", _connect_ctx(), "/seller/markets/connect", DESKTOP, True),
        ("connect-390", "markets_connect.html", _connect_ctx(), "/seller/markets/connect", MOBILE, False),
        ("guide-실데이터", "markets_guide.html", _guide_ctx(), "/seller/markets/guide", DESKTOP, False),
        ("guide-390", "markets_guide.html", _guide_ctx(), "/seller/markets/guide", MOBILE, False),
    ]
    print("=== Stage 6-d 실측 (AFTER 단독 · 원본 해상도) ===")
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        for label, tpl, ctx, route, size, drawer in shots:
            path = f"/tmp/_s6d_{label}.html"
            _render(path, tpl, ctx, route, drawer)
            pg = br.new_page(viewport={"width": size[0], "height": size[1]})
            pg.goto(f"file://{path}")
            pg.wait_for_timeout(700)
            a = pg.evaluate(AUDIT)
            pg.screenshot(path=f"{OUT_DIR}/{label}.png")       # 원본 해상도 · 축소 0
            pg.close()
            print(f"  {label} {a['vw']}×{a['vh']}: 높이 {a['pageHeight']} · 가로 스크롤 "
                  f"{'있음 ✗' if a['bodyScrollX'] else '없음 ✓'} · 카드 {a['cards']} · 타일 "
                  f"{a['tiles']}({a['tileCols']}열)")
            print(f"      style태그 {a['styleTags']} · 인라인 하드코딩 {a['inlineHardcoded']} · "
                  f"SVG hex {a['svgHardcoded']} · 44px 미만 {a['smallTargets']} · "
                  f"강조버튼 {a['primaryButtons']}"
                  + (f" · 드로어 열림 {a['drawerOpen']}" if drawer else "")
                  + (f" · 신호점 대기={a['pendingDot']} 연결={a['connectedDot']}" if a['tiles'] else ""))
        br.close()
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
