"""개발용 스크린샷 — 디자인 v2 Stage 5-f: 공동 제거·비율 교정.

**합격 기준(오너 F5):** 0행 / 1행 / 30행 **3벌 전부 공동이 없어야** 한다.
공동 = 카드 밖 빈 배경. 좌우 카드가 열 높이를 끝까지 쓰는지 실측한다
(카드 bottom vs 셸 bottom 차이 = 공동 px).

F1 열 비율 32/68 · F6 scrollHeight ≤ 940 · 모바일 1열도 같이 잰다.
"""
import io
import os
import re
import subprocess
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

TPL = "src/seller_console/templates/register_pipe.html"
CSS = "src/static/app.css"
PIPE = "src/pipeline/register_pipe.py"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
OUT_DIR = "docs/screens/v40s5f"
DESKTOP = (1920, 940)
MOBILE = (390, 844)

sys.path.insert(0, "scripts")
from _devshot_v40s5_regpipe import REVIEW

AUDIT = """() => {
  const px = v => Math.round(v);
  const vw = innerWidth, vh = innerHeight;
  const shell = document.querySelector('.rp-shell');
  const sr = shell ? shell.getBoundingClientRect() : null;
  // 공동 = 열 안에서 카드가 못 채운 아래 여백. 좌(입력 카드)·우(통합 카드) 각각 잰다.
  const gap = (sel) => {
    const el = document.querySelector(sel);
    if (!el || !sr) return null;
    return px(sr.bottom - el.getBoundingClientRect().bottom);
  };
  const scrollers = [...document.querySelectorAll('.rp-shell *')].filter(e => {
    const cs = getComputedStyle(e);
    return /auto|scroll/.test(cs.overflowY) && e.scrollHeight > e.clientHeight + 1;
  }).map(e => (e.className || '').toString().split(/\\s+/)[0]);
  const ta = document.querySelector('.rp-input');
  const cols = shell ? getComputedStyle(shell).gridTemplateColumns.split(' ').map(v => px(parseFloat(v))) : [];
  const total = cols.reduce((a, b) => a + b, 0) || 1;
  return {
    vw, vh,
    pageHeight: document.documentElement.scrollHeight,
    bodyScrollY: document.documentElement.scrollHeight > vh + 1,
    bodyScrollX: document.documentElement.scrollWidth > vw + 1,
    cols, ratio: cols.map(c => Math.round(c / total * 100)),
    gapLeft: gap('.rp-pane-in .rp-hero'),
    gapRight: gap('.rp-card') ?? gap('.rp-pane-work > *:last-child'),
    textareaH: ta ? px(ta.getBoundingClientRect().height) : null,
    textareaRows: ta ? Math.floor(ta.getBoundingClientRect().height /
                      parseFloat(getComputedStyle(ta).lineHeight || 20)) : null,
    scrollers,
    emptyMsg: !!document.querySelector('.rp-listempty'),
    rows: document.querySelectorAll('.rp-table tbody tr').length,
  };
}"""


def _variant(n):
    """행 수 n짜리 검수 데이터. 0 = 빈 상태(F5)."""
    base = dict(REVIEW)
    rows = list(REVIEW["review_pass"]) + list(REVIEW["excluded"])
    if not rows:
        rows = []
    out = []
    for i in range(n):
        src = dict(rows[i % len(rows)]) if rows else {}
        src["url"] = f"https://www.amazon.com/dp/B0TEST{i:04d}?ref=sr_1_{i}&keywords=x&qid=17{i}"
        # BEFORE(origin/main)엔 `_short_url`이 없다 → 데이터 생성은 devshot이 자립한다.
        short = re.sub(r"^https?://", "", src["url"].split("?", 1)[0]).rstrip("/")
        src["url_short"] = short if len(short) <= 60 else short[:59] + "…"
        out.append(src)
    base["review_pass"] = out
    base["excluded"] = []
    base["failed"] = []
    base["requested"] = n
    return base


