"""scripts/build_intro_deck.py — K1a 소개서 **PDF** 생성(Chromium 인쇄).

`docs/apply/intro_content.json` **하나가 콘텐츠 단일 소스**다. pptx(편집용)와 PDF(제출용)는
같은 JSON을 읽는 **두 개의 출력기**일 뿐 — 문구가 두 벌로 갈리지 않는다(계약이 검사).

**왜 Chromium인가:** 이 샌드박스의 LibreOffice가 pptx를 하나도 못 연다(빈 python-pptx
파일로도 재현 — `Error: source file could not be loaded`). 그래서 soffice → PDF 경로가 없다.
대신 우리 실제 디자인 토큰(app.css)을 그대로 쓰는 HTML을 Chromium이 인쇄한다 —
브랜드 재현은 오히려 이쪽이 정확하다.

    python scripts/build_intro_deck.py
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT = os.path.join(ROOT, "docs/apply/intro_content.json")
OUT_PDF = os.path.join(ROOT, "docs/apply/gogabridj_intro_kakao_v2.pdf")
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# 디자인 v3 토큰(app.css :root) 승계 — 값을 여기서 새로 만들지 않는다.
T = {"ink": "#1A1714", "ink2": "#2A241E", "hanji": "#F5EFE3", "paper": "#FBF8F1",
     "gold": "#C9A24B", "goldsoft": "#E0C588", "teal": "#119A8E", "orange": "#F5821F",
     "line": "#E6DECB", "muted": "#8A8275", "inksoft": "#3A352E"}


def _img(rel_path: str) -> str:
    """이미지를 data URI로 인라인 — 인쇄 시 외부 로드에 의존하지 않게."""
    path = os.path.join(ROOT, rel_path)
    if not os.path.exists(path):
        return ""
    mime = mimetypes.guess_type(path)[0] or "image/png"
    with open(path, "rb") as fp:
        return f"data:{mime};base64," + base64.b64encode(fp.read()).decode()


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build_html(c: dict) -> str:
    cov, ov, mk, sec, pl, sl, ct = (c["cover"], c["overview"], c["markets"], c["security"],
                                    c["plan"], c["sellers"], c["contact"])

    def kicker(k):
        return f'<div class="kicker">{_esc(k)}</div>'

    def head(blk):
        return kicker(blk["kicker"]) + f'<h2>{_esc(blk["title"])}</h2>'

    steps = "".join(
        f'<div class="step"><div class="dot{" accent" if i == 5 else ""}">{i + 1}</div>'
        f'<div class="st">{_esc(t)}</div><div class="sd">{_esc(d)}</div></div>'
        for i, (t, d) in enumerate(ov["steps"]))

    mkrows = "".join(
        f'<div class="row"><span class="bullet {cls}"></span>'
        f'<div class="rn"><b>{_esc(n)}</b><span>{_esc(api)}</span></div>'
        f'<div class="rs">{_esc(st)}</div></div>'
        for n, api, st, cls in mk["rows"])

    secitems = "".join(
        f'<div class="sec-card{" wide" if i == 4 else ""}"><span class="ring"></span>'
        f'<b>{_esc(t)}</b><p>{_esc(d)}</p></div>'
        for i, (t, d) in enumerate(sec["items"]))

    def pairs(items):
        return "".join(f'<div class="pair"><b>{_esc(t)}</b><span>{_esc(d)}</span></div>'
                       for t, d in items)

    facts = "".join(f'<div class="fact"><span>{_esc(k)}</span><b>{_esc(v)}</b></div>'
                    for k, v in pl["facts"])
    stats = "".join(
        f'<div class="stat"><div class="num{" accent" if i == 0 else ""}">{_esc(n)}</div>'
        f'<div class="sk">{_esc(k)}</div><div class="sm">{_esc(d)}</div></div>'
        for i, (n, k, d) in enumerate(sl["stats"]))

    def rowtable(rows, cls=""):
        return "".join(f'<div class="kv {cls}"><span>{_esc(k)}</span><b>{_esc(v)}</b></div>'
                       for k, v in rows)

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<style>
  @page {{ size: 330mm 176mm; margin: 0; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font-family: "Noto Sans KR", "Malgun Gothic", sans-serif;
          color: {T['ink']}; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  .slide {{ width: 330mm; height: 176mm; padding: 18mm 20mm; page-break-after: always;
            position: relative; overflow: hidden; background: {T['paper']}; }}
  .slide:last-child {{ page-break-after: auto; }}
  .dark {{ background: {T['ink']}; color: {T['hanji']}; }}
  .kicker {{ font-size: 10pt; font-weight: 700; letter-spacing: .22em; color: {T['gold']};
             margin-bottom: 4mm; }}
  h1 {{ font-family: Georgia, "Times New Roman", serif; font-size: 46pt; margin: 0 0 3mm;
        letter-spacing: -.02em; }}
  h2 {{ font-family: Georgia, "Times New Roman", serif; font-size: 27pt; margin: 0 0 8mm;
        letter-spacing: -.015em; }}
  .tagline {{ font-size: 15pt; color: {T['goldsoft']}; margin-bottom: 8mm; }}
  .rule {{ width: 42mm; height: .6mm; background: {T['gold']}; margin: 0 0 9mm; }}
  .kv {{ display: flex; gap: 8mm; padding: 2.2mm 0; font-size: 11pt; }}
  .kv span {{ width: 34mm; color: {T['muted']}; }}
  .kv b {{ font-weight: 500; }}
  .steps {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 4mm; margin-bottom: 7mm; }}
  .step {{ background: #fff; border: .3mm solid {T['line']}; border-radius: 2.5mm; padding: 5mm; }}
  .dot {{ width: 9mm; height: 9mm; border-radius: 50%; background: {T['ink']}; color: #fff;
          font-family: Georgia, serif; font-weight: 700; font-size: 12pt; text-align: center;
          line-height: 9mm; margin-bottom: 4mm; }}
  .dot.accent {{ background: {T['orange']}; }}
  .st {{ font-family: Georgia, serif; font-weight: 700; font-size: 12.5pt; margin-bottom: 2mm; }}
  .sd {{ font-size: 9pt; color: {T['inksoft']}; line-height: 1.55; }}
  .note {{ font-size: 11pt; color: {T['inksoft']}; margin-bottom: 6mm; }}
  .muted-note {{ font-size: 10pt; color: {T['muted']}; font-style: italic; }}
  .shot {{ width: 100%; border: .3mm solid {T['line']}; border-radius: 2mm; object-fit: cover;
           object-position: top center; }}
  .cap {{ font-size: 8.5pt; color: {T['muted']}; margin-top: 2mm; }}
  .row {{ display: flex; align-items: center; gap: 6mm; background: #fff; border-radius: 2.5mm;
          border: .3mm solid {T['line']}; padding: 5mm 7mm; margin-bottom: 4mm; }}
  .bullet {{ width: 4mm; height: 4mm; border-radius: 50%; flex: none; }}
  .bullet.teal {{ background: {T['teal']}; }}  .bullet.gold {{ background: {T['gold']}; }}
  .rn {{ width: 52mm; }}
  .rn b {{ font-family: Georgia, serif; font-size: 13pt; display: block; }}
  .rn span {{ font-size: 9pt; color: {T['muted']}; }}
  .rs {{ font-size: 12pt; color: {T['inksoft']}; }}
  .sec-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; }}
  .sec-card {{ background: #fff; border: .3mm solid {T['line']}; border-radius: 2.5mm;
               padding: 5mm 6mm; position: relative; }}
  .sec-card.wide {{ grid-column: 1 / -1; }}
  .ring {{ position: absolute; left: 6mm; top: 6mm; width: 5mm; height: 5mm; border-radius: 50%;
           background: {T['hanji']}; box-shadow: inset 0 0 0 1.4mm {T['teal']}; }}
  .sec-card b {{ display: block; margin-left: 9mm; font-family: Georgia, serif; font-size: 12.5pt; }}
  .sec-card p {{ margin: 2mm 0 0 9mm; font-size: 9.5pt; color: {T['inksoft']}; line-height: 1.6; }}
  .two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; margin-bottom: 5mm; }}
  .panel {{ background: #fff; border: .3mm solid {T['line']}; border-radius: 2.5mm; padding: 6mm; }}
  .panel h3 {{ font-family: Georgia, serif; font-size: 14pt; margin: 0 0 4mm; }}
  .pair {{ margin-bottom: 3.5mm; }}
  .pair b {{ display: block; font-size: 10.5pt; color: {T['teal']}; }}
  .pair span {{ font-size: 9pt; color: {T['inksoft']}; }}
  .facts {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 6mm;
            background: {T['hanji']}; border-radius: 2.5mm; padding: 6mm 7mm; margin-bottom: 5mm; }}
  .fact span {{ display: block; font-size: 9pt; font-weight: 700; letter-spacing: .1em;
                color: {T['gold']}; margin-bottom: 1.5mm; }}
  .fact b {{ font-size: 11.5pt; font-weight: 500; }}
  .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 6mm; margin-bottom: 5mm; }}
  .stat {{ background: #fff; border: .3mm solid {T['line']}; border-radius: 2.5mm; padding: 6mm; }}
  .num {{ font-family: Georgia, serif; font-size: 40pt; font-weight: 700; line-height: 1; }}
  .num.accent {{ color: {T['orange']}; }}
  .sk {{ font-size: 11pt; font-weight: 700; margin-top: 3mm; }}
  .sm {{ font-size: 9pt; color: {T['muted']}; }}
  .headline {{ background: {T['hanji']}; border-radius: 2.5mm; padding: 5mm 7mm;
               font-family: Georgia, serif; font-size: 14pt; font-weight: 700; margin-bottom: 4mm; }}
  .dark .kv span {{ color: {T['muted']}; }}
  .dark .kv b {{ color: {T['hanji']}; }}
  .wordmark {{ position: absolute; right: 20mm; bottom: 16mm; font-family: Georgia, serif;
               font-size: 18pt; font-weight: 700; color: {T['goldsoft']}; }}
</style></head><body>

<section class="slide dark">
  {kicker(cov['kicker'])}
  <h1>{_esc(cov['brand'])}</h1>
  <div class="tagline">{_esc(cov['tagline'])}</div>
  <div class="rule"></div>
  {rowtable(cov['rows'])}
</section>

<section class="slide">
  {head(ov)}
  <div class="steps">{steps}</div>
  <div class="note">{_esc(ov['note'])}</div>
  <img class="shot" style="height:56mm" src="{_img(ov['shot'])}" alt="">
  <div class="cap">{_esc(ov['shot_caption'])}</div>
</section>

<section class="slide">
  {head(mk)}
  {mkrows}
  <div class="muted-note">{_esc(mk['note'])}</div>
</section>

<section class="slide">
  {head(sec)}
  <div class="sec-grid">{secitems}</div>
</section>

<section class="slide">
  {head(pl)}
  <div class="two">
    <div class="panel"><h3>매핑 모델</h3>{pairs(pl['model'])}</div>
    <div class="panel"><h3>연동 범위</h3>{pairs(pl['scope'])}</div>
  </div>
  <div class="facts">{facts}</div>
  <div class="muted-note">{_esc(pl['note'])}</div>
</section>

<section class="slide">
  {head(sl)}
  <div class="stats">{stats}</div>
  <div class="headline">{_esc(sl['headline'])}</div>
  <div class="note">{_esc(sl['goal'])}</div>
  <img class="shot" style="height:38mm" src="{_img(sl['shot'])}" alt="">
  <div class="cap">{_esc(sl['shot_caption'])}</div>
</section>

<section class="slide dark">
  {kicker(ct['kicker'])}
  <h1 style="font-size:36pt">{_esc(ct['title'])}</h1>
  <div class="rule"></div>
  {rowtable(ct['rows'])}
  <div class="wordmark">고가브릿지</div>
</section>

</body></html>"""


def main() -> int:
    with open(CONTENT, encoding="utf-8") as fp:
        content = json.load(fp)
    html = build_html(content)
    html_path = "/tmp/_intro_deck.html"
    with open(html_path, "w", encoding="utf-8") as fp:
        fp.write(html)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        pg = br.new_page()
        pg.goto(f"file://{html_path}")
        pg.wait_for_timeout(900)
        pg.pdf(path=OUT_PDF, width="330mm", height="176mm", print_background=True,
               margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        pg.close()
        br.close()

    size = os.path.getsize(OUT_PDF)
    print(f"저장 {OUT_PDF} · {size:,} bytes ({size / 1_048_576:.2f} MB)")
    if size > 10 * 1_048_576:
        print("⚠ 10MB 초과 — 이미지 압축 필요")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
