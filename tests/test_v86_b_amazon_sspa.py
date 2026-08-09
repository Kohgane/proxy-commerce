"""tests/test_v86_b_amazon_sspa.py — v86-B: 아마존 스폰서 ASIN 추출 + dup 인스턴스 버튼.

오너 실측(라이브): 66타일 중 버튼 18 — 제외 내역 ad 18(sspa)·dup 47·no-url류 29.

근본 두 갈래(둘 다 실측으로 특정):
 1) sspa 링크의 목적지는 **URL 안에 평문으로** 있다 —
    /sspa/click?…&url=%2FComfortable-Magnetic…%2Fdp%2FB0FJM1FRNZ%2Fref%3D…
    (라쿠텐 redirect_rpp의 불투명 토큰과 다르다 → 리다이렉트 추적·서버 호출 없이 해석 가능.)
    그런데 href를 split("?")[0]로 잘라 payload를 통째로 버려서 **모든 광고 타일이 …/sspa/click 하나로
    붕괴** → 첫 건만 채택되고 나머지가 전부 'dup'으로 떨어졌다.
 2) 어댑터가 dup 인스턴스를 채택해도 `_kgpMergeCards`가 **상품키로 다시 합쳐** 도로 지웠다.
    실측: 34개 실타일 중 10개가 data-kgp-skip 표식조차 없이 소멸(v77 '무표식 타일 0' 계약의 위반).

수리 후 실측(오너 스냅샷): cards 19→36 · buttons 36 · sspa 붕괴 0 · 무표식 소멸 0 · sponsored 18.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import _pw

EXT = Path("extensions/chrome-collector")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
CS = (EXT / "content_script.js").read_text(encoding="utf-8")
_SNAPS = sorted(Path("fixtures/realpages/diag").glob("kgp-snapshot-www-amazon-com-s-k-*.html"))
_URL = "https://www.amazon.com/s?k=ultraslim+phone+grip"


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.142"


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

PROBE = r"""async () => {
    const cards = (typeof kgpFindCards === 'function') ? kgpFindCards() : [];
    const tiles = [...document.querySelectorAll(
      '[data-component-type="s-search-result"], div[data-asin]:not([data-asin=""])')];
    const adopted = new Set(cards.map(c => c.el));
    let silent = 0;
    tiles.forEach(t => {
      if (!adopted.has(t) && !t.getAttribute('data-kgp-skip')
          && /s-result-item/.test(String(t.className || ''))) silent++;
    });
    // 광고 타일 첫 건 — 화면 밖이면 elementFromPoint는 원래 null이라 먼저 뷰포트로 옮긴다.
    const ad = cards.find(c => c.sponsored);
    let adHit = null;
    if (ad && ad.el) {
      ad.el.scrollIntoView({ block: 'center' });
      await new Promise(r => setTimeout(r, 150));
      const b = ad.el.querySelector('.kgp-card-quick');
      if (b) {
        const r = b.getBoundingClientRect();
        const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
        adHit = { ok: !!(e && (e === b || b.contains(e))), w: Math.round(r.width) };
      } else { adHit = { ok: false, err: '광고 타일에 버튼 없음' }; }
    }
    return {
      cards: cards.length,
      buttons: document.querySelectorAll('.kgp-card-quick').length,
      sponsored: cards.filter(c => c.sponsored).length,
      dupInstances: cards.filter(c => c.dup_instance).length,
      sspaLeak: cards.filter(c => /sspa\/click/.test(c.url || '')).length,
      allDpUrls: cards.length > 0 && cards.every(c => /\/dp\/[A-Z0-9]{10}/.test(c.url || '')),
      silentDrops: silent,
      adHit: adHit,
    };
}"""


def _isolated_code():
    return ";\n".join(
        (EXT / j).read_text(encoding="utf-8")
        for cs in MANIFEST["content_scripts"]
        if (cs.get("world") or "ISOLATED") == "ISOLATED" for j in cs["js"])


def _run(code):
    """오너 실측 스냅샷을 그대로 띄운다(합성 픽스처 금지)."""
    from playwright.sync_api import sync_playwright

    if not _SNAPS:
        pytest.skip("아마존 검색 스냅샷 미커밋")
    body = _SNAPS[0].read_text(encoding="utf-8", errors="ignore")
    ph = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
          '<rect fill="#ccc" width="200" height="200"/></svg>')
    with sync_playwright() as pw:
        b = pw.chromium.launch(**_pw.launch_opts())
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
        page.wait_for_timeout(1400)
        got = page.evaluate(PROBE)
        b.close()
    return got


# ── 소스 계약 ────────────────────────────────────────────────────────────────

def test_sspa_asin_extracted_from_url_param_source():
    """목적지를 **URL 파라미터에서** 뽑는다 — 리다이렉트 추적·서버 호출 금지(오너 지시)."""
    assert "function _kgpAmazonSspaAsin" in CS
    seg = CS.split("function _kgpAmazonSspaAsin")[1].split("\n}")[0]
    assert "/sspa/click" in seg
    assert 'searchParams.get("url")' in seg
    assert "decodeURIComponent" in seg
    assert "[A-Z0-9]{10}" in seg
    # 추적/서버 호출 0 — 이 함수는 순수 파싱이어야 한다.
    for banned in ("fetch(", "XMLHttpRequest", "sendMessage"):
        assert banned not in seg, f"sspa 해석이 {banned}를 쓴다(리다이렉트 추적 금지)"


def test_ad_sspa_fail_reason_is_separated_source():
    """payload에서도 못 뽑은 광고 타일은 'no-asin'과 원인이 다르다 → 사유 분리(구조 변경 신호)."""
    seg = CS.split("if (!/^[A-Z0-9]{10}$/.test(asin)) {")[1].split("return;")[0]
    assert '"ad-sspa-fail"' in seg and '"no-asin"' in seg


def test_dup_instances_are_preserved_in_merge_source():
    """상품키 병합이 반복 타일을 지우지 않는다(지우면 '왜 이 타일만 버튼이 없지'가 된다)."""
    seg = CS.split("function _kgpMergeCards")[1].split("\n}")[0]
    assert "dup_instance" in seg
    assert "_kgpTaken" in seg, "DOM 타일 단위 인스턴스 보존 로직이 없다"


def test_rakuten_ad_policy_unchanged():
    """라쿠텐 광고(redirect_rpp)는 여전히 제외 — 그쪽은 목적지가 불투명 토큰이라 원칙이 다르다."""
    assert "function _kgpIsAdRedirectHref" in CS
    assert '"ad-redirect"' in CS
    assert "_kgpIsAdRedirectHref(href) ? \"ad-redirect\"" in CS


# ── 실브라우저: 오너 실측 스냅샷 ──────────────────────────────────────────────

@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_amazon_tiles_buttoned_and_ad_clickable():
    got = _run(_isolated_code())
    assert got["buttons"] >= 30, ("타일 버튼이 목표에 못 미친다", got)
    assert got["sspaLeak"] == 0, ("sspa 추적 URL이 상품 URL로 새어 나갔다", got)
    assert got["allDpUrls"], ("상품 URL이 /dp/ASIN 정규형이 아니다", got)
    assert got["sponsored"] >= 10, ("광고 타일이 여전히 통째로 빠진다", got)
    assert got["silentDrops"] == 0, ("표식도 버튼도 없이 사라진 타일이 있다", got)
    assert got["adHit"] and got["adHit"]["ok"], ("광고 타일 버튼이 중앙 히트테스트에 안 잡힌다", got)


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_contract_fails_without_sspa_collapse_guard():
    """인위회귀 — 잘린 sspa href가 URL이 되게 두면 광고 타일이 한 URL로 붕괴해 다시 사라져야 한다.

    정직: 이 스냅샷의 광고 타일은 data-asin을 들고 있어서, 실제로 타일을 되살린 수리는
    **payload ASIN 추출이 아니라 이 붕괴 방지**다. payload 추출(_kgpAmazonSspaAsin)은 data-asin이
    없는 광고 타일용 폴백이며 소스 계약이 따로 못박는다 — 둘을 뭉뚱그리면 어느 쪽이 일했는지 못 읽는다.
    """
    code = _isolated_code()
    anchor = '      if (_aHref.indexOf("/sspa/click") >= 0) href = "";'
    assert anchor in code, "회귀 주입 지점을 찾지 못했다"
    broken = code.replace(anchor, "      // removed", 1)
    got = _run(broken)
    assert got["buttons"] < 30 or got["sspaLeak"] > 0, (
        "붕괴 방지를 껐는데도 멀쩡 = 게이트가 무의미", got)


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_contract_fails_without_instance_preservation():
    """인위회귀 — 인스턴스 보존을 빼면 반복 타일이 다시 표식 없이 사라져야 한다."""
    code = _isolated_code()
    anchor = "    if (!c || !c.el || c.el._kgpTaken) return;"
    assert anchor in code, "회귀 주입 지점을 찾지 못했다"
    broken = code.replace(anchor, "    if (true) return;", 1)
    got = _run(broken)
    assert got["silentDrops"] > 0, ("인스턴스 보존을 껐는데 소멸 타일이 0 = 게이트가 무의미", got)
