"""개발용 스크린샷 — 디자인 v3 Stage 6-a: 운영 대시보드.

**합격 기준(오너 G1·G4):** 1920×940 body 스크롤바 0 · 390px 1열 폴백 ·
카드 밖 공동 0. 캡처 3벌 — **0데이터 / 실데이터 / 390px**.

0데이터 = 전 블록 미연결(정직 표기가 실제로 나오는지). 실데이터 = 계정·대장·큐가 찬 상태.
"""
import io
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


def _shoot(br, tag, css, size, ops):
    out_html = f"/tmp/_s6a_{tag}.html"
    _render(out_html, css, ops)
    pg = br.new_page(viewport={"width": size[0], "height": size[1]})
    pg.goto(f"file://{out_html}")
    pg.wait_for_timeout(700)
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
    from PIL import Image, ImageDraw
    from playwright.sync_api import sync_playwright

    files = (TPL, CSS, VIEWS, SNAP)
    base = {}
    for f in files:
        r = subprocess.run(["git", "show", f"origin/main:{f}"], capture_output=True, text=True)
        base[f] = r.stdout if r.returncode == 0 else None      # 신규 파일은 BEFORE에 없다
    cur = {f: open(f, encoding="utf-8").read() for f in files}
    variants = [("0데이터", EMPTY, DESKTOP), ("실데이터", LIVE, DESKTOP), ("390", LIVE, MOBILE)]
    shots, audits = {}, {}
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        for label, ops, size in variants:
            audits[label], shots[label] = _shoot(br, label, cur[CSS], size, ops)
        br.close()

    print("=== Stage 6-a 실측 ===")
    for label, _, _ in variants:
        _report(label, audits[label])

    os.makedirs(OUT_DIR, exist_ok=True)
    for label, png in shots.items():
        open(f"{OUT_DIR}/dashboard-{label}.png", "wb").write(png)
    # 데스크톱 2벌은 나란히, 모바일은 단독.
    ims = {l: Image.open(io.BytesIO(shots[l])) for l in ("0데이터", "실데이터")}
    ims = {l: i.resize((i.width // 2, i.height // 2)) for l, i in ims.items()}
    pad = 30
    cv = Image.new("RGB", (sum(i.width for i in ims.values()) + pad * 3,
                           max(i.height for i in ims.values()) + pad + 8), (238, 232, 220))
    d = ImageDraw.Draw(cv)
    x = pad
    for label in ("0데이터", "실데이터"):
        a = audits[label]
        d.text((x, 8), f"{label}  {a['vw']}x{a['vh']}  scrollHeight={a['pageHeight']}  "
                       f"hollow={a['hollow']}  cards={a['cards']}", fill=(26, 23, 20))
        cv.paste(ims[label], (x, pad))
        x += ims[label].width + pad
    cv.save(f"{OUT_DIR}/dashboard-6a-desktop.png")
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
