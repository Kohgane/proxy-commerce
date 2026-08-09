"""tests/test_v86_step5_rakuten_url.py — v86 STEP5: 라쿠텐 검색 상품 URL 해석.

증상(오너 1.5.129 진단): 라쿠텐 검색 목록에서 `skipStats {"no-item-url": 45}` — 타일이 통째로 후보에서 빠졌다.

근본: **라쿠텐 상품 URL은 경로에 `/item/`이 없다.** 호스트 자체가 `item.rakuten.co.jp`이고 경로는
`/{샵ID}/{상품코드}/`다(예: `item.rakuten.co.jp/tabemon-dikara/20072/?variantId=20072`).
`_kgpIsProductHref`의 기존 패턴은 전부 '경로에 /item/·/dp/·/goods/…'를 전제해서 라쿠텐만 통째로 탈락했다.

수리: 호스트가 item.rakuten.co.jp이고 **경로 세그먼트가 2개 이상**이면 상품 상세로 인정
(샵 최상위 `/{샵ID}/`는 세그먼트 1개라 자연히 제외 — 상품코드 형식은 샵마다 숫자·해시가 섞여 형식 기반 판정 불가).

곁가지(정직): 남은 타일 중 10여 개는 **광고 리다이렉트**(grp07.ias…/redirect_rpp)다. 목적지 URL이
타일 어디에도 없고(앵커 1개·불투명 토큰, data 속성 0 — 실측), 채택하면 normalize_product_key가 쿼리를 버려
**전부 같은 키로 붕괴**해 서로 다른 상품이 1건으로 합쳐진다. 그래서 제외하되 사유를 `ad-redirect`로 분리했다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import _pw

EXT = Path("extensions/chrome-collector")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
CS = (EXT / "content_script.js").read_text(encoding="utf-8")
_DIAG = Path("fixtures/realpages/diag")
_SNAP = "kgp-snapshot-search-rakuten-co-jp-search-mall-*.html"
_URL = "https://search.rakuten.co.jp/search/mall/x/"


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.143"


def _pw_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(_pw.chromium_hits())


CHROME_STUB = """
  window.chrome = {
    runtime: { id: 'x', lastError: null, getManifest: () => ({version:'0'}), getURL: (p)=>p,
               sendMessage: (m,cb)=>{ cb && setTimeout(()=>cb({ok:false}),0); }, onMessage:{addListener(){}} },
    storage: { local: { get:(k,cb)=>cb&&cb({}), set:()=>{} }, sync:{ get:(k,cb)=>cb&&cb({}) },
               onChanged:{ addListener(){} } },
  };
