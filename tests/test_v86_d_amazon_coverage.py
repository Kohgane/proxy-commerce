"""tests/test_v86_d_amazon_coverage.py — v86-D: 아마존 커버리지 + 툴바 잔재 + 닫기 경로.

■ 갈래 판정(수정 전 실측)
오너 스크린샷의 '스폰서에 우리 버튼 없음'은 **재제외 회귀가 아니었다.** 픽스처 실측에서 스폰서 18/18,
dup 12/12 전부 버튼이 붙는다. `excl.ad`는 v45 P3 설계대로 **집계 전용 카운터**(제외 아님)다.
스크린샷에 안 보인 건 v86-C에서 rest=0 호버 전용으로 바뀌었기 때문이고, 그 타일의 파란 배지는
**경쟁사 확장**이지 우리 것이 아니다.

■ 그 대신 (a) 규명에서 나온 진짜 버그 — 툴바 잔재가 재생성을 막는다
저장된 페이지·확장 업데이트·SPA 복원에는 우리 오버레이 호스트가 **빈 껍데기로 남는다**
(shadow 내용은 직렬화되지 않는다). 그런데 `kgpInjectListing`은
`if (!getElementById(KGP_TOOLBAR_ID)) kgpBuildToolbar()`로만 만들어서, 그 껍데기가 **재생성을 영영 막는다**
→ 벌크바가 DOM엔 있는데 내용 0(버튼·닫기 전부 없음)인 유령이 된다.
v86 STEP3가 타일에 대해 고친 것과 **같은 유형**인데 바를 빼먹었다.
실측: 오너 아마존 스냅샷에 `id="kgp-listing-toolbar"` 1개 + 스테일 타일 18쌍이 실제로 들어 있다.

수리 후: 바 재생성(shadow 有·parent=HTML·버튼 9) → 닫기 클릭 시 chk만 걷히고 호버 버튼 36개 생존.
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


def _isolated_code():
    return ";\n".join(
        (EXT / j).read_text(encoding="utf-8")
        for cs in MANIFEST["content_scripts"]
        if (cs.get("world") or "ISOLATED") == "ISOLATED" for j in cs["js"])


def _run(probe, code=None):
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
        page.evaluate(code or _isolated_code())
        page.wait_for_timeout(1800)
        got = page.evaluate(probe)
        b.close()
    return got


# ── 픽스처가 회귀 재현 조건을 실제로 담고 있는지(반-공허) ─────────────────────

def test_fixture_actually_contains_stale_overlay():
    """이 계약이 의미를 가지려면 스냅샷에 **잔재 호스트가 실제로 있어야** 한다."""
    if not _SNAPS:
        pytest.skip("스냅샷 미커밋")
    html = _SNAPS[0].read_text(encoding="utf-8", errors="ignore")
    assert 'id="kgp-listing-toolbar"' in html, "잔재 툴바가 없는 픽스처 — 회귀 재현 불가"
    assert 'class="kgp-card-quick"' in html, "잔재 타일이 없는 픽스처"


# ── 소스 계약 ────────────────────────────────────────────────────────────────

def test_sweep_covers_toolbar_and_pill_source():
    """잔재 스윕이 타일뿐 아니라 **툴바·재오픈 배지**도 본다(STEP3가 빠뜨린 부분)."""
    seg = CS.split("function _kgpSweepStaleTiles")[1].split("\n}")[0]
    assert "KGP_TOOLBAR_ID" in seg and "KGP_REOPEN_ID" in seg
    assert "_kgpShadow === undefined" in seg, "현행 빌더 산출물과 잔재를 가르는 판정이 없다"


def test_close_handlers_keep_quick_source():
    """바를 **접는** 두 경로(✕·수동 토글)만 chk를 걷고 호버 버튼은 되붙인다.

    주의: 전체 파일에서 `.kgp-card-chk, .kgp-card-quick` 동시 제거를 금지하면 안 된다 —
    목록 아님(cards<3)·비소싱처(kgpTeardown)·상세 전환(kgpRemoveListing)에서는 **전부 걷는 게 맞다**.
    (처음 이 계약을 파일 전역으로 썼다가 그 정당한 정리 3곳에 걸렸다.)
    계약 대상은 '접기'뿐이므로 그 두 핸들러 본문으로 범위를 좁힌다.
    """
    assert CS.count("_kgpReensureQuick()") >= 2, "접기 경로 중 일부가 여전히 버튼을 지운다"
    close_seg = CS.split('} else if (act === "close") {')[1].split("kgpShowReopenPill();")[0]
    auto_seg = CS.split('const next = kgpLSget("kgp_bar_auto"')[1].split("kgpShowReopenPill();")[0]
    for name, seg in (("✕ 닫기", close_seg), ("수동 토글", auto_seg)):
        assert ".kgp-card-quick" not in seg, f"{name} 경로가 호버 버튼까지 지운다"
        assert "_kgpReensureQuick()" in seg, f"{name} 경로가 호버 버튼을 되붙이지 않는다"


def test_reopen_pill_label_unified_source():
    """재오픈 배지는 **벌크바 오프너**다 → 여는 대상(바 그립 '고가수집기')과 명칭 통일."""
    assert "고가수집기 열기" in CS
    assert ">수집 열기<" not in CS, "옛 라벨이 남아 타일 호버 버튼과 혼동된다"


def test_tile_coverage_instrumented_source():
    """부착률·미부착 사유를 진단에 싣는다(절대 수만 보면 '68 중 35'를 못 읽는다)."""
    assert "tile_coverage" in CS
    seg = CS.split("_ui.tile_coverage = {")[1].split("};")[0]
    for k in ("merged:", "attached:", "missing:", "rate:", "missing_by:", "sponsored:", "dup_instances:"):
        assert k in seg, k


def test_hover_test_three_samples_source():
    """첫 타일만 재면 '첫 건은 되는데 나머지는?'을 못 본다 → 첫·중간·마지막 3표본."""
    assert "hover_test_samples" in CS
    seg = CS.split("hover_test_samples")[0][-600:]
    assert "Math.floor(_qs.length / 2)" in seg and "_qs.length - 1" in seg


# ── 실브라우저: 오너 실측 스냅샷 ──────────────────────────────────────────────

COVERAGE_PROBE = r"""() => {
    const cards = (typeof kgpFindCards === 'function') ? kgpFindCards() : [];
    const has = (c) => !!(c.el && c.el.querySelector('.kgp-card-quick'));
    const sp = cards.filter(c => c.sponsored);
    const dup = cards.filter(c => c.dup_instance);
    return {
      merged: cards.length,
      attached: cards.filter(has).length,
      sponsored: sp.length, sponsoredAttached: sp.filter(has).length,
      dup: dup.length, dupAttached: dup.filter(has).length,
    };
}"""


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_every_merged_card_has_a_button():
    """부착률 100% — 스폰서·dup 포함. 종전 계약은 개수만 봐서 이 구멍을 못 잡았다."""
    got = _run(COVERAGE_PROBE)
    assert got["merged"] >= 30, ("감지 자체가 무너졌다", got)
    assert got["attached"] == got["merged"], ("버튼 없는 카드가 있다", got)
    assert got["sponsored"] >= 10 and got["sponsoredAttached"] == got["sponsored"], \
        ("스폰서 타일에 버튼이 빠졌다", got)
    assert got["dup"] > 0 and got["dupAttached"] == got["dup"], ("dup 인스턴스에 버튼이 빠졌다", got)


TOOLBAR_PROBE = r"""async () => {
    const bar = document.getElementById('kgp-listing-toolbar');
    const sr = bar && (bar._kgpShadow || bar.shadowRoot);
    const out = {
      bar: !!bar, hasShadow: !!sr,
      parent: bar && bar.parentElement && bar.parentElement.tagName,
      btns: sr ? sr.querySelectorAll('.kgp-tb-btn').length : 0,
      quickBefore: document.querySelectorAll('.kgp-card-quick').length,
    };
    const x = sr && sr.querySelector('.kgp-tb-btn[data-act="close"]');
    if (!x) { out.err = '닫기 버튼 없음'; return out; }
    x.click();
    // v86-D: 재스캔(디바운스 300ms)이 되붙이기 **전**에 잰다. 300ms 뒤에 복구되더라도 그 사이
    //   버튼이 사라지는 건 사용자 눈에 깜빡임이고, 정적 페이지(뮤테이션 없음)에선 영영 안 돌아온다.
    await new Promise(r => setTimeout(r, 120));
    out.quickAfterClose = document.querySelectorAll('.kgp-card-quick').length;
    out.chkAfterClose = document.querySelectorAll('.kgp-card-chk').length;
    out.barAfterClose = !!document.getElementById('kgp-listing-toolbar');
    const pill = document.getElementById('kgp-listing-reopen');
    const pr = pill && (pill._kgpShadow || pill.shadowRoot);
    out.pillText = pill ? ((pr || pill).textContent || '').trim() : null;
    return out;
}"""


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_stale_toolbar_rebuilt_and_close_keeps_hover():
    """잔재 껍데기를 걷고 바를 다시 세운다 + 닫아도 호버 버튼은 산다."""
    got = _run(_isolated_code())
    got = _run(TOOLBAR_PROBE)
    assert got["bar"] and got["hasShadow"], ("바가 유령(빈 껍데기)으로 남았다", got)
    assert got["parent"] == "HTML", ("바가 documentElement 직속이 아니다(v45 P4 회귀)", got)
    assert got["btns"] >= 5, ("바에 버튼이 없다 — 내용 0인 껍데기", got)
    assert "err" not in got, got
    # 닫기: chk만 걷고 호버 버튼은 생존.
    assert got["quickAfterClose"] == got["quickBefore"], ("바를 닫자 호버 버튼이 사라졌다", got)
    assert got["chkAfterClose"] == 0, ("바를 닫았는데 체크박스가 남았다", got)
    assert got["barAfterClose"] is False, got
    assert got["pillText"] == "고가수집기 열기", ("재오픈 배지 명칭 미통일", got)


# ── 인위회귀 ─────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_contract_fails_without_toolbar_sweep():
    """인위회귀 — 스윕에서 툴바를 빼면 잔재 껍데기가 재생성을 막아 바가 유령으로 남아야 한다."""
    code = _isolated_code()
    anchor = "    var hostIds = [KGP_TOOLBAR_ID, KGP_REOPEN_ID];"
    assert anchor in code, "회귀 주입 지점을 찾지 못했다"
    broken = code.replace(anchor, "    var hostIds = [];", 1)
    got = _run(TOOLBAR_PROBE, code=broken)
    assert got["bar"], got
    assert not got["hasShadow"] or got["btns"] == 0, \
        ("툴바 스윕을 껐는데도 바가 멀쩡히 세워진다 = 게이트가 무의미", got)


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_contract_fails_when_close_wipes_hover_buttons():
    """인위회귀 — 접기 핸들러가 다시 호버 버튼을 지우면 계약이 빨개져야 한다."""
    code = _isolated_code()
    anchor = ('      document.querySelectorAll(".kgp-card-chk").forEach((b) => b.remove());\n'
              "      _kgpReensureQuick();")
    assert anchor in code, "회귀 주입 지점을 찾지 못했다"
    broken = code.replace(
        anchor,
        '      document.querySelectorAll(".kgp-card-chk, .kgp-card-quick").forEach((b) => b.remove());', 1)
    got = _run(TOOLBAR_PROBE, code=broken)
    assert "err" not in got, got
    assert got["quickAfterClose"] < got["quickBefore"], \
        ("접기가 버튼을 지우게 되돌렸는데도 계약이 통과한다 = 게이트가 무의미", got)
