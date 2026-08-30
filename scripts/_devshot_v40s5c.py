"""개발용 스크린샷 — 디자인 v2 Stage 5-c: 존 패딩 48px + 디스플레이 타이포 1단 축소.

**합격 기준 실측:** 1080p(1920×1080)에서 섹션 01(입력폼)+02(검수결과 카드 4장)가
**스크롤 없이 한 화면**에 들어오는가 — 마지막 KPI 카드의 bottom Y를 뷰포트 높이와 대조한다.
"""
import io
import os
import subprocess
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

TPL = "src/seller_console/templates/register_pipe.html"
CSS = "src/static/app.css"
SELLER_CSS = "src/seller_console/static/seller.css"
CONSOLE_CSS = "src/seller_console/static/console.css"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
OUT_DIR = "docs/screens/v40s5c"

sys.path.insert(0, "scripts")
from _devshot_v40s5_regpipe import REVIEW  # 같은 검수 데이터(동일 조건 비교)


def _render(html_path, app_css):
    from flask import render_template

    from src.order_webhook import app
    app.jinja_env.cache.clear()
    with app.test_request_context("/seller/sourcing/register-pipe"):
        html = render_template("register_pipe.html", page="sourcing", review=REVIEW, urls_text="")
    inline = ""
    if os.path.exists(BOOTSTRAP):
        inline += "<style>" + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    inline += "<style>" + app_css + "</style>"
    for extra in (SELLER_CSS, CONSOLE_CSS):
        if os.path.exists(extra):
            inline += "<style>" + open(extra, encoding="utf-8").read() + "</style>"
    html = html.replace("</head>", inline + "</head>", 1)
    open(html_path, "w", encoding="utf-8").write(html)


def main():
    from PIL import Image, ImageDraw
    from playwright.sync_api import sync_playwright

    base = {f: subprocess.run(["git", "show", f"origin/main:{f}"], capture_output=True,
                              text=True).stdout for f in (TPL, CSS)}
    cur = {f: open(f, encoding="utf-8").read() for f in (TPL, CSS)}
    shots, metrics = {}, {}
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            for tag, src in (("BEFORE", base), ("AFTER", cur)):
                for f, content in src.items():
                    open(f, "w", encoding="utf-8").write(content)
                out_html = f"/tmp/_s5c_{tag}.html"
                _render(out_html, src[CSS])
                pg = br.new_page(viewport={"width": 1920, "height": 1080})
                pg.goto(f"file://{out_html}")
                pg.wait_for_timeout(800)
                m = pg.evaluate("""() => {
                  const kpis = document.querySelectorAll('.rp-kpi');
                  const last = kpis[kpis.length - 1];
                  const title = document.querySelector('.rp-step-title');
                  const zone = document.querySelector('.rp-zone');
                  return {
                    kpiBottom: last ? Math.round(last.getBoundingClientRect().bottom + window.scrollY) : null,
                    viewport: window.innerHeight,
                    titlePx: title ? getComputedStyle(title).fontSize : null,
                    zonePadTop: zone ? getComputedStyle(zone).paddingTop : null,
                    pageHeight: document.documentElement.scrollHeight,
                  };
                }""")
                metrics[tag] = m
                shots[tag] = pg.screenshot()          # 뷰포트 1화면(스크롤 없음)
                pg.close()
            br.close()
    finally:
        for f, content in cur.items():
            open(f, "w", encoding="utf-8").write(content)

    os.makedirs(OUT_DIR, exist_ok=True)
    for tag in shots:
        open(f"{OUT_DIR}/regpipe-1080p-{tag.lower()}.png", "wb").write(shots[tag])
    ims = {t: Image.open(io.BytesIO(shots[t])) for t in shots}
    sc = 0.5
    ims = {t: i.resize((int(i.width * sc), int(i.height * sc))) for t, i in ims.items()}
    cv = Image.new("RGB", (ims["BEFORE"].width, ims["BEFORE"].height * 2 + 60), (238, 232, 220))
    d = ImageDraw.Draw(cv)
    y = 0
    for tag in ("BEFORE", "AFTER"):
        m = metrics[tag]
        d.text((10, y + 8), f"{tag}  1920x1080  title={m['titlePx']}  zonePad={m['zonePadTop']}  "
                            f"KPI bottom={m['kpiBottom']}px  page={m['pageHeight']}px",
               fill=(26, 23, 20))
        cv.paste(ims[tag], (0, y + 28))
        y += ims[tag].height + 30
    cv.save(f"{OUT_DIR}/regpipe-5c-1080p-before-after.png")
    print("=== 1080p 실측 ===")
    for tag in ("BEFORE", "AFTER"):
        m = metrics[tag]
        fits = "한 화면 O" if (m["kpiBottom"] or 9999) <= m["viewport"] else "스크롤 필요 X"
        print(f"  {tag}: 헤드라인 {m['titlePx']} · 존패딩 {m['zonePadTop']} · "
              f"KPI 하단 {m['kpiBottom']}px / 뷰포트 {m['viewport']}px → {fits} · 페이지 {m['pageHeight']}px")
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
