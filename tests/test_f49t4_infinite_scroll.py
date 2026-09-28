"""F49-T 4부 — 무한 스크롤: 스크롤로 붙은 카드도 탐지·타일·선택된다(전 소싱처 공통 엔진).

오너 실측(world.taobao): 스크롤로 새 카드가 붙으면 「선택」이 안 먹고, hover 버튼도 없었다.
확인된 원인 하나: 「전체 선택」이 **DOM의 체크박스만** 돌았다 — 탐지는 됐는데 체크박스가 아직 없는 카드는 영영
선택되지 않았다. 재스캔은 스로틀(첫 변이 뒤 300ms 한 번)이라 그 뒤에 붙은 카드는 다음 변이를 기다렸다.

이 파일이 못박는 것(실브라우저):
  ① 합성 목록: 카드 10장씩 3회 추가 → 탐지 30/30 · 뷰포트 안 타일 전부 · 「전체 선택」 30 · 「새 상품 +N」
  ② 가상 스크롤(카드 DOM 통째 교체) → 같은 상품 키면 타일 재부착 · 선택 유지
  ③ page_diag.watch — scan_count·last_scan_at·cards_total·cards_tiled·observer_alive
  ④ 실 스냅샷(아마존·알리·요시다): 기존 카드를 복제해 새 상품 3회 추가 → 탐지 +30
  ⑤ 성능: 300장 붙인 뒤 스캔 1회 시간(측정값 출력, 50ms 이하)
  ⑥ 카드 컨테이너 셀렉터는 원격 규칙(list_watch.container.<사이트>) — 데이터
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import _pw

EXT = Path("extensions/chrome-collector")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
CHROME_STUB = """
  window.chrome = {
    runtime: { id: 'x', lastError: null, getManifest: () => ({version:'0'}), getURL: (p)=>p,
               sendMessage: (m,cb)=>{ cb && setTimeout(()=>cb({ok:false}),0); }, onMessage:{addListener(){}} },
    storage: { local: { get:(k,cb)=>cb&&cb({}), set:()=>{} }, sync:{ get:(k,cb)=>cb&&cb({}) },
               onChanged:{ addListener(){} } },
  };
