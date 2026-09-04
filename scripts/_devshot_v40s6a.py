"""개발용 스크린샷 — 디자인 v3 Stage 6-a: 운영 대시보드.

**합격 기준(오너 G1·G4):** 1920×940 body 스크롤바 0 · 390px 1열 폴백 ·
카드 밖 공동 0. 캡처 3벌 — **0데이터 / 실데이터 / 390px**.

0데이터 = 전 블록 미연결(정직 표기가 실제로 나오는지). 실데이터 = 계정·대장·큐가 찬 상태.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

TPL = "src/seller_console/templates/dashboard.html"
CSS = "src/static/app.css"
VIEWS = "src/seller_console/views.py"
SNAP = "src/pipeline/ops_snapshot.py"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
OUT_DIR = "docs/screens/v40s6a"
DESKTOP = (1920, 940)
MOBILE = (390, 844)

AUDIT = """() => {
  const px = v => Math.round(v);
  const vw = innerWidth, vh = innerHeight;
  const shell = document.querySelector('.op-shell');
  const sr = shell ? shell.getBoundingClientRect() : null;
  // 공동 = 셸 안에서 카드가 못 채운 아래 여백(가장 아래 카드 기준).
  const cards = [...document.querySelectorAll('.op-card')];
  const lowest = cards.reduce((a, c) =>
    (!a || c.getBoundingClientRect().bottom > a.getBoundingClientRect().bottom) ? c : a, null);
  const scrollers = [...document.querySelectorAll('.op-shell *')].filter(e => {
    const cs = getComputedStyle(e);
    return /auto|scroll/.test(cs.overflowY) && e.scrollHeight > e.clientHeight + 1;
  }).map(e => (e.className || '').toString().split(/\\s+/)[0]);
  const small = [...document.querySelectorAll('.op-shell a.btn, .op-shell button, .op-shell select')]
    .filter(e => { const r = e.getBoundingClientRect(); return r.height > 0 && r.height < 44; }).length;
  return {
    vw, vh,
    pageHeight: document.documentElement.scrollHeight,
    bodyScrollY: document.documentElement.scrollHeight > vh + 1,
    bodyScrollX: document.documentElement.scrollWidth > vw + 1,
    hollow: (sr && lowest) ? px(sr.bottom - lowest.getBoundingClientRect().bottom) : null,
    cards: cards.length,
    cols: shell ? getComputedStyle(shell).gridTemplateColumns.split(' ').length : 0,
    scrollers, smallTargets: small,
    offline: document.querySelectorAll('.op-off').length,
    tiles: document.querySelectorAll('.op-tile').length,
    signal: [...document.querySelectorAll('.op-sig-item')].map(e =>
      (e.dataset.market || '') + ':' + (e.className.match(/is-\w+/) || ['자격설정됨'])[0]),
  };
}"""

EMPTY = {
    "accounts": [{"account": a, "label": a, "vendor_id": "", "connected": False,
                  "note": "API 자격 미설정", "market": m, "market_ko": ko}
                 for m, ko, accs in (("coupang", "쿠팡", ("gogane", "woojoo")),
                                     ("smartstore", "스마트스토어", ("chezgoga", "gocosmos")))
                 for a in accs],
    "registrations": {"connected": False, "note": "등록 대장 미연결(DATABASE_URL 미설정)", "counts": {}},
    "rejections": {"connected": False, "note": "등록 대장 미연결", "rows": []},
    "sourcing": {"connected": False, "note": "수집 이력 조회 실패", "today": 0, "total": 0},
    "markets": {"connected": True, "note": "", "rows": [
        {"market": m, "label": ko, "configured": False, "source": ""}
        for m, ko in (("coupang", "쿠팡"), ("smartstore", "스마트스토어"), ("elevenst", "11번가"),
                      ("woocommerce", "우커머스"), ("shopify", "쇼피파이"))]},
}

LIVE = {
    "accounts": [
        {"account": "gogane", "label": "고가네", "vendor_id": "A01381223", "connected": True,
         "note": "", "market": "coupang", "market_ko": "쿠팡"},
        {"account": "woojoo", "label": "우주대행", "vendor_id": "A01504840", "connected": True,
         "note": "", "market": "coupang", "market_ko": "쿠팡"},
        {"account": "chezgoga", "label": "chezgoga", "vendor_id": "", "connected": True,
         "note": "", "market": "smartstore", "market_ko": "스마트스토어"},
        {"account": "gocosmos", "label": "gocosmos", "vendor_id": "", "connected": False,
         "note": "API 자격 미설정", "market": "smartstore", "market_ko": "스마트스토어"},
    ],
    "registrations": {"connected": True, "note": "",
                      "counts": {"registered": 47, "rejected": 3, "held": 1, "failed": 2}},
    "rejections": {"connected": True, "note": "", "rows": [
        {"product_id": "16359486080", "title": "PopSockets 그립톡 스탠드 블랙", "account": "gogane"},
        {"product_id": "16359486081", "title": "ystudio 클래식 황동 볼펜", "account": "woojoo"},
        {"product_id": "16359486082", "title": "ALPAKA 에어 슬링 크로스백", "account": "gogane"},
        {"product_id": "16359486083", "title": "ULANZI 미니 삼각대 확장 키트", "account": "gogane"},
        {"product_id": "16359486084", "title": "하베스트라벨 캔버스 토트", "account": "woojoo"},
    ]},
    "sourcing": {"connected": True, "note": "", "today": 12, "total": 396},
    "markets": {"connected": True, "note": "", "rows": [
        {"market": "coupang", "label": "쿠팡", "configured": True, "source": "server"},
        {"market": "smartstore", "label": "스마트스토어", "configured": True, "source": "server"},
        {"market": "elevenst", "label": "11번가", "configured": True, "source": "seller"},
        {"market": "woocommerce", "label": "우커머스", "configured": True, "source": "seller"},
        {"market": "shopify", "label": "쇼피파이", "configured": False, "source": ""},
    ]},
}


def _render(html_path, app_css, ops):
    from flask import render_template

    from src.order_webhook import app
    app.jinja_env.cache.clear()
    with app.test_request_context("/seller/dashboard"):
        html = render_template("dashboard.html", page="dashboard", ops=ops, widgets=[])
    inline = ""
    if os.path.exists(BOOTSTRAP):
        inline += "<style>" + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    inline += "<style>" + app_css + "</style>"
    for extra in EXTRA_CSS:
        if os.path.exists(extra):
            inline += "<style>" + open(extra, encoding="utf-8").read() + "</style>"
    open(html_path, "w", encoding="utf-8").write(html.replace("</head>", inline + "</head>", 1))


# S3 — 진단 응답 스텁. file:// 렌더라 실제 fetch가 안 나가므로, **화면이 응답을 받았을 때**와
#   **못 받았을 때**를 각각 실제 코드 경로로 재현한다(그림 합성 0).
# 6-b: 화면이 **마켓별 단건 POST**를 부른다 — 스텁도 그 모양이어야 한다.
DIAG_OK = """() => {
  const byMarket = {
    coupang: { status: 'connected' },
    smartstore: { status: 'connected' },
    elevenst: { status: 'api_error', error_code: 'openapi_not_registered',
      action: '11번가 셀러오피스에서 OpenAPI 이용 신청/키 발급 상태를 먼저 확인하세요' },
    woocommerce: { status: 'connected' },
  };
  window.fetch = (url, opt) => {
    const m = JSON.parse((opt && opt.body) || '{}').market;
    const r = byMarket[m];
    if (!r) return new Promise(() => {});          // 모르는 마켓은 응답 없음 = 그 점만 '진단 실패'
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true, result: { market: m, ...r } }) });
  };
}"""
DIAG_HANG = """() => { window.fetch = () => new Promise(() => {}); }"""   # 전 마켓 응답 없음


def _shoot(br, tag, css, size, ops, stub=None):
    out_html = f"/tmp/_s6a_{tag}.html"
    _render(out_html, css, ops)
    pg = br.new_page(viewport={"width": size[0], "height": size[1]})
    if stub:
        pg.add_init_script("(" + stub + ")()")
    pg.goto(f"file://{out_html}")
    pg.wait_for_timeout(13000 if stub is DIAG_HANG else 900)   # 마켓별 12초 상한 통과 대기
    a = pg.evaluate(AUDIT)
    shot = pg.screenshot()
    pg.close()
    return a, shot


def _report(tag, a):
    print(f"  {tag} {a['vw']}×{a['vh']}: body 스크롤 {'있음 ✗' if a['bodyScrollY'] else '없음 ✓'} "
          f"({a['pageHeight']}/{a['vh']}) · 가로 {'있음 ✗' if a['bodyScrollX'] else '없음 ✓'} "
          f"· 공동 {a['hollow']}px")
    print(f"      카드 {a['cards']} · 그리드 {a['cols']}열 · 타일 {a['tiles']} "
          f"· 내부 스크롤 {len(a['scrollers'])}곳 · 44px 미만 타깃 {a['smallTargets']} "
          f"· 미연결 표기 {a['offline']}곳")


def main():
    from playwright.sync_api import sync_playwright

    files = (TPL, CSS, VIEWS, SNAP)
    base = {}
    for f in files:
        r = subprocess.run(["git", "show", f"origin/main:{f}"], capture_output=True, text=True)
        base[f] = r.stdout if r.returncode == 0 else None      # 신규 파일은 BEFORE에 없다
    cur = {f: open(f, encoding="utf-8").read() for f in files}
    variants = [("0데이터", EMPTY, DESKTOP, None), ("실데이터", LIVE, DESKTOP, DIAG_OK),
                ("진단실패", LIVE, DESKTOP, DIAG_HANG), ("390", LIVE, MOBILE, DIAG_OK)]
    shots, audits = {}, {}
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        for label, ops, size, stub in variants:
            audits[label], shots[label] = _shoot(br, label, cur[CSS], size, ops, stub)
        br.close()

    print("=== Stage 6-a 실측 ===")
    for label, _, _, _ in variants:
        _report(label, audits[label])
        print(f"      신호줄: {' '.join(audits[label]['signal'])}")

    os.makedirs(OUT_DIR, exist_ok=True)
    for label, png in shots.items():
        open(f"{OUT_DIR}/dashboard-{label}.png", "wb").write(png)
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