"""

PROBE = """() => {
    const cards = (typeof kgpFindCards === 'function') ? kgpFindCards() : [];
    const skips = {};
    document.querySelectorAll('[data-kgp-skip]').forEach(e => {
      const r = e.getAttribute('data-kgp-skip'); skips[r] = (skips[r] || 0) + 1;
    });
    const rakutenItem = /item\\.rakuten\\.co\\.jp\\/[^\\/]+\\/[^\\/]+/;
    return {
      cards: cards.length,
      unique: new Set(cards.map(c => c.url)).size,
      allRakutenItem: cards.length > 0 && cards.every(c => rakutenItem.test(c.url || '')),
      adAdopted: cards.filter(c => /redirect_rpp|ias\\.rakuten/.test(c.url || '')).length,
      skips: skips,
    };
}"""


def _isolated_code():
    scripts = [j for cs in MANIFEST["content_scripts"]
               if (cs.get("world") or "ISOLATED") == "ISOLATED" for j in cs["js"]]
    return ";\n".join((EXT / s).read_text(encoding="utf-8") for s in scripts)


def _run(code):
    """오너 실측 스냅샷을 그대로 띄워 타일 감지를 실측한다(합성 픽스처 금지)."""
    from playwright.sync_api import sync_playwright

    hits = sorted(_DIAG.glob(_SNAP))
    if not hits:
        pytest.skip(f"스냅샷 미커밋: {_SNAP}")
    body = hits[0].read_text(encoding="utf-8", errors="ignore")
    exe = _pw.chromium_hits()
    opts = {"executable_path": exe[0]} if exe else {}
    # 이미지는 플레이스홀더로 — 전부 abort하면 img 크기가 0이라 카드 감지가 실패해 계약이 공허해진다.
    ph = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
          '<rect fill="#ccc" width="200" height="200"/></svg>')
    with sync_playwright() as pw:
        b = pw.chromium.launch(**opts)
        page = b.new_context(viewport={"width": 1400, "height": 900}).new_page()

        def route(r):
            u = r.request.url.split("#")[0]
            if u == _URL:
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
            elif r.request.resource_type == "image":
                r.fulfill(status=200, content_type="image/svg+xml", body=ph)
            else:
                r.abort()
        page.route("**/*", route)
        page.goto(_URL, wait_until="domcontentloaded")
        page.evaluate(CHROME_STUB)
        page.evaluate(code)
        page.wait_for_timeout(900)
        got = page.evaluate(PROBE)
        b.close()
    return got


# ── 소스 계약 ────────────────────────────────────────────────────────────────

def test_rakuten_item_href_recognised_source():
    """라쿠텐 상품 판정이 **호스트+세그먼트 수** 기준으로 존재한다(형식 추측 금지)."""
    assert "function _kgpIsRakutenItemHref" in CS
    seg = CS.split("function _kgpIsRakutenItemHref")[1].split("\n}")[0]
    assert "item.rakuten.co.jp" in seg.replace("\\", "")
    assert "seg.length >= 2" in seg, "세그먼트 2개 이상 규칙이 없다(샵 최상위까지 상품으로 오인)"
    assert "_kgpIsRakutenItemHref(h)" in CS, "_kgpIsProductHref가 라쿠텐 판정을 호출하지 않는다"


def test_ad_redirect_reason_separated_source():
    """광고 리다이렉트를 'no-item-url'로 뭉뚱그리지 않고 별도 사유로 남긴다."""
    assert "function _kgpIsAdRedirectHref" in CS
    assert '"ad-redirect"' in CS


# ── 실브라우저: 오너 실측 스냅샷 ──────────────────────────────────────────────

@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_rakuten_search_tiles_resolved():
    """라쿠텐 검색 스냅샷 — 타일이 실제로 감지되고, URL이 전부 라쿠텐 상품 상세다."""
    got = _run(_isolated_code())
    # 공허한 통과 방지: 0건이면 아래 단언이 의미 없다.
    assert got["cards"] >= 30, ("라쿠텐 검색 타일이 여전히 안 잡힌다", got)
    assert got["unique"] == got["cards"], ("중복 URL이 병합되지 않았다", got)
    assert got["allRakutenItem"], ("상품 상세가 아닌 URL이 섞였다", got)
    # no-item-url은 잔여 쓰레기 링크 수준으로 떨어져야 한다(수리 전 80).
    assert got["skips"].get("no-item-url", 0) <= 5, ("여전히 대량 no-item-url", got)


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_ad_redirect_tiles_excluded_and_labelled():
    """광고 리다이렉트는 **채택하지 않되** 사유를 정직하게 남긴다.

    채택하면 안 되는 근거(실측): 목적지 URL이 타일 어디에도 없고, normalize_product_key가 쿼리를 버려
    광고 링크가 전부 같은 키로 붕괴한다 → 서로 다른 상품이 1건으로 합쳐져 **소실**된다.
    """
    got = _run(_isolated_code())
    assert got["adAdopted"] == 0, ("광고 리다이렉트 URL이 상품으로 채택됐다 — 키 붕괴로 소실 위험", got)
    assert got["skips"].get("ad-redirect", 0) >= 5, ("광고 타일이 ad-redirect로 집계되지 않는다", got)


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_contract_fails_without_rakuten_pattern():
    """인위회귀 — 라쿠텐 판정을 빼면 타일이 다시 통째로 사라져야 한다(게이트가 실제로 잡는지)."""
    code = _isolated_code()
    anchor = "  if (_kgpIsRakutenItemHref(h)) return true;"
    assert anchor in code, "회귀 주입 지점을 찾지 못했다"
    broken = code.replace(anchor, "  // removed", 1)
    got = _run(broken)
    assert got["cards"] < 5, ("라쿠텐 판정을 제거했는데도 타일이 잡힌다 = 게이트가 무의미", got)


def test_ad_redirect_key_collapse_is_real():
    """광고 URL을 채택하면 안 되는 이유를 **서버 정규화로 실증**한다(주장 아님).

    서로 다른 광고 링크가 같은 product_key로 붕괴하면, 수집 시 dedup(v42 1-3)이 다른 상품을 같은 것으로 본다.
    """
    from src.collectors.product_key import normalize_product_key as key
    a = "https://grp07.ias.rakuten.co.jp/redirect_rpp/?s=AAA&d=2026-07-28&si=XXX"
    b = "https://grp07.ias.rakuten.co.jp/redirect_rpp/?s=BBB&d=2026-07-28&si=YYY"
    assert key(a) == key(b), "전제가 바뀌었다 — 광고 URL이 더는 붕괴하지 않으면 이 제외 근거를 재검토할 것"
    # 반대로 실제 상품 URL은 쿼리와 무관하게 **상품별로** 안정된 키를 만든다.
    i1 = "https://item.rakuten.co.jp/tabemon-dikara/20072/?variantId=20072"
    i2 = "https://item.rakuten.co.jp/tabemon-dikara/20072/"
    i3 = "https://item.rakuten.co.jp/liquor-boss/19291bc5/"
    assert key(i1) == key(i2), "같은 상품이 쿼리 때문에 다른 키가 된다(중복 수집)"
    assert key(i1) != key(i3), "다른 상품이 같은 키로 붕괴한다(소실)"
