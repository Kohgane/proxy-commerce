"""개발용 스크린샷 — 디자인 v2 Stage 5-e: 뷰포트 고정 2단 셸.

**합격 기준(오너 E1):** 1920×940에서 **body 스크롤바 부재**(`document.scrollHeight ≤ innerHeight`).
내부 스크롤은 03 표 영역 **1곳만** 허용 — 실제로 몇 곳이 스크롤하는지 세어서 보고한다.

**E6:** 캡처 2벌(1920×940 + 390) · E5 모바일 감사(가로 스크롤 · 터치 타깃 44px · 헤드라인).
"""
import io
import os
import subprocess
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

TPL = "src/seller_console/templates/register_pipe.html"
CSS = "src/static/app.css"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
OUT_DIR = "docs/screens/v40s5e"
DESKTOP = (1920, 940)          # ★ D1 좌표계(오너 확정)
MOBILE = (390, 844)

sys.path.insert(0, "scripts")
from _devshot_v40s5_regpipe import REVIEW  # 같은 검수 데이터(동일 조건 비교)

AUDIT = """() => {
  const px = v => Math.round(v);
  const vw = innerWidth, vh = innerHeight;
  // 내부 스크롤러 — E1은 "03 표 1곳만" 허용한다. 실제로 세어 본다.
  const scrollers = [...document.querySelectorAll('.rp-shell *')].filter(e => {
    const cs = getComputedStyle(e);
    return /auto|scroll/.test(cs.overflowY) && e.scrollHeight > e.clientHeight + 1;
  }).map(e => (e.className || '').toString().split(/\\s+/)[0]);
  // 뷰포트 밖으로 나간 요소(오프캔버스 사이드바는 의도된 것이라 제외).
  const over = [];
  document.querySelectorAll('.rp-shell, .rp-shell *').forEach(e => {
    const r = e.getBoundingClientRect();
    if (r.width === 0) return;
    if (r.right + scrollX > vw + 1 || r.left + scrollX < -1) {
      over.push(((e.className || '').toString().split(/\\s+/)[0]) || e.tagName.toLowerCase());
    }
  });
  const small = [];
  document.querySelectorAll('.rp-shell button, .rp-shell a, .rp-shell select, .rp-shell summary')
    .forEach(e => { const r = e.getBoundingClientRect();
      if (r.height > 0 && r.height < 44) small.push(
        ((e.className || '').toString().split(/\\s+/)[0] || e.tagName.toLowerCase()) + ':' + px(r.height)); });
  const t = document.querySelector('.rp-step-title');
  const shell = document.querySelector('.rp-shell');   // BEFORE(5-d)엔 셸이 없다 — null 가드.
  return {
    vw, vh,
    pageHeight: document.documentElement.scrollHeight,
    bodyScrollY: document.documentElement.scrollHeight > vh + 1,
    bodyScrollX: document.documentElement.scrollWidth > vw + 1,
    scrollers, overflow: [...new Set(over)], small: [...new Set(small)],
    titleFs: t ? getComputedStyle(t).fontSize : null,
    cols: shell ? getComputedStyle(shell).gridTemplateColumns : '(셸 없음 — 옛 세로 존)',
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
    for extra in EXTRA_CSS:
        if os.path.exists(extra):
            inline += "<style>" + open(extra, encoding="utf-8").read() + "</style>"
    open(html_path, "w", encoding="utf-8").write(html.replace("</head>", inline + "</head>", 1))


def _shoot(br, tag, css, size):
    out_html = f"/tmp/_s5e_{tag}_{size[0]}.html"
    _render(out_html, css)
    pg = br.new_page(viewport={"width": size[0], "height": size[1]})
    pg.goto(f"file://{out_html}")
    pg.wait_for_timeout(800)
    a = pg.evaluate(AUDIT)
    shot = pg.screenshot()          # 뷰포트 1화면(스크롤 없음) — E6
    pg.close()
    return a, shot


def _report(tag, a):
    ok = "없음 ✓" if not a["bodyScrollY"] else "있음 ✗"
    print(f"  {tag} {a['vw']}×{a['vh']}: body 세로 스크롤 {ok} "
          f"(scrollHeight {a['pageHeight']} / {a['vh']}) · 가로 "
          f"{'있음 ✗' if a['bodyScrollX'] else '없음 ✓'}")
    print(f"      내부 스크롤 영역 {len(a['scrollers'])}곳: {a['scrollers'] or '-'}")
    print(f"      뷰포트 밖 요소: {a['overflow'] or '0'} · 44px 미만 타깃: {a['small'] or '0'}")
    print(f"      헤드라인 {a['titleFs']} · 그리드 {a['cols']}")


def main():
    from PIL import Image, ImageDraw
    from playwright.sync_api import sync_playwright

    base = {f: subprocess.run(["git", "show", f"origin/main:{f}"], capture_output=True,
                              text=True).stdout for f in (TPL, CSS)}
    cur = {f: open(f, encoding="utf-8").read() for f in (TPL, CSS)}
    shots, audits = {}, {}
    try:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            for tag, src in (("BEFORE", base), ("AFTER", cur)):
                for f, content in src.items():
                    open(f, "w", encoding="utf-8").write(content)
                for size, key in ((DESKTOP, "desk"), (MOBILE, "mob")):
                    audits[(tag, key)], shots[(tag, key)] = _shoot(br, tag, src[CSS], size)
            br.close()
    finally:
        for f, content in cur.items():
            open(f, "w", encoding="utf-8").write(content)

    print("=== Stage 5-e 실측 ===")
    for key, label in (("desk", "데스크톱"), ("mob", "모바일")):
        for tag in ("BEFORE", "AFTER"):
            _report(f"{tag} {label}", audits[(tag, key)])

    os.makedirs(OUT_DIR, exist_ok=True)
    for (tag, key), png in shots.items():
        open(f"{OUT_DIR}/regpipe-{key}-{tag.lower()}.png", "wb").write(png)
    for key, w in (("desk", 0.5), ("mob", 1.0)):
        ims = {t: Image.open(io.BytesIO(shots[(t, key)])) for t in ("BEFORE", "AFTER")}
        ims = {t: i.resize((int(i.width * w), int(i.height * w))) for t, i in ims.items()}
        pad = 30
        cv = Image.new("RGB", (sum(i.width for i in ims.values()) + pad * 3,
                               max(i.height for i in ims.values()) + pad + 8), (238, 232, 220))
        d = ImageDraw.Draw(cv)
        x = pad
        for tag in ("BEFORE", "AFTER"):
            a = audits[(tag, key)]
            d.text((x, 8), f"{tag}  {a['vw']}x{a['vh']}  scrollHeight={a['pageHeight']}  "
                           f"bodyScroll={'YES' if a['bodyScrollY'] else 'NO'}  "
                           f"inner={len(a['scrollers'])}", fill=(26, 23, 20))
            cv.paste(ims[tag], (x, pad))
            x += ims[tag].width + pad
        cv.save(f"{OUT_DIR}/regpipe-5e-{key}-before-after.png")
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
