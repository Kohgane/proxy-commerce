"""tests/test_v81_ali_carousel_verdict.py — v81 STEP6: 알리 캐러셀 판정 회수(v80 STEP2 배포 감사).

v80 STEP2(#538, 최외곽 캐러셀 컨테이너 앵커 + z-index 2147483644)가 main에 배포됐는지 감사하고
판정을 못박는다. 코드 변경 없음(회수/감사) — 계약이 유지되는지 드리프트 가드.

판정: 캐러셀 안정 앵커 계약 present + 라이브 하네스(슬라이드 교체 후 버튼 생존)에 여전히 그린.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
DETECT = Path("extensions/chrome-collector/kgp-detect.js").read_text(encoding="utf-8")


# ── 배포 감사(소스계약): v80 STEP2 안정 앵커가 main에 실존 ──
def test_v80_step2_carousel_anchor_deployed():
    assert "const _carRe = /(carousel|swiper|slider|slick|gallery|magnifier)/i;" in CS
    assert "if (_carRe.test(tok)) carousel = cur;" in CS      # 계속 올라가며 최외곽 갱신
    assert "host = carousel || imgEl.parentElement;" in CS     # 캐러셀 없으면 정밀 앵커(회귀 0)
    assert '"z-index:2147483644 !important"' in CS             # 알리 호버 오버레이(…643) 위
    # v80 STEP2 가드 모듈이 리포에 존재(배포 감사).
    assert Path("tests/test_v80_carousel_anchor.py").exists()


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


_CHROME_STUB = """
window.chrome = {
  runtime: { id: 'x', onMessage: { addListener(){} }, sendMessage(){}, getURL: u => u, lastError: null,
             getManifest: () => ({ version: '1.5.120' }) },
  storage: { local: { get:(k,cb)=>cb&&cb({}), set(){}, onChanged:{addListener(){}} },
             sync:  { get:(k,cb)=>cb&&cb({}), set(){}, onChanged:{addListener(){}} } }
};
"""

_ALI = (
    '<!doctype html><html><head><meta charset="utf-8"><title>ali search</title></head><body><div class="list">'
    '<div class="product-card"><a href="/item/1005001.html">'
    '<div class="images-magnifier swiper" data-role="gallery"><div class="swiper-wrapper">'
    '<div class="swiper-slide"><img src="https://ae01.alicdn.com/kf/S1_a.jpg" width="220" height="220"></div>'
    '<div class="swiper-slide"><img src="https://ae01.alicdn.com/kf/S1_b.jpg" width="220" height="220"></div>'
    '</div></div></a><div class="hover-preview" style="position:absolute;z-index:2147483643"></div>'
    '<div class="title">Foam Roller Massage 1</div><div class="price">US $6.62</div></div>'
    '<div class="product-card"><a href="/item/1005002.html">'
    '<div class="images-magnifier swiper"><div class="swiper-wrapper">'
    '<div class="swiper-slide"><img src="https://ae01.alicdn.com/kf/S2_a.jpg" width="220" height="220"></div>'
    '</div></div></a><div class="title">Foam Roller Massage 2</div><div class="price">US $7.10</div></div>'
    '<div class="product-card"><a href="/item/1005003.html">'
    '<div class="images-magnifier swiper"><div class="swiper-wrapper">'
    '<div class="swiper-slide"><img src="https://ae01.alicdn.com/kf/S3_a.jpg" width="220" height="220"></div>'
    '</div></div></a><div class="title">Foam Roller Massage 3</div><div class="price">US $8.00</div></div>'
    '</div></body></html>'
)
ALI_URL = "https://www.aliexpress.com/w/wholesale-roller.html?q=roller"


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_verdict_button_survives_slide_swap():
    """판정 회수 라이브: 슬라이드 교체 후에도 버튼이 캐러셀 컨테이너에 생존(v80 STEP2 계약 유지)."""
    from playwright.sync_api import sync_playwright
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()

        def h(r):
            if r.request.url.split("#")[0] == ALI_URL:
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=_ALI)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(ALI_URL, wait_until="domcontentloaded")
        page.evaluate("(a)=>{ (0,eval)(a[0]); (0,eval)(a[1]); (0,eval)(a[2]); }", [_CHROME_STUB, DETECT, CS])
        page.wait_for_timeout(900)
        info = page.evaluate("""async () => {
            const sleep = (ms)=>new Promise(r=>setTimeout(r,ms));
            const q = document.querySelector('.product-card:first-child .kgp-card-quick');
            if (!q) return { err:'no-button' };
            const z = parseInt(getComputedStyle(q).zIndex || '0', 10);
            const track = document.querySelector('.swiper-wrapper');
            track.innerHTML = '<div class="swiper-slide"><img src="https://ae01.alicdn.com/kf/S1_c.jpg" width="220" height="220"></div>';
            await sleep(400);
            const still = document.querySelector('.product-card:first-child .kgp-card-quick');
            return { z, survived: !!still,
                     stillCarousel: !!(still && still.parentElement && still.parentElement.classList.contains('swiper')) };
        }""")
        b.close()
    assert "err" not in info, info
    assert info["survived"] is True, ("슬라이드 교체 후 버튼 증발(회귀!)", info)
    assert info["stillCarousel"] is True, ("교체 후 버튼이 캐러셀 컨테이너 이탈(회귀!)", info)
    assert info["z"] >= 2147483644, ("z-index 오버레이 위 아님(회귀!)", info)
