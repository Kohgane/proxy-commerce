"""F49-T 4부 캡처 — 아마존 검색 실스냅샷: 로드 직후 툴바 → 카드 30장(10×3) 추가 + 「전체 선택」 뒤 툴바.

world.taobao 스냅샷은 아직 레포에 없다(오너 업로드 대기) — 올라오면 같은 스크립트에 URL만 바꿔 돌린다.
사용: python scripts/_devshot_f49t4.py <before|after> <out_dir>
"""
import os
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())


def main():
    from pathlib import Path
    from playwright.sync_api import sync_playwright
    import tests.test_f49t4_infinite_scroll as T
    snap, url = T.REAL[0]
    body = sorted(Path("fixtures/realpages/diag").glob(snap))[0].read_text(encoding="utf-8", errors="ignore")
    os.makedirs(OUT, exist_ok=True)
    count_js = """() => { const b = document.getElementById('kgp-listing-toolbar'); const r = b && (b._kgpShadow || b);
                   const c = r && r.querySelector('#kgp-tb-count'); return c ? c.textContent : '(툴바 없음)'; }"""
    with sync_playwright() as pw:
        b, page = T._open(pw, url, body)
        page.wait_for_timeout(1500)
        page.evaluate("() => window.scrollTo(0, 0)")
        t0 = page.evaluate(count_js)
        page.locator("#kgp-listing-toolbar").screenshot(path=f"{OUT}/f49t4-toolbar-{TAG}-1-load.png")
        for _ in range(3):
            page.evaluate(T.CLONE, 10)
            page.wait_for_timeout(700)
        T._click_all(page)
        page.wait_for_timeout(300)
        t1 = page.evaluate(count_js)
        page.locator("#kgp-listing-toolbar").screenshot(path=f"{OUT}/f49t4-toolbar-{TAG}-2-scrolled.png")
        diag = page.evaluate("() => (typeof KGP_WATCH === 'object') ? KGP_WATCH : null")
        b.close()
    print(f"[{TAG}] 로드: {t0}")
    print(f"[{TAG}] 30장 추가+전체 선택: {t1}")
    print(f"[{TAG}] watch: {diag}")


if __name__ == "__main__":
    main()
