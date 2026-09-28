"""F49-T 4부-b 캡처 — world.taobao 실스냅샷(오너 재업로드 2026-09-28)에서 스크롤로 피드 칸이 붙을 때 툴바.

같은 스냅샷에 피드 칸(div.tb-pick-content-item)을 10개씩 3번 붙인다(상품 번호만 새로).
before(main)·after(이 브랜치) 각각 툴바 숫자와 행사 입구 처리를 찍는다.
사용: python scripts/_devshot_f49t4b.py <before|after> <out_dir>
"""
import os
import sys
from pathlib import Path

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())

APPEND = """(n) => {
  const feed = document.querySelector('.tb-pick-feeds-container');
  const unit = feed && feed.querySelector('.tb-pick-content-item');
  const a = unit && unit.querySelector('a.item-link');
  const id = ((a && a.getAttribute('href') || '').match(/[?&]id=(\\d{6,})/) || [])[1];
  if (!id) return 0;
  for (let i = 0; i < n; i++) {
    window.__wtSeq = (window.__wtSeq || 0) + 1;
    const nid = '9' + String(100000000000 + window.__wtSeq).slice(1);
    const el = unit.cloneNode(true);
    el.querySelectorAll('.kgp-card-chk, .kgp-card-quick').forEach(x => x.remove());
    el.querySelectorAll('*').forEach(x => x.getAttributeNames().forEach(k => { const v = x.getAttribute(k);
      if (v && v.indexOf(id) >= 0) x.setAttribute(k, v.split(id).join(nid)); }));
    feed.appendChild(el);
  }
  return n;
}"""
BAR = """() => { const b = document.getElementById('kgp-listing-toolbar'); const r = b && (b._kgpShadow || b);
  const c = r && r.querySelector('#kgp-tb-count'); return c ? c.textContent.replace(/\\s+/g, ' ').trim() : '(툴바 없음)'; }"""


def main():
    from playwright.sync_api import sync_playwright
    from tests import test_f49t4_infinite_scroll as T
    snap = sorted(Path("fixtures/realpages/diag").glob("kgp-snapshot-world-taobao-com*.html"))[0]
    body = snap.read_text(encoding="utf-8", errors="ignore")
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        b, page = T._open(pw, "https://world.taobao.com/", body, viewport=(1400, 900))
        page.wait_for_timeout(1500)
        rows = [("처음", page.evaluate(BAR), page.evaluate("() => KGP_WATCH.cards_total"))]
        for i in range(3):
            page.evaluate(APPEND, 10)
            page.wait_for_timeout(900)
            rows.append((f"스크롤 {i + 1}", page.evaluate(BAR), page.evaluate("() => KGP_WATCH.cards_total")))
        promos = page.evaluate("() => Array.from(document.querySelectorAll('.business-entry-container a, .business-entry-container [class*=item-card]')).filter(e => e.querySelector('.kgp-card-chk, .kgp-card-quick')).length")
        page.evaluate("() => { const f = document.querySelector('.tb-pick-feeds-container'); const u = f.children[f.children.length - 12]; u && u.scrollIntoView({block: 'center'}); }")
        page.wait_for_timeout(500)
        page.screenshot(path=f"{OUT}/f49t4b-feed-{TAG}.png")
        page.evaluate("() => window.scrollTo(0, 0)")
        page.wait_for_timeout(300)
        page.screenshot(path=f"{OUT}/f49t4b-top-{TAG}.png")
        b.close()
    for r in rows:
        print(f"[{TAG}] {r[0]:6s} 툴바='{r[1]}' 탐지={r[2]}")
    print(f"[{TAG}] 행사 입구에 붙은 선택 배지·수집 버튼 {promos}")


if __name__ == "__main__":
    main()
