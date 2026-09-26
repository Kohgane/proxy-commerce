"""F49-T 3부 캡처 — 같은 스크립트를 main 워크트리(before)와 작업 트리(after)에서 돌린다.

⚠️ 페이지는 **합성 구조 페이지**다(tests/test_f49t3_taobao_list_cards.py `_synthetic_page` — 오너 진단 실측
속성만 옮김). 오너 진단 파일(world.taobao.com 스냅샷)이 레포에 없어서다 — 커밋되면 그 파일로 다시 찍는다.
확장 코드는 **그 트리의 실코드**(ISOLATED content_scripts 전부)다.

사용: python scripts/_devshot_f49t3.py <before|after> <out_dir>
"""
import json
import os
import sys

TAG, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.getcwd())
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def main():
    from pathlib import Path
    from playwright.sync_api import sync_playwright
    sys.path.insert(0, "/tmp/wt_f3")
    from tests.test_f49t3_taobao_list_cards import _synthetic_page, _stub
    ext = Path("extensions/chrome-collector")
    mf = json.loads((ext / "manifest.json").read_text(encoding="utf-8"))
    code = ";\n".join((ext / j).read_text(encoding="utf-8") for cs in mf["content_scripts"]
                      if (cs.get("world") or "ISOLATED") == "ISOLATED" for j in cs["js"])
    body = _synthetic_page().replace("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'/%3E",
                                     "data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Crect width='240' height='240' fill='%23e8e2d6'/%3E%3C/svg%3E")
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=CHROME)
        page = b.new_context(viewport={"width": 1340, "height": 900}).new_page()
        page.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
                   if r.request.resource_type == "document" else r.abort())
        page.goto("https://world.taobao.com/", wait_until="domcontentloaded")
        page.evaluate(_stub())
        page.evaluate(code)
        page.wait_for_timeout(1500)
        stat = page.evaluate("""() => ({cards: kgpFindCards().length,
            quick: document.querySelectorAll('.kgp-card-quick').length,
            feed_quick: document.querySelectorAll('.feed .kgp-card-quick').length,
            saved_quick: document.querySelectorAll('.mytao .kgp-card-quick').length,
            rest: (document.querySelector('.feed .kgp-card-quick') ? getComputedStyle(document.querySelector('.feed .kgp-card-quick')).opacity : null)})""")
        print(f"[{TAG}]", json.dumps(stat, ensure_ascii=False))
        rect = "(s) => { const r = document.querySelector(s).getBoundingClientRect(); return {x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height}; }"
        box = page.evaluate(rect, ".feed")
        page.screenshot(path=f"{OUT}/f49t3-list-{TAG}.png", full_page=True,
                        clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": min(box["height"], 560)})
        page.hover(".feed a.item-link >> nth=1")
        page.wait_for_timeout(400)
        a = page.evaluate(rect, ".feed-cell:nth-child(1)")
        c = page.evaluate(rect, ".feed-cell:nth-child(3)")
        page.screenshot(path=f"{OUT}/f49t3-hover-{TAG}.png", full_page=True,
                        clip={"x": a["x"], "y": a["y"], "width": c["x"] + c["width"] - a["x"], "height": a["height"]})
        b.close()


if __name__ == "__main__":
    main()
