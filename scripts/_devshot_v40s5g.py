"""개발용 스크린샷 — 디자인 v2 Stage 5-g: 빈 영역 정리 + textarea 자동 높이.

**캡처 계약 변경(오너 H4):** BEFORE/AFTER 병치 축소판 **금지**. AFTER 단독, **원본 해상도**로 낸다
(1920×940 1장 + 390 1장). 축소 캡처가 직전 판정 착오의 원인이었다 — 오너는 실제 크기로 본다.

H1 빈 영역 무늬 0 · H2 0행 안내 1줄 · H6 textarea 6줄~카드 잔여 · H7 카드 stretch·내용 상단 정렬.
"""
import os
import re
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
OUT_DIR = "docs/screens/v40s5g"
DESKTOP = (1920, 940)
MOBILE = (390, 844)

sys.path.insert(0, "scripts")
from _devshot_v40s5_regpipe import REVIEW

AUDIT = """() => {
  const px = v => Math.round(v);
  const vw = innerWidth, vh = innerHeight;
  const shell = document.querySelector('.rp-shell');
  const sr = shell ? shell.getBoundingClientRect() : null;
  const gap = (sel) => { const el = document.querySelector(sel);
    return (el && sr) ? px(sr.bottom - el.getBoundingClientRect().bottom) : null; };
  const ta = document.querySelector('.rp-input');
  const body = document.querySelector('.rp-card > .rp-scroll');
  const cs = body ? getComputedStyle(body) : null;
  const foot = document.querySelector('.rp-hero-foot');
  return {
    vw, vh,
    pageHeight: document.documentElement.scrollHeight,
    bodyScrollY: document.documentElement.scrollHeight > vh + 1,
    bodyScrollX: document.documentElement.scrollWidth > vw + 1,
    hollowLeft: gap('.rp-pane-in .rp-hero'), hollowRight: gap('.rp-card'),
    bodyBgImage: cs ? cs.backgroundImage : null,
    textareaH: ta ? px(ta.getBoundingClientRect().height) : null,
    textareaRows: ta ? Math.round(ta.getBoundingClientRect().height /
                       parseFloat(getComputedStyle(ta).lineHeight || 18)) : null,
    footTop: foot ? px(foot.getBoundingClientRect().top) : null,
    taBottom: ta ? px(ta.getBoundingClientRect().bottom) : null,
    emptyMsg: !!document.querySelector('.rp-listempty'),
    rows: document.querySelectorAll('.rp-table tbody tr').length,
  };
}"""


def _variant(n, urls=0):
    base = dict(REVIEW)
    rows = list(REVIEW["review_pass"]) + list(REVIEW["excluded"])
    out = []
    for i in range(n):
        src = dict(rows[i % len(rows)]) if rows else {}
        src["url"] = f"https://www.amazon.com/dp/B0TEST{i:04d}?ref=sr_1_{i}&keywords=x"
        short = re.sub(r"^https?://", "", src["url"].split("?", 1)[0]).rstrip("/")
        src["url_short"] = short if len(short) <= 60 else short[:59] + "\u2026"
        out.append(src)
    base["review_pass"], base["excluded"], base["failed"] = out, [], []
    base["requested"] = n
    return base


def _urls_text(n):
    return "\n".join(f"https://www.amazon.com/dp/B0TEST{i:04d}" for i in range(n))


def _render(html_path, review, urls_text):
    from flask import render_template

    from src.order_webhook import app
    app.jinja_env.cache.clear()
    with app.test_request_context("/seller/sourcing/register-pipe"):
        html = render_template("register_pipe.html", page="sourcing",
                               review=review, urls_text=urls_text)
    inline = ""
    if os.path.exists(BOOTSTRAP):
        inline += "<style>" + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    inline += "<style>" + open("src/static/app.css", encoding="utf-8").read() + "</style>"
    for extra in EXTRA_CSS:
        if os.path.exists(extra):
            inline += "<style>" + open(extra, encoding="utf-8").read() + "</style>"
    open(html_path, "w", encoding="utf-8").write(html.replace("</head>", inline + "</head>", 1))


def main():
    from playwright.sync_api import sync_playwright

    os.makedirs(OUT_DIR, exist_ok=True)
    shots = [
        ("0행-빈입력", _variant(0), "", DESKTOP),
        ("1행", _variant(1), _urls_text(1), DESKTOP),
        ("30행-URL50", _variant(30), _urls_text(50), DESKTOP),
        ("390", _variant(30), _urls_text(3), MOBILE),
    ]
    print("=== Stage 5-g 실측 (AFTER 단독 · 원본 해상도) ===")
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        for label, review, urls, size in shots:
            path = f"/tmp/_s5g_{label}.html"
            _render(path, review, urls)
            pg = br.new_page(viewport={"width": size[0], "height": size[1]})
            pg.goto(f"file://{path}")
            pg.wait_for_timeout(700)
            a = pg.evaluate(AUDIT)
            pg.screenshot(path=f"{OUT_DIR}/regpipe-5g-{label}.png")   # 원본 해상도 · 축소 0
            pg.close()
            hollow = f"좌 {a['hollowLeft']} / 우 {a['hollowRight']}"
            print(f"  {label} {a['vw']}×{a['vh']}: scrollHeight {a['pageHeight']}/{a['vh']} "
                  f"· 공동 {hollow} · 빈영역 무늬 {a['bodyBgImage']}")
            print(f"      textarea {a['textareaH']}px(~{a['textareaRows']}줄) "
                  f"· 버튼줄 top {a['footTop']} (textarea 하단 {a['taBottom']}) "
                  f"· 표 {a['rows']}행{' · 빈 상태 안내 O' if a['emptyMsg'] else ''}")
        br.close()
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
