"""tests/test_v80_carousel_anchor.py — v80 STEP2: 알리 캐러셀 안정 앵커.

오너 진단(1.5.114): 알리 카드 호버 시 이미지 자동 슬라이드 → img 부모(슬라이드)가 매 전환마다 교체 →
버튼 앵커 재배치·증발·클릭 불가. 수리: ① 이미지가 캐러셀/슬라이더 안이면 앵커를 img 부모(슬라이드)가 아닌
**캐러셀 컨테이너(안정, 교체 안 됨)** 기준 absolute → 좌표 고정. ② 버튼 z-index를 알리 호버 오버레이 위로.
계약: 슬라이드 교체 후에도 버튼이 DOM에 생존(캐러셀 컨테이너 자식)·클릭 가능.
"""
from __future__ import annotations

from tests import _pw

import glob
import json
import os
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
DETECT = Path("extensions/chrome-collector/kgp-detect.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.133"


# ── source-contract: 캐러셀 안정 앵커 + z-index ──
def test_carousel_anchor_source():
    # c.el까지 올라가며 최외곽 캐러셀 조상(안정 컨테이너)을 앵커로 — 슬라이드(swiper-slide) 회피.
    assert "const _carRe = /(carousel|swiper|slider|slick|gallery|magnifier)/i;" in CS
    assert "if (_carRe.test(tok)) carousel = cur;" in CS
    assert "host = carousel || imgEl.parentElement;" in CS
    # z-index 알리 호버 오버레이 위로(2147483644).
    assert '"z-index:2147483644 !important"' in CS
    # 재부착 트리거는 우리 오버레이 제거 시만(캐러셀 img 교체 변이 제외) — v74 STEP3 유지.
    assert "if (_isOurOverlay(rm[j])) { kgpReattachOverlays(); return; }" in CS


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(_pw.chromium_hits())


_CHROME_STUB = """
window.chrome = {
  runtime: { id: 'x', onMessage: { addListener(){} }, sendMessage(){}, getURL: u => u, lastError: null,
             getManifest: () => ({ version: '1.5.120' }) },
  storage: {
    local: { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } },
    sync:  { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } }
  }
};
"""

# 알리식 목록: 카드 안에 캐러셀 컨테이너(swiper=안정) > 트랙 > 슬라이드 > img. 호버 오버레이(높은 z-index) 포함.
#   ('carousel'·'slider'는 _kgpNonProductRe(추천영역 신호) → 카드 배제되므로 실 알리처럼 swiper 사용.)
_ALI_LIST = (
    '<!doctype html><html><head><meta charset="utf-8"><title>ali search</title></head><body>'
    '<div class="list">' +
    "".join(
        '<div class="product-card"><a href="/item/100500%d.html">'
        '<div class="images-magnifier swiper" data-role="gallery">'
        '<div class="swiper-wrapper">'
        '<div class="swiper-slide"><img src="https://ae01.alicdn.com/kf/S%d_a.jpg" width="220" height="220"></div>'
        '<div class="swiper-slide"><img src="https://ae01.alicdn.com/kf/S%d_b.jpg" width="220" height="220"></div>'
        '</div></div></a>'
        '<div class="hover-preview" style="position:absolute;z-index:2147483643"></div>'
        '<div class="title">Foam Roller Massage %d</div><div class="price">US $6.62</div></div>'
        % (i, i, i, i) for i in range(1, 5)
    )
    + '</div></body></html>'
)

ALI_URL = "https://www.aliexpress.com/w/wholesale-roller.html?q=roller"


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_button_anchors_carousel_and_survives_swap():
    """버튼이 캐러셀 컨테이너(안정)에 앵커 + 슬라이드 img 교체 후에도 생존·클릭 가능·z-index 오버레이 위."""
    from playwright.sync_api import sync_playwright
    exe = _pw.chromium_hits()[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()

        def h(r):
            if r.request.url.split("#")[0] == ALI_URL:
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=_ALI_LIST)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(ALI_URL, wait_until="domcontentloaded")
        page.evaluate("(a)=>{ (0,eval)(a[0]); (0,eval)(a[1]); (0,eval)(a[2]); }", [_CHROME_STUB, DETECT, CS])
        page.wait_for_timeout(900)

        info = page.evaluate("""async () => {
            const sleep = (ms) => new Promise(r => setTimeout(r, ms));
            const q = document.querySelector('.kgp-card-quick');
            if (!q) return { err: 'no-button' };
            // 앵커가 캐러셀 컨테이너인지(슬라이드 아님).
            const parent = q.parentElement;
            const anchoredToCarousel = !!(parent && parent.classList.contains('swiper'));
            const anchoredToSlide = !!(parent && parent.classList.contains('swiper-slide'));
            const z = parseInt(getComputedStyle(q).zIndex || '0', 10);
            // 캐러셀 슬라이드 교체(자동 슬라이드 시뮬): 트랙의 슬라이드들을 새 노드로 교체.
            const track = document.querySelector('.swiper-wrapper');
            track.innerHTML = '<div class="swiper-slide"><img src="https://ae01.alicdn.com/kf/S1_c.jpg" width="220" height="220"></div>';
            await sleep(400);   // 재부착 디바운스(100ms)·재스캔(300ms) 경과
            // 슬라이드 교체 후에도 버튼 생존 + 여전히 캐러셀 컨테이너 자식.
            const still = document.querySelector('.kgp-card-quick');
            const survived = !!still;
            const stillCarousel = !!(still && still.parentElement && still.parentElement.classList.contains('swiper'));
            // 중복 버튼 0(교체가 버튼을 복제하지 않음).
            const dupCount = document.querySelectorAll('.product-card:first-child .kgp-card-quick').length;
            return { anchoredToCarousel, anchoredToSlide, z, survived, stillCarousel, dupCount };
        }""")
        b.close()

    assert "err" not in info, info
    assert info["anchoredToCarousel"] is True, ("버튼이 캐러셀 컨테이너에 앵커 안 됨", info)
    assert info["anchoredToSlide"] is False, ("버튼이 슬라이드(교체됨)에 앵커됨!", info)
    assert info["z"] >= 2147483644, ("z-index가 호버 오버레이(2147483643) 위 아님", info)
    assert info["survived"] is True, ("슬라이드 교체 후 버튼 증발!", info)
    assert info["stillCarousel"] is True, ("교체 후 버튼이 캐러셀 컨테이너에서 이탈", info)
    assert info["dupCount"] <= 1, ("교체가 버튼 복제!", info)
