"""F53 캡처 — 수행방패 쿠팡 사전검증(메타·출고지는 F48 계약의 목, 전송 0회): 보낼 상품명 + 노트.
사용: python scripts/_devshot_f53_precheck.py <before|after> <out_dir>
"""
import html as _h
import json
import os
import re
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
KO = ("수행 방패(SPORTLINK)는 애플 워치 충전 거치대 applewatch7 9용, S8 무선 iwatch 신형 Ultra2 시계 거치대, "
      "Airpods 이어폰 거치대")


def main():
    from playwright.sync_api import sync_playwright
    from tests.test_f48_coupang_register import SHIP_ENV, _meta, _no_post
    from src.channel_sync._channel_bridge import to_collected
    from src.uploaders.coupang_uploader import CoupangUploader
    for k, v in SHIP_ENV.items():
        os.environ[k] = v
    os.environ["COUPANG_IMAGE_SCREEN"] = "0"
    t = open("fixtures/realpages/diag/kgp-diagnostic-detail-tmall-com-item-htm-id-617129397971.html", encoding="utf-8").read()
    e = json.loads(re.search(r'<script type="application/json" id="kgp-diagnostic">(.*?)</script>', t, re.S).group(1))["extracted"]
    rows = []
    for label, extra in (("자동(드로어 손대지 않음)", {}),
                         ("오너가 번역 문장을 그대로 넣은 경우", {"coupang_name": KO, "coupang_name_source": "manual"})):
        u = CoupangUploader()
        u.predict_category = lambda *a, **k: "1001"
        u.overseas_outbound_place_code = "OVS1"
        _no_post(u, _meta(attrs=[]))
        prep = u.prepare_product(to_collected({"title": KO, "title_ko": KO, "title_en": e["title"], "price": 29.9,
                                               "currency": "CNY", "options": e["options"], "sell_price_krw": 30000, **extra}))
        out = u.precheck(prep)
        name_notes = [n for n in out["notes"] if "상품명" in n]
        rows.append((label, prep["title"], name_notes, out["holds"]))
    body = "".join(
        f"<tr><td>{_h.escape(a)}</td><td><b>{_h.escape(n)}</b></td><td>{'<br>'.join(_h.escape(x) for x in notes) or '(상품명 노트 없음)'}</td>"
        f"<td>{len(holds)}</td></tr>" for a, n, notes, holds in rows)
    page = ("<html><body style='font:14px/1.5 sans-serif;padding:20px;background:#FBF8F1'><h3 style='margin:0 0 8px'>"
            f"쿠팡 사전검증 — 수행방패 ({TAG})</h3><table border=1 cellpadding=8 style='border-collapse:collapse;background:#fff;max-width:1100px'>"
            "<tr><th>경우</th><th>쿠팡에 보낼 상품명</th><th>상품명 노트</th><th>보류 수</th></tr>" + body + "</table></body></html>")
    os.makedirs(OUT, exist_ok=True)
    open(f"/tmp/_f53pv_{TAG}.html", "w").write(page)
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CHROME)
        pg = br.new_page(viewport={"width": 1140, "height": 360})
        pg.goto(f"file:///tmp/_f53pv_{TAG}.html")
        pg.screenshot(path=f"{OUT}/f53-precheck-{TAG}.png", full_page=True)
        br.close()
    for r in rows:
        print(f"[{TAG}]", r[0], "|", r[1], "|", r[2], "| holds", len(r[3]))


if __name__ == "__main__":
    main()
