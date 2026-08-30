"""개발용 스크린샷 — 디자인 v2 Stage 5-d: 1920×940 좌표계에서 섹션 01+02 한 화면.

**합격 기준(오너 D1):** 뷰포트 **1920×940**(1080 모니터 − 브라우저 크롬 실측 여유)에서
섹션 01(입력폼)+02(검수결과 KPI 4장)가 스크롤 없이 들어오는가.
이후 모든 "한 화면" 판정은 이 좌표계다.

`--budget`을 주면 캡처 없이 **구간별 높이 내역**만 찍는다(어디서 몇 px 모자라는지 보고용).
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
OUT_DIR = "docs/screens/v40s5d"
VW, VH = 1920, 940                      # ★ D1 좌표계

sys.path.insert(0, "scripts")
from _devshot_v40s5_regpipe import REVIEW  # 같은 검수 데이터(동일 조건 비교)

# 구간별 높이 내역 — 여백에서 깎을 여지를 px로 본다(추측 금지).
MEASURE = """() => {
  const px = v => Math.round(v);
  const box = sel => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    return {top: px(r.top + scrollY), bottom: px(r.bottom + scrollY), h: px(r.height),
            padT: cs.paddingTop, padB: cs.paddingBottom, mT: cs.marginTop, mB: cs.marginBottom,
            fs: cs.fontSize};
  };
  const kpis = document.querySelectorAll('.rp-kpi');
  const last = kpis[kpis.length - 1];
  const zones = [...document.querySelectorAll('.rp-zone')].map(z => {
    const cs = getComputedStyle(z);
    return {h: px(z.getBoundingClientRect().height), padT: cs.paddingTop, padB: cs.paddingBottom};
  });
  return {
    viewport: window.innerHeight,
    kpiBottom: last ? px(last.getBoundingClientRect().bottom + scrollY) : null,
    pageHeight: document.documentElement.scrollHeight,
    hero: box('.rp-hero') || box('.rp-head'),
    lead: box('.rp-step-lead'),
    eyebrow: box('.rp-step-eyebrow'),
    step: box('.rp-step'),
    heroFoot: box('.rp-hero-foot'),
    title: box('.rp-step-title'),
    form: box('#urls'),
    kpisBox: box('.rp-kpis'),
    zones,
  };
}"""


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


def _shoot(br, tag, css):
    out_html = f"/tmp/_s5d_{tag}.html"
    _render(out_html, css)
    pg = br.new_page(viewport={"width": VW, "height": VH})
    pg.goto(f"file://{out_html}")
    pg.wait_for_timeout(800)
    m = pg.evaluate(MEASURE)
    shot = pg.screenshot()               # 뷰포트 1화면(스크롤 없음) — D4
    pg.close()
    return m, shot


def _report(tag, m):
    fits = "한 화면 O" if (m["kpiBottom"] or 9999) <= m["viewport"] else "스크롤 필요 X"
    short = (m["kpiBottom"] or 0) - m["viewport"]
    print(f"  {tag}: 헤드라인 {m['title']['fs'] if m['title'] else '-'} · "
          f"부제 {m['lead']['fs'] if m['lead'] else '-'} · "
          f"KPI 하단 {m['kpiBottom']}px / 뷰포트 {m['viewport']}px → {fits}"
          + (f" (모자람 {short}px)" if short > 0 else f" (여유 {-short}px)"))
    for i, z in enumerate(m["zones"], 1):
        print(f"      존{i:02d} h={z['h']}px pad={z['padT']}/{z['padB']}")
    for k in ("step", "eyebrow", "title", "lead", "hero", "form", "heroFoot", "kpisBox"):
        b = m.get(k)
        if b:
            print(f"      {k:8s} top={b['top']} h={b['h']} m={b['mT']}/{b['mB']} p={b['padT']}/{b['padB']}")


def main():
    budget_only = "--budget" in sys.argv
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
                metrics[tag], shots[tag] = _shoot(br, tag, src[CSS])
            br.close()
    finally:
        for f, content in cur.items():
            open(f, "w", encoding="utf-8").write(content)

    print(f"=== {VW}x{VH} 실측(D1 좌표계) ===")
    for tag in ("BEFORE", "AFTER"):
        _report(tag, metrics[tag])
    if budget_only:
        return

    from PIL import Image, ImageDraw
    os.makedirs(OUT_DIR, exist_ok=True)
    for tag in shots:
        open(f"{OUT_DIR}/regpipe-940-{tag.lower()}.png", "wb").write(shots[tag])
    ims = {t: Image.open(io.BytesIO(shots[t])) for t in shots}
    sc = 0.5
    ims = {t: i.resize((int(i.width * sc), int(i.height * sc))) for t, i in ims.items()}
    cv = Image.new("RGB", (ims["BEFORE"].width, ims["BEFORE"].height * 2 + 60), (238, 232, 220))
    d = ImageDraw.Draw(cv)
    y = 0
    for tag in ("BEFORE", "AFTER"):
        m = metrics[tag]
        fits = "FITS" if (m["kpiBottom"] or 9999) <= m["viewport"] else "SCROLL"
        d.text((10, y + 8), f"{tag}  {VW}x{VH}  title={m['title']['fs'] if m['title'] else '-'}  "
                            f"lead={m['lead']['fs'] if m['lead'] else '-'}  "
                            f"KPI bottom={m['kpiBottom']}px / {m['viewport']}px  -> {fits}",
               fill=(26, 23, 20))
        cv.paste(ims[tag], (0, y + 28))
        y += ims[tag].height + 30
    cv.save(f"{OUT_DIR}/regpipe-5d-940-before-after.png")
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
