"""개발용 스크린샷 — C-트랙: 공유 텍스트 수집(폰 390).

**캡처 계약(오너):** 폰 390 3벌 — ①공유 텍스트 붙여넣기 ②초안 ③검수표 '보강 대기' 뱃지.

두 갈래를 **둘 다** 찍는다(폰이 편 갈래 / 못 편 갈래) — 화면이 실제로 다르게 말하는지가
이 트랙의 핵심이라, 한쪽만 찍으면 그 핵심이 캡처에 안 남는다.
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
os.environ["SELLER_CONSOLE_AUTH"] = "0"

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
BOOTSTRAP = "/tmp/bsdl/node_modules/bootstrap/dist/css/bootstrap.min.css"
EXTRA_CSS = ("src/seller_console/static/seller.css", "src/seller_console/static/console.css")
OUT_DIR = "docs/screens/v40c"
MOBILE = (390, 844)
# 미인증 캡처 세션이 해석하는 셀러 — 이걸 안 맞추면 드로어가 항목을 못 찾아 "수집 실패"가 찍힌다.
SELLER = "default"

SHARE_TEXT = (
    "【淘宝】https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt CZ356\n"
    "「新中式双人书桌靠墙长条桌简约现代学生写字学习桌实木办公电脑桌」\n"
    "点击链接直接打开 或者 淘宝搜索直接打开"
)
FINAL_URL = ("https://m.intl.taobao.com/detail/detail.html?id=993154784090"
             "&price=199&tk=nyXpT7VA7lt&short_name=h.8IcTrtZuTU19ieN")

AUDIT = """() => ({
  vw: innerWidth,
  pageHeight: Math.max(document.documentElement.scrollHeight,
    ...[...document.querySelectorAll('main')].map(m => m.getBoundingClientRect().bottom)),
  scrollX: document.documentElement.scrollWidth > innerWidth + 1,
  warn: (document.querySelector('.pc-status-warning')||{}).innerText || '',
  badge: [...document.querySelectorAll('.pc-badge')].map(b => b.textContent.trim()).slice(0,6),
  price: (document.getElementById('editPrice')||{}).value || '(빈칸)',
})"""


def _inline(html: str) -> str:
    css = ""
    if os.path.exists(BOOTSTRAP):
        css += '<style data-devshot>' + open(BOOTSTRAP, encoding="utf-8").read() + "</style>"
    css += '<style data-devshot>' + open("src/static/app.css", encoding="utf-8").read() + "</style>"
    for extra in EXTRA_CSS:
        if os.path.exists(extra):
            css += '<style data-devshot>' + open(extra, encoding="utf-8").read() + "</style>"
    return html.replace("</head>", css + "</head>", 1)


def main():
    from playwright.sync_api import sync_playwright

    from src.order_webhook import app
    from src.collectors.share_collect import collect_from_share_text
    app.jinja_env.cache.clear()
    os.makedirs(OUT_DIR, exist_ok=True)

    # 두 갈래 초안을 실제로 만든다(목업 아님 — 실제 저장 경로를 태운다).
    made = {}
    for tag, fin in (("폰이-폄", FINAL_URL), ("VPN-켜짐", "")):
        r = collect_from_share_text(SHARE_TEXT, seller_id=SELLER, translate=False, final_url=fin)
        made[tag] = r
        print(f"  초안[{tag}] ok={r['ok']} item={r.get('item_id')} "
              f"가격={r.get('price') or '(없음)'} 게이트={r.get('enrich_state')} "
              f"미수집={','.join(r.get('uncollected') or [])}")

    shots = [("01-입력", "/seller/collect")]
    for tag, r in made.items():
        if r.get("ok"):
            shots.append((f"02-초안-{tag}", f"/seller/collect/preview/{r['item_id']}?drawer=1"))

    print(f"\n=== C-트랙 폰 캡처 ({MOBILE[0]}px) ===")
    with app.test_client() as client:
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            for name, url in shots:
                res = client.get(url, follow_redirects=True)
                path = f"/tmp/_c_{name}.html"
                open(path, "w", encoding="utf-8").write(_inline(res.get_data(as_text=True)))
                pg = br.new_page(viewport={"width": MOBILE[0], "height": MOBILE[1]})
                pg.goto(f"file://{path}")
                pg.wait_for_timeout(600)
                if name == "01-입력":                 # 붙여넣은 상태를 재현
                    pg.evaluate("t => { const e = document.getElementById('productUrl');"
                                "if (e) e.value = t; }", SHARE_TEXT)
                    pg.wait_for_timeout(200)
                a = pg.evaluate(AUDIT)
                pg.screenshot(path=f"{OUT_DIR}/{name}.png", full_page=True)
                pg.close()
                print(f"  {name:22s} HTTP {res.status_code} · 높이 {int(a['pageHeight']):4d} · "
                      f"가로스크롤 {'있음 ✗' if a['scrollX'] else '없음 ✓'} · 가격 {a['price']}")
                if a["warn"]:
                    print(f"      경고문: {a['warn'][:70]}")
                if a["badge"]:
                    print(f"      뱃지: {a['badge']}")
            br.close()
    print("saved", OUT_DIR)


if __name__ == "__main__":
    main()