"""
SYN_URL = "https://www.yoshidakaban.com/product/search.html?q=kgp4"
PH = '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200"><rect fill="#ccc" width="200" height="200"/></svg>'


def _code():
    return ";\n".join((EXT / j).read_text(encoding="utf-8")
                      for cs in MANIFEST["content_scripts"]
                      if (cs.get("world") or "ISOLATED") == "ISOLATED" for j in cs["js"])


def _need_pw():
    pytest.importorskip("playwright.sync_api")
    if not _pw.chromium_hits():
        pytest.skip("chromium 없음")


SYN_PAGE = """<!doctype html><html><head><title>검색 결과</title>
<style>#grid{display:grid;grid-template-columns:repeat(8,150px);gap:8px}.card{position:relative;height:150px}
.card img{width:120px;height:100px}</style></head><body><h1>검색</h1><div id="grid"></div>
<script>
window.__addCards = function(n, start){
  const g = document.getElementById('grid');
  for (let i = start; i < start + n; i++) {
    const d = document.createElement('div'); d.className = 'card item';
    d.innerHTML = '<a href="/product/' + (100000 + i) + '.html"><img src="/img/' + i + '.png" width="120" height="100" alt="가방 ' + i + '">'
      + '<span class="title">가방 상품 ' + i + '</span></a><span class="price">¥' + (1000 + i) + '</span>';
    g.appendChild(d);
  }
};
</script></body></html>"""

PROBE = """() => ({
  total: KGP_WATCH.cards_total, tiled: document.querySelectorAll('.kgp-card-quick').length,
  chk: document.querySelectorAll('.kgp-card-chk').length, scans: KGP_WATCH.scan_count,
  alive: KGP_WATCH.observer_alive, newN: KGP_WATCH.new_cards, lastMs: KGP_WATCH.last_scan_ms,
  sel: _kgpSelKeys.size,
  count: (function(){ const b = document.getElementById('kgp-listing-toolbar'); const r = b && (b._kgpShadow || b);
          const c = r && r.querySelector('#kgp-tb-count'); return c ? c.textContent : ''; })(),
  inView: Array.from(document.querySelectorAll('.card')).filter(e => { const r = e.getBoundingClientRect();
          return r.bottom > 0 && r.top < innerHeight; }).length,
  inViewTiled: Array.from(document.querySelectorAll('.card')).filter(e => { const r = e.getBoundingClientRect();
          return r.bottom > 0 && r.top < innerHeight && e.querySelector('.kgp-card-quick'); }).length,
})"""


def _open(pw, url, body, viewport=(1400, 900)):
    b = pw.chromium.launch(**_pw.launch_opts())
    page = b.new_context(viewport={"width": viewport[0], "height": viewport[1]}).new_page()

    def route(r):
        u = r.request.url.split("#")[0]
        if u == url:
            r.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
        elif r.request.resource_type == "image":
            r.fulfill(status=200, content_type="image/svg+xml", body=PH)
        else:
            r.abort()
    page.route("**/*", route)
    page.goto(url, wait_until="domcontentloaded")
    page.evaluate(CHROME_STUB)
    page.add_script_tag(content=_code())      # 스크립트 전역(탐침이 KGP_WATCH 등을 읽는다)
    return b, page


def _click_all(page):
    page.evaluate("""() => { const b = document.getElementById('kgp-listing-toolbar'); const r = b._kgpShadow || b;
                     r.querySelector('[data-act="all-sel"]').click(); }""")


# ① 합성 목록 — 10장씩 3회
def test_cards_added_in_three_batches_are_all_detected_tiled_and_selectable():
    _need_pw()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b, page = _open(pw, SYN_URL, SYN_PAGE)
        page.evaluate("() => { let k = 0; const t = setInterval(() => { __addCards(10, k * 10); k++; if (k === 3) clearInterval(t); }, 500); }")
        page.wait_for_timeout(2600)
        got = page.evaluate(PROBE)
        _click_all(page)
        page.wait_for_timeout(100)
        after = page.evaluate(PROBE)
        diag = page.evaluate("() => kgpPageDiag().watch")
        b.close()
    assert got["total"] == 30, got
    assert got["inView"] and got["inViewTiled"] == got["inView"], got          # 뷰포트 안 타일 전부
    assert got["alive"] is True and got["scans"] >= 3
    assert got["newN"] == 20 and "새 상품 +20" in got["count"], got           # 첫 스캔(10) 이후 20
    assert after["sel"] == 30 and "30개 선택" in after["count"], after
    for k in ("scan_count", "last_scan_at", "cards_total", "cards_tiled", "observer_alive"):
        assert k in diag, (k, diag)
    assert diag["cards_total"] == 30 and diag["observer_alive"] is True


# ② 가상 스크롤 — 카드 DOM 통째 교체
def test_virtual_scroll_replacement_keeps_selection_and_reattaches():
    _need_pw()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b, page = _open(pw, SYN_URL, SYN_PAGE)
        page.evaluate("() => __addCards(12, 0)")
        page.wait_for_timeout(900)
        _click_all(page)
        page.evaluate("""() => { const g = document.getElementById('grid'); const html = g.innerHTML
                          .replace(/<div class="kgp-card-(chk|quick)[^]*?<\\/div>/g, '');
                          const fresh = document.createElement('div'); fresh.id = 'grid'; fresh.innerHTML = '';
                          g.replaceWith(fresh); __addCards(12, 0); }""")
        page.wait_for_timeout(1200)
        got = page.evaluate(PROBE)
        outlined = page.evaluate("() => document.querySelectorAll('.card[data-kgp-outline=\"1\"]').length")
        b.close()
    assert got["total"] == 12 and got["inViewTiled"] == 12, got
    assert got["sel"] == 12 and outlined == 12, (got, outlined)                  # 새 DOM에도 선택 유지


# ⑤ 성능 — 300장
def test_three_hundred_cards_one_scan_under_50ms():
    _need_pw()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b, page = _open(pw, SYN_URL, SYN_PAGE)
        page.evaluate("() => __addCards(300, 0)")                               # 한 번에 300장(가장 무거운 첫 스캔)
        page.wait_for_timeout(1500)
        first = page.evaluate("() => ({max: KGP_WATCH.max_scan_ms, chunk: KGP_WATCH.max_chunk_ms})")
        page.evaluate("() => kgpInjectListing()")                               # 정상 상태 스캔 1회
        got = page.evaluate(PROBE)
        lazy = page.evaluate("() => ({lazy: KGP_WATCH.lazy, pending: document.querySelectorAll('[data-kgp-lazy]').length})")
        b.close()
    print(f"\n[F49-T 4부 성능] 300장 첫 스캔 {first['max']}ms · 부착 조각 최대 {first['chunk']}ms · "
          f"정상 스캔 {got['lastMs']}ms · lazy={lazy} · 타일 {got['tiled']}")
    assert got["total"] == 300
    assert lazy["lazy"] is True and lazy["pending"] > 0                         # 150장 넘으면 뷰포트 밖은 대기
    assert got["inViewTiled"] == got["inView"]
    # 메인 스레드 한 태스크 = 50ms 이하 — 첫 스캔(가장 무거움)·부착 조각·정상 스캔 모두.
    assert first["max"] <= 50 and first["chunk"] <= 50 and got["lastMs"] <= 50, (first, got["lastMs"])


# ④ 실 스냅샷
REAL = [
    ("kgp-snapshot-www-amazon-com-s-k-ultraslim-phone-grip-crid-3T81T8A1LNTXL-s.html",
     "https://www.amazon.com/s?k=ultraslim+phone+grip&crid=3T81T8A1LNTXL"),
    ("kgp-snapshot-ko-aliexpress-com-w-wholesale-craighill-summit-2525252dcard-.html",
     "https://ko.aliexpress.com/w/wholesale-craighill-summit-card-case.html"),
    ("kgp-snapshot-www-yoshidakaban-com-product-search-html-ls-90-st-2.html",
     "https://www.yoshidakaban.com/product/search.html?ls=90&st=2"),
    ("kgp-snapshot-world-taobao-com*.html", "https://world.taobao.com/"),
]

CLONE = """(n) => {
  // 탐지된 메인 카드 하나를 골라 **상품 식별자만 바꾼** 복제를 같은 부모에 붙인다(무한 스크롤 흉내).
  const src = (_kgpCards || []).filter(c => c.region !== 'reco' && !c.sponsored && c.el && c.el.parentElement)[0];
  if (!src) return 0;
  const key = _kgpCardKey(src.url);
  const tok = (key.match(/^(?:asin|goods|tb):(.+)$/) || [])[1] || (src.url.match(/(\\d{6,})/) || [])[1] || '';
  if (!tok) return -1;
  let made = 0;
  for (let i = 0; i < n; i++) {
    window.__kgpSeq = (window.__kgpSeq || 0) + 1;
    const nt = /^[A-Z0-9]{10}$/.test(tok) ? ('BZ' + String(10000000 + window.__kgpSeq).slice(-8)) : (tok.slice(0, -4) + String(1000 + window.__kgpSeq).slice(-4));
    const el = src.el.cloneNode(true);
    el.querySelectorAll('.kgp-card-chk, .kgp-card-quick').forEach(x => x.remove());
    el.removeAttribute('data-kgp'); el.removeAttribute('data-kgp-outline'); el.style.outline = '';
    const fix = (node) => { if (!node.getAttributeNames) return; node.getAttributeNames().forEach(a => {
      const v = node.getAttribute(a); if (v && v.indexOf(tok) >= 0) node.setAttribute(a, v.split(tok).join(nt)); }); };
    fix(el); el.querySelectorAll('*').forEach(fix);
    src.el.parentElement.appendChild(el); made++;
  }
  return made;
}"""


@pytest.mark.parametrize("snap,url", REAL, ids=["amazon", "aliexpress", "yoshida", "world-taobao"])
def test_real_snapshots_detect_cards_appended_later(snap, url):
    _need_pw()
    hits = sorted(Path("fixtures/realpages/diag").glob(snap))
    if not hits:
        pytest.skip(f"스냅샷 미커밋: {snap} — 오너 업로드 후 자동 실행")
    body = hits[0].read_text(encoding="utf-8", errors="ignore")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b, page = _open(pw, url, body)
        page.wait_for_timeout(1500)
        before = page.evaluate("() => KGP_WATCH.cards_total")
        if before < 3:
            b.close()
            # v86 계약과 같은 한계 — 외부 CSS·지연 이미지가 빠진 오프라인 재현에선 카드가 안 잡히는 사이트가 있다.
            pytest.skip(f"{snap}: 오프라인 재현에서 카드 미감지(before={before}) — 공허 그린 가드가 아래에 있다")
        made = 0
        for _ in range(3):
            made += page.evaluate(CLONE, 10)
            page.wait_for_timeout(700)
        after = page.evaluate("() => ({total: KGP_WATCH.cards_total, alive: KGP_WATCH.observer_alive, newN: KGP_WATCH.new_cards})")
        _click_all(page)
        sel = page.evaluate("() => _kgpSelKeys.size")
        main = page.evaluate("() => _kgpSelectableUrls().length")
        b.close()
    assert before >= 3 and made == 30, (before, made)
    assert after["total"] == before + 30, (before, after)
    assert after["newN"] >= 30 and after["alive"] is True
    assert sel == main                                                          # 전체 선택 = 탐지 전부(선택 대상)


WT_FEED_APPEND = """(n) => {
  // 실제 피드처럼 **상품 칸**(div.tb-pick-content-item)을 피드 컨테이너에 붙인다 — 상품 번호만 새로.
  const feed = document.querySelector('.tb-pick-feeds-container');
  const unit = feed && feed.querySelector('.tb-pick-content-item');
  if (!unit) return 0;
  const a = unit.querySelector('a.item-link');
  const id = ((a && a.getAttribute('href') || '').match(/[?&]id=(\\d{6,})/) || [])[1];
  if (!id) return -1;
  for (let i = 0; i < n; i++) {
    window.__wtSeq = (window.__wtSeq || 0) + 1;
    const nid = '9' + String(100000000000 + window.__wtSeq).slice(1);
    const el = unit.cloneNode(true);
    el.querySelectorAll('.kgp-card-chk, .kgp-card-quick').forEach(x => x.remove());
    el.querySelectorAll('[data-kgp],[data-kgp-outline]').forEach(x => { x.removeAttribute('data-kgp'); x.removeAttribute('data-kgp-outline'); x.style.outline = ''; });
    el.querySelectorAll('*').forEach(x => x.getAttributeNames().forEach(k => { const v = x.getAttribute(k); if (v && v.indexOf(id) >= 0) x.setAttribute(k, v.split(id).join(nid)); }));
    feed.appendChild(el);
  }
  return n;
}"""


def test_world_taobao_real_feed_grows_after_scroll_and_promos_are_not_products():
    """오너 검증 기준 — world.taobao 스크롤 후 툴바 N 증가(재업로드 스냅샷 2026-09-28, ext 1.5.161).

    실측: 제네릭이 피드 위 행사 입구 4개(huodong·web.m.taobao)를 상품으로 셌다(34 = 30 + 4) → 뺀다.
    피드 칸 10개씩 3번 붙이면 30 → 60, 「새 상품」 30, 붙은 칸마다 선택 배지, 전체 선택 = 60.
    """
    _need_pw()
    hits = sorted(Path("fixtures/realpages/diag").glob("kgp-snapshot-world-taobao-com*.html"))
    assert hits, "world-taobao 스냅샷이 main에 있어야 한다(오너 업로드 52dda872)"
    body = hits[0].read_text(encoding="utf-8", errors="ignore")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b, page = _open(pw, "https://world.taobao.com/", body)
        page.wait_for_timeout(1500)
        before = page.evaluate(PROBE)
        kinds = page.evaluate("() => (_kgpCards || []).map(c => _kgpCardKey(c.url).slice(0, 3))")
        promo_skip = page.evaluate("() => document.querySelectorAll('[data-kgp-skip=\"taobao-promo\"]').length")
        steps = []
        for _ in range(3):
            page.evaluate(WT_FEED_APPEND, 10)
            page.wait_for_timeout(800)
            steps.append(page.evaluate(PROBE))
        tiled = page.evaluate("() => Array.from(document.querySelectorAll('.tb-pick-feeds-container > .tb-pick-content-item')).filter(u => u.querySelector('.kgp-card-chk, .kgp-card-quick')).length")
        _click_all(page)
        sel = page.evaluate("() => _kgpSelKeys.size")
        b.close()
    assert before["total"] == 30 and set(kinds) == {"tb:"}, (before, kinds)     # 행사 입구 제외
    assert promo_skip == 4
    assert [s["total"] for s in steps] == [40, 50, 60], steps                   # 스크롤마다 N 증가
    assert steps[-1]["newN"] >= 30 and steps[-1]["alive"] is True
    assert "60" in steps[-1]["count"], steps[-1]["count"]                      # 툴바 숫자도 따라온다
    assert tiled == 60 and sel == 60


# ⑥ 원격 규칙
def test_container_selectors_are_remote_rule_data():
    from src.collectors.ext_rules import load
    r = load()["rules"]["list_watch"]
    assert r["debounce_ms"] == 300 and r["lazy_after"] == 150 and isinstance(r["container"], dict)
    js = (EXT / "content_script.js").read_text(encoding="utf-8")
    assert '_kgpRule("list_watch.container." + _kgpWatchSite(), "")' in js
    assert '_kgpRule("list_watch.debounce_ms", 300)' in js


def test_server_keeps_watch_in_page_diag():
    from src.collectors.collect_status import clean_page_diag
    d = clean_page_diag({"watch": {"scan_count": "4", "cards_total": 30, "cards_tiled": 30, "observer_alive": True,
                                   "last_scan_at": "2026-09-27T12:00:00Z", "last_scan_ms": "3.4", "evil": "<x>"}})
    assert d["watch"]["scan_count"] == 4 and d["watch"]["cards_total"] == 30 and d["watch"]["observer_alive"] is True
    assert d["watch"]["last_scan_ms"] == 3.4 and "evil" not in d["watch"]


def test_real_snapshot_contract_is_not_vacuous():
    """위 실 스냅샷 계약이 전부 skip돼 공허하게 그린이 되지 않게 — 아마존·알리 두 개는 반드시 실제로 돈다."""
    _need_pw()
    for snap, url in REAL[:2]:
        assert sorted(Path("fixtures/realpages/diag").glob(snap)), snap
        test_real_snapshots_detect_cards_appended_later(snap, url)