def _render(html_path, app_css, review):
    from flask import render_template

    from src.order_webhook import app
    app.jinja_env.cache.clear()
    with app.test_request_context("/seller/sourcing/register-pipe"):
        html = render_template("register_pipe.html", page="sourcing", review=review, urls_text="")
    inline = ""
    if os.path.exists(BOOTSTRAP):
        inline += "<style>" + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    inline += "<style>" + app_css + "</style>"
    for extra in EXTRA_CSS:
        if os.path.exists(extra):
            inline += "<style>" + open(extra, encoding="utf-8").read() + "</style>"
    open(html_path, "w", encoding="utf-8").write(html.replace("</head>", inline + "</head>", 1))


def _shoot(br, tag, css, size, review):
    out_html = f"/tmp/_s5f_{tag}_{size[0]}.html"
    _render(out_html, css, review)
    pg = br.new_page(viewport={"width": size[0], "height": size[1]})
    pg.goto(f"file://{out_html}")
    pg.wait_for_timeout(700)
    a = pg.evaluate(AUDIT)
    shot = pg.screenshot()
    pg.close()
    return a, shot


def _report(tag, a):
    hollow = [g for g in (a["gapLeft"], a["gapRight"]) if g is not None and g > 4]
    print(f"  {tag}: 비율 {a['ratio']} · 공동 좌 {a['gapLeft']}px / 우 {a['gapRight']}px "
          f"→ {'없음 ✓' if not hollow else '있음 ✗'}")
    print(f"      body 스크롤 {'있음 ✗' if a['bodyScrollY'] else '없음 ✓'} "
          f"({a['pageHeight']}/{a['vh']}) · 내부 스크롤 {len(a['scrollers'])}곳 "
          f"· textarea {a['textareaH']}px(~{a['textareaRows']}줄) · 표 {a['rows']}행"
          f"{' · 빈 상태 안내 O' if a['emptyMsg'] else ''}")


def main():
    from PIL import Image, ImageDraw
    from playwright.sync_api import sync_playwright

    files = (TPL, CSS, PIPE)
    base = {f: subprocess.run(["git", "show", f"origin/main:{f}"], capture_output=True,
                              text=True).stdout for f in files}
    cur = {f: open(f, encoding="utf-8").read() for f in files}
    shots, audits = {}, {}
    variants = [("0행", 0), ("1행", 1), ("30행", 30)]
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            for tag, src in (("BEFORE", base), ("AFTER", cur)):
                for f, content in src.items():
                    open(f, "w", encoding="utf-8").write(content)
                for label, n in variants:
                    key = (tag, label)
                    audits[key], shots[key] = _shoot(br, f"{tag}{n}", src[CSS], DESKTOP, _variant(n))
                audits[(tag, "mobile")], shots[(tag, "mobile")] = _shoot(
                    br, f"{tag}m", src[CSS], MOBILE, _variant(30))
            br.close()
    finally:
        for f, content in cur.items():
            open(f, "w", encoding="utf-8").write(content)

    print("=== Stage 5-f 실측(1920×940) ===")
    for label, _ in variants:
        for tag in ("BEFORE", "AFTER"):
            _report(f"{tag} {label}", audits[(tag, label)])
    print("=== 모바일 390 ===")
    for tag in ("BEFORE", "AFTER"):
        _report(f"{tag} 모바일", audits[(tag, "mobile")])

    os.makedirs(OUT_DIR, exist_ok=True)
    for (tag, label), png in shots.items():
        open(f"{OUT_DIR}/regpipe-{label}-{tag.lower()}.png", "wb").write(png)
    for label, _ in variants:
        ims = {t: Image.open(io.BytesIO(shots[(t, label)])) for t in ("BEFORE", "AFTER")}
        ims = {t: i.resize((i.width // 2, i.height // 2)) for t, i in ims.items()}
        pad = 30
        cv = Image.new("RGB", (sum(i.width for i in ims.values()) + pad * 3,
                               max(i.height for i in ims.values()) + pad + 8), (238, 232, 220))
        d = ImageDraw.Draw(cv)
        x = pad
        for tag in ("BEFORE", "AFTER"):
            a = audits[(tag, label)]
            d.text((x, 8), f"{tag}  {label}  ratio={a['ratio']}  "
                           f"hollow L={a['gapLeft']} R={a['gapRight']}  "
                           f"scrollHeight={a['pageHeight']}", fill=(26, 23, 20))
            cv.paste(ims[tag], (x, pad))
            x += ims[tag].width + pad
        cv.save(f"{OUT_DIR}/regpipe-5f-{label}-before-after.png")
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
