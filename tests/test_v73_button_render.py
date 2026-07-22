"""tests/test_v73_button_render.py — v73 STEP1: 버튼 렌더 회귀 가드(bisect 확정 + 재발 방지 machine).

배경(오너 회귀 리포트): 아마존 검색결과 중앙 벌크바 소멸·상세 우측 FAB 소멸·호버 버튼 일부만.
용의자=v72 STEP4 격리 커밋(0d46c55, all:initial !important).

bisect 확정(이 가드가 못박음): 회귀 커밋=**0d46c55(v72 STEP4)**. 근본 원인은 감지·주입 로직이 아니라
**위치 오프셋**: all:initial !important가 top/left/right/transform을 `auto !important`로 덮어썼는데,
벌크바·FAB·호버버튼의 그 오프셋들은 **비-!important**였다 → auto가 이겨 요소가 정적 흐름(긴 페이지
최하단=화면 밖)으로 떨어져 '소멸'. 카드 배지는 오프셋이 이미 !important라 생존('배지는 보이는데
바/FAB/호버는 소멸'과 정확히 일치). 수리(v73 STEP1): 크기 격리(all:initial)는 유지하되 위치 오프셋
전부에 !important 부여 + 동적 위치(드래그·클램프)도 setProperty(...,'important'). 이 가드가 '존재하나
안 보임'(barVisible=실렌더+뷰포트)을 검증해 "추출은 되는데 버튼이 사라지는" 회귀를 기계로 잡는다.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
DETECT = Path("extensions/chrome-collector/kgp-detect.js").read_text(encoding="utf-8")
SEARCH_FIXTURE = Path("fixtures/realpages/amazon-search.html").read_text(encoding="utf-8")
DP_FIXTURE = Path("fixtures/realpages/synthetic-amazon-dp.html").read_text(encoding="utf-8")


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


# chrome 스텁을 evaluate 함수 본문에 인라인 정의 → 스크립트 eval과 동일 동기 호출(add_init_script 레이스 제거).
# 매니페스트 로드 순서대로 kgp-detect.js → content_script.js 를 eval(실 번들 = 감지 모듈 위임 경로 검증).
_INJECT = """(a) => {
  const [detect, cs] = a;
  window.chrome = {
    runtime: { id: 'x', onMessage: { addListener(){} }, sendMessage(){}, getURL: u => u, lastError: null,
               getManifest: () => ({ version: '1.5.118' }) },
    storage: {
      local: { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } },
      sync:  { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } }
    }
  };
  (0, eval)(detect);
  (0, eval)(cs);
}"""


def _run(url, body):
    from playwright.sync_api import sync_playwright
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()

        def handler(route):
            if route.request.url.split("#")[0] == url:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
            else:
                route.abort()
        page.route("**/*", handler)
        page.goto(url, wait_until="domcontentloaded")
        page.evaluate(_INJECT, [DETECT, CS])   # chrome 정의 + kgp-detect + CS eval(동기·무레이스)
        page.wait_for_timeout(1200)
        info = page.evaluate("""() => {
            const bar = document.getElementById('kgp-listing-toolbar');
            const fab = document.getElementById('kgp-collect-fab');
            const fcs = fab ? getComputedStyle(fab) : null;
            const bcs = bar ? getComputedStyle(bar) : null;
            const brc = bar ? bar.getBoundingClientRect() : null;
            // 실렌더 판정: DOM 존재 + display/visibility + 뷰포트 안 + 폭>0. '존재하나 안 보임'(소멸 증상) 차단.
            const barVisible = !!(bar && bcs.display !== 'none' && bcs.visibility !== 'hidden'
                && parseFloat(bcs.opacity || '1') > 0 && brc.width > 0 && brc.top >= 0 && brc.top < 720);
            return {
                pageType: (typeof kgpPageType === 'function') ? kgpPageType() : '?',
                bar: !!bar,
                barVisible: barVisible,
                barPosition: bcs ? bcs.position : null,
                barTop: brc ? Math.round(brc.top) : null,
                fab: !!fab,
                fabPosition: fcs ? fcs.position : null,
                fabVisible: fcs ? (fcs.display !== 'none' && fcs.visibility !== 'hidden') : null,
                badges: document.querySelectorAll('.kgp-card-chk').length,
                quick: document.querySelectorAll('.kgp-card-quick').length,
                // v77 STEP1(B): 상시 노출 금지 — 미선택/미수집인데 opacity>0(호버 아닌데 보임) = 정책 위반.
                persistentBadge: (() => { let n=0; document.querySelectorAll('.kgp-card-chk').forEach((b)=>{ const on=b.shadowRoot && b.shadowRoot.querySelector('.b.on'); if(!on && parseFloat(getComputedStyle(b).opacity||'1')>0) n++; }); return n; })(),
                persistentQuick: (() => { let n=0; document.querySelectorAll('.kgp-card-quick').forEach((q)=>{ if(q.dataset.collected!=='1' && parseFloat(getComputedStyle(q).opacity||'1')>0) n++; }); return n; })(),
                maxQuickPerTile: (() => { let mx=0; (typeof _kgpAmazonCards==='function'?_kgpAmazonCards():[]).forEach((c)=>{ const el=c.el||c; const n=el.querySelectorAll?el.querySelectorAll('.kgp-card-quick').length:0; if(n>mx)mx=n; }); return mx; })(),
                amazonCards: (typeof _kgpAmazonCards === 'function') ? _kgpAmazonCards().length : -1,
                count: (document.getElementById('kgp-tb-count') || {}).textContent || '',
            };
        }""")
        b.close()
    return info


AMZ_SEARCH_URL = "https://www.amazon.com/s?k=ultraslim+phone+grip"
AMZ_DP_URL = "https://www.amazon.com/dp/B0AMZDP0001"


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_amazon_search_renders_bulk_bar_and_all_tile_buttons():
    """아마존 검색: 벌크바 + 전 타일(24) 배지·호버 버튼 렌더 + 카운트 계약 '메인 16 · 광고 8'."""
    info = _run(AMZ_SEARCH_URL, SEARCH_FIXTURE)
    assert info["pageType"] == "list", info
    assert info["bar"] is True, ("중앙 벌크바 소멸 회귀!", info)
    assert info["barVisible"] is True, ("벌크바가 DOM엔 있으나 실렌더 안 됨(소멸 증상)!", info)
    assert info["amazonCards"] == 24, info
    assert info["badges"] == 24, ("선택 토글 일부 타일 누락 회귀!", info)
    assert info["quick"] == 24, ("호버 [수집] 버튼 일부만 회귀!", info)
    # v77 STEP1(B): 단일 버튼 시스템 — 타일당 [수집] 1개 · 상시 노출 0(호버 시에만).
    assert info["maxQuickPerTile"] <= 1, ("타일당 [수집] 2개 이상(이중 버튼) 회귀!", info)
    assert info["persistentQuick"] == 0, ("상시 [수집] 노출 금지 위반(호버 시에만)!", info)
    assert info["persistentBadge"] == 0, ("상시 선택 토글 노출 금지 위반(호버 시에만)!", info)
    assert "메인 16 · 광고 8" in info["count"], info


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_amazon_detail_renders_right_fab():
    """아마존 상세: 우측 단건 FAB 렌더(fixed·가시) — '상세 우측 버튼 소멸' 회귀 가드."""
    info = _run(AMZ_DP_URL, DP_FIXTURE)
    assert info["pageType"] == "single", info
    assert info["fab"] is True, ("상세 우측 FAB 소멸 회귀!", info)
    assert info["fabPosition"] == "fixed", info
    assert info["fabVisible"] is True, info
    assert info["bar"] is False, ("상세에서 벌크바가 뜨면 안 됨(상호배타)", info)
