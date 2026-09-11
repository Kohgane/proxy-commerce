"""개발용 스크린샷 — C-트랙: 공유 텍스트 수집(폰 390).

**캡처 계약(오너):** 폰 390 3벌 — ①공유 텍스트 붙여넣기 ②초안 ③검수표 '보강 대기' 뱃지.

두 갈래를 **둘 다** 찍는다(폰이 편 갈래 / 전체(Global) 모드라 못 편 갈래) — 화면이 실제로 다르게 말하는지가
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
    # 갈래 이름은 **원인**으로 적는다 — "VPN 켜짐"이 아니라 "전체 모드"다.
    #   규칙/Smart 모드면 VPN이 켜져 있어도 폰이 링크를 편다(오너 확정 2026-09-11).
    for tag, fin in (("폰이-폄", FINAL_URL), ("전체모드", "")):
        r = collect_from_share_text(SHARE_TEXT, seller_id=SELLER, translate=False, final_url=fin)
        made[tag] = r
        print(f"  초안[{tag}] ok={r['ok']} item={r.get('item_id')} "
              f"가격={r.get('price') or '(없음)'} 게이트={r.get('enrich_state')} "
              f"미수집={','.join(r.get('uncollected') or [])}")

    shots = [("01-일괄결과", "/seller/collect")]
    # C-F5: 오너가 실제로 겪은 자리 — 「여러 URL 한 번에」 결과 영역.
    #   전엔 "전체 2 · 성공 0 · 실패 2"였다. 지금은 성공 카드 1장이어야 한다.
    bulk_html = None
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
                if name == "01-일괄결과":
                    # 붙여넣고 실제로 일괄 수집을 돌린 **결과 영역**을 그린다(목업 아님).
                    import json as _j
                    with app.test_client() as c2:
                        with c2.session_transaction() as sess:
                            sess["user_id"] = SELLER
                        bulk = c2.post("/seller/collect/bulk",
                                       json={"urls": SHARE_TEXT}).get_json()
                    pg.evaluate("""([t, d]) => {
                      const e = document.getElementById('bulkUrls'); if (e) e.value = t;
                      const box = document.getElementById('bulkResult'); if (!box) return;
                      let h = `<div class="pc-status pc-status-info small mb-2">전체 ${d.total}개 · 성공 <strong>${d.success}</strong> · 실패 ${d.total - d.success}</div><ul class="list-group">`;
                      (d.results || []).forEach(r => {
                        const left = (r.uncollected || []).map(f => ({price:'가격',images:'이미지',options:'옵션',description:'상세설명'}[f] || f)).join('·');
                        const note = r.kind === 'share_draft'
                          ? `<div class="small text-muted mt-1">초안 1건 생성 — 제목 담김${r.price ? ' · 가격 ' + r.price + ' ' + (r.currency||'') : ''}${left ? ' · ' + left + '은 단축어/PC 보강' : ''}</div>` : '';
                        h += `<li class="list-group-item d-flex justify-content-between align-items-start"><span><i class="bi bi-check-circle" style="color:var(--success)"></i> ${r.title}${note}</span><a href="#" class="btn btn-sm btn-ghost py-0">확인·등록</a></li>`;
                      });
                      box.innerHTML = h + '</ul>'; box.classList.remove('d-none');
                    }""", [SHARE_TEXT, bulk])
                    pg.wait_for_timeout(300)
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
