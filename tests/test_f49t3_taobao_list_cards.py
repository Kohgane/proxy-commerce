"""F49-T 3부 — 타오바오 목록(world.taobao.com) 카드별 「고가 수집」 버튼 계약.

오너 진단 실측(ext 1.5.152, 2026-09-26 09:40Z, world.taobao.com):
- 피드 카드 30장 = `a.item-link`(class tb-pick-content-item · item-appear), href = item.taobao.com | detail.tmall.com
  `/item.htm?id=`. 우리 탐지는 제네릭 4장 = `mytao-collectitem`(내 찜 블록)뿐 · 피드 카드 0/30 · no-url 7 · dup 4.
- 타일 `host_opacity` 0 — 호버 뒤에도 "0". 퍼센티 버튼은 30장 전부에 있었다.

두 층으로 잰다:
① **진단 파일 그대로**(오너 지시 7) — `fixtures/realpages/diag/kgp-snapshot-world-taobao-com*.html`.
   ⚠️ 이 세션엔 파일이 없다(레포·볼트 둘 다 없음) → **파일이 커밋되면 자동으로 켜진다**(지금은 skip, 통과로 세지 않는다).
② **구조 계약**(합성) — 위 실측 속성만 옮긴 최소 페이지. 진단 파일의 대역이 아니라 로직 검증용이다.
   셀렉터·클래스 이름은 전부 오너 실측 문장에서 왔다(발명 0).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import _pw

EXT = Path("extensions/chrome-collector")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
CS = (EXT / "content_script.js").read_text(encoding="utf-8")
EX = (EXT / "kgp-extractor.js").read_text(encoding="utf-8")
URL = "https://world.taobao.com/"
DIAG_GLOB = "kgp-snapshot-world-taobao-com*.html"


def _pw_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(_pw.chromium_hits())


needs_browser = pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")


def _stub(manifest=True):
    mf = json.dumps(MANIFEST if manifest else {"version": "0"})
    return """
  window.__kgpSent = [];
  window.__kgpReply = null;
  window.chrome = {
    runtime: { id: 'x', lastError: null, getManifest: () => (%s), getURL: (p)=>p,
               sendMessage: (m,cb)=>{ window.__kgpSent.push(m);
                 const r = (typeof window.__kgpReply === 'function') ? window.__kgpReply(m) : {ok:false};
                 cb && setTimeout(()=>cb(r),0); },
               onMessage:{addListener(){}} },
    storage: { local: { get:(k,cb)=>cb&&cb({}), set:()=>{} }, sync:{ get:(k,cb)=>cb&&cb({}) },
               onChanged:{ addListener(){} } },
  };
