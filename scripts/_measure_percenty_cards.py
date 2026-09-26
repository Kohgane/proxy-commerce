"""F49-T 2부 ⑥ — 타 확장(퍼센티) 삽입 노드가 우리 카드 탐지를 망치는가 — **측정만**.

레포 진단 스냅샷(실페이지 DOM, 퍼센티 확장 켠 상태로 저장된 것)을 **원래 호스트 주소**로 서빙하고,
실제 kgp-sources.js · kgp-extractor.js · kgp-detect.js · content_script.js를 그대로 싣는다(chrome API만 목).
같은 페이지에서 ① 그대로 ② 퍼센티 노드(「퍼센티 수집」 버튼·플로팅 버튼)를 걷어낸 뒤 kgpFindCards()를 비교.
"""
import glob
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path("/home/user/proxy-commerce")
EXT = ROOT / "extensions/chrome-collector"
D = ROOT / "fixtures/realpages/diag"
CASES = [
    ("amazon-search", "kgp-snapshot-www-amazon-com-s-k-ultraslim-phone-grip-crid-3T81T8A1LNTXL-s.html",
     "https://www.amazon.com/s?k=ultraslim+phone+grip"),
    ("aliexpress-list", "kgp-snapshot-ko-aliexpress-com-w-wholesale-craighill-summit-2525252dcard-.html",
     "https://ko.aliexpress.com/w/wholesale-craighill-summit.html"),
    ("temu-list", "kgp-snapshot-www-temu-com-kr-EC-83-88-EB-A1-9C-EC-9A-B4-ED-8A-B8-EB-A0-8C.html",
     "https://www.temu.com/kr/search_result.html"),
]
STUB = """
window.chrome = {runtime: {id: 'x', sendMessage: function(){}, onMessage: {addListener: function(){}},
  getManifest: function(){ return {version: 'measure'}; }, getURL: function(p){ return p; }},
  storage: {local: {get: function(k, cb){ cb && cb({}); }, set: function(){}},
            sync: {get: function(k, cb){ cb && cb({}); }, set: function(){}},
            onChanged: {addListener: function(){}}}};
"""
STRIP = """() => {
  let n = 0;
  document.querySelectorAll('button, div, span, a').forEach(el => {
    if (!el.isConnected) return;
    const own = (el.id || '') + ' ' + (typeof el.className === 'string' ? el.className : '');
    if (/percenty/i.test(own)) { el.remove(); n++; return; }
    if (el.tagName === 'BUTTON' && /퍼센티 수집/.test(el.textContent || '')) {
      const box = el.parentElement && el.parentElement.children.length === 1 ? el.parentElement : el;
      box.remove(); n++;
    }
  });
  return n;
}"""
COUNT = """() => {
  const cards = (typeof kgpFindCards === 'function') ? kgpFindCards() : null;
  if (!cards) return {error: 'kgpFindCards 없음'};
  const polluted = cards.filter(c => /퍼센티/.test((c.title || '') + ' ' + (c.image || ''))).length;
  return {cards: cards.length, polluted_titles: polluted,
          sample: cards.slice(0, 3).map(c => (c.title || '').slice(0, 40)),
          percenty_buttons_on_page: Array.from(document.querySelectorAll('button')).filter(b => /퍼센티 수집/.test(b.textContent||'')).length};
}"""


def main():
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    js = [(EXT / n).read_text(encoding="utf-8") for n in ("kgp-sources.js", "kgp-extractor.js", "kgp-detect.js", "content_script.js")]
    out = []
    with sync_playwright() as p:
        br = p.chromium.launch(**({"executable_path": hits[0]} if hits else {}))
        for name, fname, url in CASES:
            html = (D / fname).read_text(encoding="utf-8", errors="ignore")
            row = {"case": name}
            for mode in ("as_is", "percenty_removed"):
                pg = br.new_page(viewport={"width": 1400, "height": 1000})
                def _handler(route, request, _h=html):
                    if request.resource_type == "document":
                        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=_h)
                    else:
                        route.abort()
                pg.route("**/*", _handler)
                pg.add_init_script(STUB)
                pg.goto(url, wait_until="domcontentloaded")
                removed = pg.evaluate(STRIP) if mode == "percenty_removed" else 0
                for code in js:
                    try:
                        pg.add_script_tag(content=code)
                    except Exception as exc:
                        row.setdefault("inject_errors", []).append(f"{type(exc).__name__}: {str(exc)[:120]}")
                pg.wait_for_timeout(300)
                try:
                    r = pg.evaluate(COUNT)
                except Exception as exc:
                    r = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
                r["removed_nodes"] = removed
                row[mode] = r
                pg.close()
            out.append(row)
        br.close()
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
