"""tests/test_v86_shadow_visibility.py — v86 STEP1: 가시성 계약(실브라우저).

오너 실측 확정: FAB는 fixed/top/right로 **존재**하는데 화면엔 안 보였다. 원인은 `all:initial !important`를
인라인에 걸면 Chrome이 250여 롱핸드로 전개해 배경·크기까지 초기화하고, 인라인 !important라 우리 시트로
복원이 원천 봉쇄되기 때문이다(width/height/transform initial 실측).

기존 계약(v84)은 `position==fixed`만 봐서 이 상태를 **전부 통과**시켰다. 그래서 "위치는 맞는데 안 보이는"
층을 따로 못박는다. 계약 3종:
  (1) shadow 내부 버튼의 computed background-color != transparent  ← 배경 초기화 감지
  (2) offsetWidth >= 40 (및 높이 >= 20)                            ← 크기 초기화 감지
  (3) 뷰포트 우측 절반 좌표                                          ← 위치 회귀 감지

추가로 **인위 회귀 검증**을 같은 실행 안에서 한다(가짜 게이트 방지): 배경 선언을 제거한 코드로 같은 페이지를
띄워 계약 (1)이 실제로 **실패**하는지 확인한다. 계약이 실패할 수 없으면 그 게이트는 의미가 없다.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

EXT = Path("extensions/chrome-collector")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))

# 사이트가 공격적인 전역 CSS를 걸어도 shadow 경계가 막아야 한다(격리 검증 포함).
PAGE_HTML = (
    "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>t</title>"
    "<style>*{background:none !important;border:0 !important;font-size:0 !important;"
    "width:auto !important;height:auto !important}</style></head>"
    "<body><h1 class='item_name'>테스트 상품</h1><div class='item_price'>3,980円</div></body></html>"
)

CHROME_STUB = """
  window.chrome = {
    runtime: { id: 'x', lastError: null, getManifest: () => ({version:'0'}), getURL: (p)=>p,
               sendMessage: (m,cb)=>{ cb && setTimeout(()=>cb({ok:false}),0); }, onMessage:{addListener(){}} },
    storage: { local: { get:(k,cb)=>cb&&cb({}), set:()=>{} }, sync:{ get:(k,cb)=>cb&&cb({}) },
               onChanged:{ addListener(){} } },
  };
"""

PROBE_JS = """() => {
    const host = document.getElementById('kgp-collect-fab');
    if (!host) return { exists: false };
    const hs = getComputedStyle(host);
    const hr = host.getBoundingClientRect();
    const inner = host.shadowRoot ? host.shadowRoot.querySelector('.w') : null;
    const is = inner ? getComputedStyle(inner) : null;
    return {
      exists: true,
      hasShadow: !!host.shadowRoot,
      hostPosition: hs.position,
      innerBg: is ? is.backgroundColor : '',
      innerW: inner ? inner.offsetWidth : 0,
      innerH: inner ? inner.offsetHeight : 0,
      innerVisibility: is ? is.visibility : '',
      innerOpacity: is ? is.opacity : '',
      hostLeft: hr.left,
    };
}"""


def _pw_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    if glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"):
        return True
    cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or (Path.home() / ".cache" / "ms-playwright"))
    return cache.is_dir() and any(cache.glob("chromium-*"))


def _isolated_code() -> str:
    scripts = [
        j
        for cs in MANIFEST["content_scripts"]
        if (cs.get("world") or "ISOLATED") == "ISOLATED"
        for j in cs["js"]
    ]
    return ";\n".join((EXT / s).read_text(encoding="utf-8") for s in scripts)


def _measure(code: str) -> dict:
    """주어진 content_script 코드로 페이지를 띄우고 FAB 가시성 지표를 실측한다."""
    from playwright.sync_api import sync_playwright

    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    opts = {"executable_path": hits[0]} if hits else {}
    proxy = os.environ.get("HTTPS_PROXY")
    if proxy:
        opts["proxy"] = {"server": proxy, "bypass": "127.0.0.1,localhost"}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**opts)
        page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
        page.route(
            "**/*",
            lambda route: (
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=PAGE_HTML)
                if route.request.url.startswith("https://item.rakuten.co.jp/")
                else route.abort()
            ),
        )
        page.goto("https://item.rakuten.co.jp/x/y/", wait_until="domcontentloaded")
        page.evaluate(CHROME_STUB)
        page.evaluate(code)
        page.wait_for_timeout(300)
        got = page.evaluate(PROBE_JS)
        browser.close()
    return got


TRANSPARENT = ("", "rgba(0, 0, 0, 0)", "transparent")


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_fab_visible_three_contracts():
    got = _measure(_isolated_code())
    assert got["exists"], "FAB 미주입 — 화면에 수집 버튼이 없다"
    assert got["hasShadow"], "shadow 호스트가 아니다(all:initial 라이트 DOM 경로 잔존)"
    assert got["hostPosition"] == "fixed", got
    # (1) 배경 — all:initial 전개로 초기화되면 여기서 잡힌다.
    assert got["innerBg"] not in TRANSPARENT, ("배경이 투명 — 비가시", got)
    # (2) 크기 — 사이트의 width/height !important 전역 규칙에도 shadow 안은 살아 있어야 한다.
    assert got["innerW"] >= 40, ("너비 초기화 — 비가시", got)
    assert got["innerH"] >= 20, ("높이 초기화 — 비가시", got)
    assert got["innerVisibility"] != "hidden", got
    assert float(got["innerOpacity"] or "1") > 0, got
    # (3) 위치 — 뷰포트 우측 절반.
    assert got["hostLeft"] > 640, ("우측 절반에 있어야 한다", got)


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_visibility_contract_actually_fails_on_regression():
    """인위 회귀 — 배경 선언을 제거하면 계약 (1)이 **실패해야** 한다.

    실패할 수 없는 계약은 게이트가 아니다(가짜 그린 방지). v84에서 CI 브랜치로 증명했던 절차를
    같은 실행 안으로 들여와 상시 자동화한다.
    """
    code = _isolated_code()
    broken = code.replace("background:#1a1714;", "")
    assert broken != code, "회귀 주입 실패 — FAB shadow CSS의 배경 선언을 찾지 못했다"
    got = _measure(broken)
    assert got["exists"] and got["hasShadow"], got
    assert got["innerBg"] in TRANSPARENT, ("배경을 지웠는데도 투명이 아니다 = 계약이 회귀를 못 잡는다", got)


def test_fab_source_uses_shadow_not_all_initial():
    """소스 계약: FAB 생성부가 all:initial 리셋 경로로 되돌아가지 않는다."""
    cs = (EXT / "content_script.js").read_text(encoding="utf-8")
    i = cs.index("btn.id = KGP_BTN_ID")
    j = cs.index("_kgpMount(btn)", i)
    block = cs[i:j]
    assert "_kgpShadowHost(btn" in block, "FAB가 shadow 호스트로 만들어지지 않는다"
    assert "_KGP_RESET" not in block, "FAB가 all:initial 리셋 경로로 복귀했다"
    # 공용 헬퍼는 :host 에만 initial을 건다(내부 요소까지 초기화하면 같은 사고 재발).
    assert '":host{all:initial}"' in cs