""" % mf


def _isolated_code():
    return ";\n".join(
        (EXT / j).read_text(encoding="utf-8")
        for cs in MANIFEST["content_scripts"]
        if (cs.get("world") or "ISOLATED") == "ISOLATED" for j in cs["js"])


# ── 구조 계약 페이지(합성) ────────────────────────────────────────────────────
#   피드 30장(타오바오 20·티몰 10) + 「내 찜」 4장 + 퍼센티가 붙이는 「퍼센티 수집」 버튼 30개.
def _synthetic_page():
    ph = "data:image/svg+xml;utf8," + "%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'/%3E"
    cards = []
    for i in range(30):
        host = "item.taobao.com" if i < 20 else "detail.tmall.com"
        gid = 700000000000 + i
        cards.append(
            f'<div class="feed-cell"><a class="item-link tb-pick-content-item item-appear" '
            f'href="//{host}/item.htm?id={gid}&spm=a21wu.1&scm=x" target="_blank">'
            f'<img src="{ph}" width="240" height="240" alt="">'
            f'<div class="info"><div class="title">卫生间置物架 {i}号 免打孔</div>'
            f'<div class="price"><span>¥</span><span>{19 + i}.90</span></div></div></a>'
            f'<div class="percenty-wrap"><button class="percenty-collect-btn">퍼센티 수집</button></div></div>')
    saved = "".join(
        f'<li class="mytao-collectitem"><a href="https://item.taobao.com/item.htm?id={600000000000 + i}">'
        f'<img src="{ph}" width="160" height="160" alt="찜한 상품 {i}"><span>찜한 상품 {i} ¥9.90</span></a></li>'
        for i in range(4))
    return ("<html><head><meta charset='utf-8'><title>淘宝 world</title>"
            "<style>.feed{display:grid;grid-template-columns:repeat(5,250px);gap:10px}"
            ".feed-cell{position:relative}a.item-link{display:block}</style></head><body>"
            f"<ul class='mytao'>{saved}</ul><div class='feed'>{''.join(cards)}</div></body></html>")


def _open(body, url=URL, manifest=True, pre=None, hover=False):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(**_pw.launch_opts())
        page = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()

        def route(r):
            if r.request.resource_type == "document":
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
            else:
                r.abort()
        page.route("**/*", route)
        page.goto(url, wait_until="domcontentloaded")
        page.evaluate(_stub(manifest))
        if pre:
            page.evaluate(pre)
        page.evaluate(_isolated_code())
        page.wait_for_timeout(1500)
        out = PROBE(page, hover)
        b.close()
    return out


def PROBE(page, hover):
    got = page.evaluate("""() => {
      const cards = kgpFindCards();
      const q = document.querySelectorAll('.kgp-card-quick');
      const first = q[0];
      const cs = first ? getComputedStyle(first) : null;
      const fr = first ? first.getBoundingClientRect() : null;
      const host = first ? first.parentElement.getBoundingClientRect() : null;
      return {
        n: cards.length,
        urls: cards.map(c => c.url),
        currencies: Array.from(new Set(cards.map(c => c.currency))),
        saved_in: cards.filter(c => c.el.closest('.mytao-collectitem')).length,
        percenty_in: cards.filter(c => /퍼센티/.test(c.title)).length,
        skip_saved: document.querySelectorAll('[data-kgp-skip="mytao-saved"]').length,
        quick_n: q.length,
        rest_opacity: cs ? parseFloat(cs.opacity) : null,
        label: first && first._kgpLbl ? first._kgpLbl.textContent : null,
        top_right: fr && host ? (Math.abs(fr.right - host.right) < 40 && Math.abs(fr.top - host.top) < 40) : null,
      };
    }""")
    if hover:
        page.hover("a.item-link >> nth=0")
        page.wait_for_timeout(400)
        got["hover_opacity"] = page.evaluate(
            "() => parseFloat(getComputedStyle(document.querySelector('.kgp-card-quick')).opacity)")
    return got


# ── ② 구조 계약 ─────────────────────────────────────────────────────────────

@needs_browser
def test_feed_cards_are_detected_30_of_30_and_saved_block_is_excluded():
    got = _open(_synthetic_page())
    assert got["n"] == 30, got
    assert got["saved_in"] == 0 and got["skip_saved"] >= 4, "「내 찜」 블록이 피드에 섞였다"
    assert got["percenty_in"] == 0, "퍼센티 노드를 상품 제목으로 읽었다"
    # 상품 주소는 id만 남긴 정규 모양(추적 쿼리 제거) — 서버 vendor_sku가 같은 id를 읽는다.
    assert all(u.startswith("https://item.taobao.com/item.htm?id=") or
               u.startswith("https://detail.tmall.com/item.htm?id=") for u in got["urls"])
    assert all("spm=" not in u for u in got["urls"])
    assert got["currencies"] == ["CNY"], "¥가 JPY로 저장된다(타오바오 = 위안)"


@needs_browser
def test_tile_is_visible_at_rest_small_top_right_and_opaque_on_hover():
    got = _open(_synthetic_page(), hover=True)
    assert got["quick_n"] == 30
    assert got["rest_opacity"] and got["rest_opacity"] > 0, "평소 host_opacity 0 — 호버 전이가 안 끝나면 영영 안 보인다"
    assert got["rest_opacity"] < 1, "평소엔 반투명이어야 한다"
    assert got["label"] == "고가 수집"
    assert got["top_right"] is True, "카드 우상단이 아니다"
    assert got["hover_opacity"] == 1


@needs_browser
def test_percenty_nodes_do_not_change_our_count():
    strip = "() => document.querySelectorAll('.percenty-wrap').forEach(n => n.remove())"
    with_p = _open(_synthetic_page())
    without_p = _open(_synthetic_page(), pre=strip)
    assert with_p["n"] == without_p["n"] == 30


@needs_browser
def test_click_collects_that_card_and_toasts_a_draft_link():
    from playwright.sync_api import sync_playwright
    reply = """() => { window.__kgpReply = (m) => m.action === 'collectBulk'
        ? {ok:true, success:1, failed:0, duplicate:0, total:1,
           enrichTargets:[{item_id:'it-777', url:m.items[0].url}]} : {ok:true}; }"""
    with sync_playwright() as pw:
        b = pw.chromium.launch(**_pw.launch_opts())
        page = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
        body = _synthetic_page()
        page.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
                   if r.request.resource_type == "document" else r.abort())
        page.goto(URL, wait_until="domcontentloaded")
        page.evaluate(_stub())
        page.evaluate(reply)
        page.evaluate(_isolated_code())
        page.wait_for_timeout(1500)
        page.evaluate("() => { window.__opened = []; window.open = (u) => { window.__opened.push(u); }; }")
        page.evaluate("() => document.querySelectorAll('.kgp-card-quick')[3].click()")
        page.wait_for_timeout(500)
        got = page.evaluate("""() => {
          const sent = window.__kgpSent.filter(m => m.action === 'collectBulk');
          const card = document.getElementById('kgp-collect-card');
          const btns = card ? Array.from(card.querySelectorAll('button')).map(b => b.textContent) : [];
          const q = document.querySelectorAll('.kgp-card-quick')[3];
          return { sent: sent.map(m => m.items.map(i => ({url: i.url, currency: i.currency}))),
                   enrich: window.__kgpSent.filter(m => m.action === 'enrichStart').length,
                   card_msg: card ? card.querySelector('.kgp-cc-msg').textContent : '',
                   btns, collected: q.dataset.collected, label: q._kgpLbl.textContent };
        }""")
        page.evaluate("""() => { const card = document.getElementById('kgp-collect-card');
          Array.from(card.querySelectorAll('button')).find(b => /초안 열기/.test(b.textContent)).click(); }""")
        opened = page.evaluate("() => window.__opened")
        b.close()
    assert got["sent"] == [[{"url": "https://item.taobao.com/item.htm?id=700000000003", "currency": "CNY"}]]
    assert got["enrich"] == 1, "상세(ICE) 보강 큐에 안 올렸다"
    assert "초안을 만들었어요" in got["card_msg"] and any("초안 열기" in t for t in got["btns"])
    assert got["collected"] == "1" and got["label"] == "수집됨 ✓"
    assert opened and opened[0].endswith("/seller/collect/preview/it-777")


@needs_browser
def test_other_sites_keep_rest_zero():
    """v86-C(rest 0)는 타오바오 밖에선 그대로 — 전역 확대는 오너 결정."""
    import re
    body = re.sub(r'//(item\.taobao|detail\.tmall)\.com/item\.htm\?id=(\d+)[^"]*',
                  r'https://www.yoshidakaban.com/product/\2.html', _synthetic_page())
    got = _open(body, url="https://www.yoshidakaban.com/product/search.html")
    assert got["quick_n"] > 0 and got["rest_opacity"] == 0


# ── 진단: 오류 한 줄 · tier1 원인 ─────────────────────────────────────────────

@needs_browser
def test_page_errors_keep_message_location_and_resource_kind():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(**_pw.launch_opts())
        page = b.new_context().new_page()
        page.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html", body="<p>x</p>")
                   if r.request.resource_type == "document" else r.abort())
        page.goto(URL)
        page.evaluate(_stub())
        page.evaluate(_isolated_code())
        page.evaluate("""() => {
          const e = new Error('boom here');
          window.dispatchEvent(new ErrorEvent('error', {message: 'Uncaught Error: boom here', filename: 'https://g.alicdn.com/a.js', lineno: 12, colno: 3, error: e}));
          const img = document.createElement('img'); document.body.appendChild(img);
          img.dispatchEvent(new Event('error'));
        }""")
        errs = page.evaluate("() => kgpPageDiag().errors")
        b.close()
    assert errs[0].startswith("script: Uncaught Error: boom here @ https://g.alicdn.com/a.js:12:3")
    assert "stack:" in errs[0]
    assert errs[1].startswith("resource: <img>")
    assert all(e != "error" for e in errs)


@needs_browser
def test_tier1_cause_says_not_a_target_on_taobao_not_reload():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(**_pw.launch_opts())
        page = b.new_context().new_page()
        page.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html", body="<p>x</p>")
                   if r.request.resource_type == "document" else r.abort())
        page.goto(URL)
        page.evaluate(_stub())
        page.evaluate(_isolated_code())
        tb = page.evaluate("() => _kgpTier1Cause({netBound:false})")
        temu = page.evaluate("() => _kgpNetRegistered('www.temu.com')")
        dead = page.evaluate("() => { chrome.runtime.id = undefined; return _kgpTier1Cause({netBound:false}); }")
        b.close()
    assert tb.startswith("인터셉터 대상 아님"), tb
    assert "재로딩" not in tb
    assert temu is True
    assert dead.startswith("확장이 갱신됐는데 이 탭을 새로고침하지 않음")


# ── 통화: 상세(추출기) — 위안 도메인에서 ¥는 경고 대상이 아니다 ───────────────────

@needs_browser
def test_yen_sign_on_tmall_detail_is_cny_without_mismatch_warning():
    from playwright.sync_api import sync_playwright
    html = ("<html><head><title>商品</title></head><body><h1>卫生间置物架</h1>"
            "<div class='price'>¥175.50</div></body></html>")
    with sync_playwright() as pw:
        b = pw.chromium.launch(**_pw.launch_opts())
        page = b.new_context().new_page()
        page.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
                   if r.request.resource_type == "document" else r.abort())
        page.goto("https://detail.tmall.com/item.htm?id=617129397971")
        page.add_script_tag(content=EX)
        out = page.evaluate("() => window.kgpExtractProduct({pageType:'single'})")
        b.close()
    assert out["currency"] == "CNY"
    assert not any("표시 통화" in w for w in out["warnings"]), out["warnings"]


# ── 서버: 목록 수집 → 상세 보강에 SKU가 실린다 · vendor_sku가 같은 id를 읽는다 ─────────

def test_enrich_body_carries_skus_source():
    bg = (EXT / "background.js").read_text(encoding="utf-8")
    body = bg.split("function _kgpEnrichBody")[1].split("\n}\n")[0]
    assert "skus: meta.skus" in body and "field_sources" in body


def test_enrich_fills_skus_once(monkeypatch):
    import src.api.extension_api as ext
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    seller = "u-f49t3"
    monkeypatch.setattr(ext, "_require_token", lambda scopes=None: {"user_id": seller})
    iid = S.append(url="https://item.taobao.com/item.htm?id=700000000003", title="卫生间置物架",
                   price="22.90", currency="CNY", source="extension", seller_id=seller,
                   extra={"mode": "simple", "images": ["https://img.alicdn.com/a.jpg"]})
    iid = iid[0] if isinstance(iid, tuple) else iid
    skus = [{"spec": ["白"], "sku_id": "1", "price": "22.90", "currency": "CNY", "stock": 5}]
    with app.test_client() as c:
        d = c.post("/api/v1/collect/enrich", json={"item_id": iid, "skus": skus,
                                                    "field_sources": {"sku": "ice_context"}}).get_json()
        again = c.post("/api/v1/collect/enrich", json={"item_id": iid, "skus": skus + skus}).get_json()
    assert d["ok"] and again["ok"]
    ex = json.loads(S.get(iid, seller_ids={seller})["extra_json"])
    assert [k["sku_id"] for k in ex["skus"]] == ["1"]                    # fill-only(두 번째는 덮지 않음)
    assert ex["field_sources"]["sku"] == "ice_context"


def test_vendor_sku_reads_the_same_id_from_card_urls():
    from src.collectors.product_key import vendor_sku
    assert vendor_sku("https://item.taobao.com/item.htm?id=700000000003") == "700000000003"
    assert vendor_sku("https://detail.tmall.com/item.htm?id=700000000021") == "700000000021"


# ── ① 오너 진단 파일 그대로(커밋되면 자동으로 켜진다) ─────────────────────────────

def _diag_snapshot():
    hits = sorted(Path("fixtures/realpages/diag").glob(DIAG_GLOB))
    return hits[0] if hits else None


@needs_browser
@pytest.mark.skipif(_diag_snapshot() is None, reason=f"진단 파일 미커밋: {DIAG_GLOB} — 오너 커밋 시 자동 실행")
def test_owner_diag_snapshot_30_of_30_with_percenty_present():
    body = _diag_snapshot().read_text(encoding="utf-8", errors="ignore")
    got = _open(body)
    assert got["n"] == 30, got
    assert got["saved_in"] == 0
    assert got["quick_n"] >= 30 and got["rest_opacity"] > 0
