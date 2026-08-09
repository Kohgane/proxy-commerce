"""tests/test_v84_injection_harness.py — v84 STEP1(P0-A): UI 주입 사활 계약.

오너 실기기 사고: 추출 값 계약은 전부 그린인데 **화면엔 수집 버튼이 없었다**(FAB computed position=initial).
값만 보는 하네스는 이걸 절대 못 잡는다 → 주입 자체를 계약으로 만든다.

두 층위(정직한 역할 분담):
1) jsdom(`scripts/inject_harness.js`) — 스크립트가 **로드되고 요소가 주입되는지**. 빠르고 CI 무설치.
   ※ 한계: jsdom CSSOM은 `all:initial` 숏핸드를 확장하지 않는다 → 오너가 겪은 '위치가 삼켜지는' 현상은
   **jsdom으로 재현 불가**. 그래서 아래 2)가 진짜 게이트다(이 한계를 계약으로 명시해 착시를 막는다).
2) 실브라우저(Playwright) — `getComputedStyle(fab).position === 'fixed'`. 여기서만 all:initial 상호작용이 진짜로 검증된다.

부수 발견(같이 고침): `_playwright_ok()`가 /opt/pw-browsers 글롭만 봐서 **GitHub CI에선 항상 skip**이었다.
CLAUDE.md는 이 하네스를 'CI 게이트'라 기술했지만 실제로 CI에서 돈 적이 없다 → CI에 chromium 설치 + 경로 인정.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

EXT = Path("extensions/chrome-collector")
CS = (EXT / "content_script.js").read_text(encoding="utf-8")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
_NODE = shutil.which("node")


# ── 소스 계약: 위치 재확정(P0-A 근치) ────────────────────────────────────
def test_position_pinned_after_csstext():
    """`all:initial !important`와 같은 블록에 위치를 두면 숏핸드 확장 순서에 따라 삼켜질 수 있다
    → cssText **배정 후** setProperty(important)로 재확정하는 이중 안전장치가 있어야 한다."""
    assert "function _kgpPinFixed(" in CS
    # FAB·벌크바 둘 다 재확정을 거친다(둘 다 오너 증상 대상).
    assert '_kgpPinFixed(btn, { right: "16px", top: "calc(50% - 24px)" });' in CS
    assert '_kgpPinFixed(bar, { top: "12px", left: "50%", transform: "translateX(-50%)" });' in CS
    # 재확정은 setProperty(...,'important') 경로(_kgpPos)를 써야 격리를 이긴다.
    assert 'el.style.setProperty(prop, val, "important")' in CS


def test_style_injection_helper_present():
    assert "function kgpEnsureStyles(" in CS
    assert 'st.id = "kgp-style"' in CS


def test_harness_script_exists():
    assert Path("scripts/inject_harness.js").exists()


@pytest.mark.skipif(_NODE is None, reason="node 미설치")
def test_injection_harness_runs():
    """jsdom 주입 하네스 실행 — 상세 FAB·스타일 케이스는 반드시 그린.

    목록(라쿠텐 검색) 케이스는 v84 STEP2에서 고친다 → 지금은 **알려진 실패**로 명시(가짜 그린 금지).
    """
    r = subprocess.run([_NODE, "scripts/inject_harness.js"], capture_output=True, text=True, timeout=180)
    out = (r.stdout or "") + (r.stderr or "")
    if "jsdom 미설치" in out:
        pytest.skip("jsdom 미설치(로컬 전용 하네스)")
    assert "✓ 상세(라쿠텐) — FAB 주입" in out, out
    assert "✓ 상세 — 스타일 주입(kgpEnsureStyles)" in out, out


def test_jsdom_limitation_is_documented():
    """jsdom이 all:initial을 확장하지 않는다는 한계가 하네스에 명시돼 있어야 한다(착시 방지)."""
    h = Path("scripts/inject_harness.js").read_text(encoding="utf-8")
    assert "all:initial" in h


# ── 실브라우저 계약(진짜 게이트) ──────────────────────────────────────────
def _pw_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    if glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"):
        return True
    cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or (Path.home() / ".cache" / "ms-playwright"))
    return cache.is_dir() and any(cache.glob("chromium-*"))


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_fab_computed_position_is_fixed_in_real_browser():
    """오너 증상 직결 계약: 실 브라우저에서 FAB의 **computed** position이 fixed여야 한다.

    all:initial 격리가 위치를 삼키면 static이 되고 → 화면에서 사라진다(정확히 오너가 본 상태).
    """
    from playwright.sync_api import sync_playwright

    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    html = (
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>t</title></head>"
        "<body><h1 class='item_name'>테스트 상품</h1><div class='item_price'>3,980円</div></body></html>"
    )
    scripts = [j for cs in MANIFEST["content_scripts"] if (cs.get("world") or "ISOLATED") == "ISOLATED" for j in cs["js"]]
    code = "\n;\n".join((EXT / s).read_text(encoding="utf-8") for s in scripts)
    stub = """
      window.chrome = {
        runtime: { id: 'x', lastError: null, getManifest: () => ({version:'0'}), getURL: (p)=>p,
                   sendMessage: (m,cb)=>{ cb && setTimeout(()=>cb({ok:false}),0); }, onMessage:{addListener(){}} },
        storage: { local: { get:(k,cb)=>cb&&cb({}), set:()=>{} }, sync:{ get:(k,cb)=>cb&&cb({}) },
                   onChanged:{ addListener(){} } },
      };
    """
    with sync_playwright() as pw:
        opts = {"executable_path": hits[0]} if hits else {}
        px = os.environ.get("HTTPS_PROXY")
        if px:
            opts["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**opts)
        page = b.new_context().new_page()
        page.route("**/*", lambda route: (
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            if route.request.url.startswith("https://item.rakuten.co.jp/") else route.abort()))
        page.goto("https://item.rakuten.co.jp/tsumugi/bag-ai-01/", wait_until="domcontentloaded")
        page.evaluate(stub)
        page.evaluate(code)
        page.wait_for_timeout(300)
        got = page.evaluate("""() => {
            const el = document.getElementById('kgp-collect-fab');
            if (!el) return { exists: false };
            const cs = getComputedStyle(el);
            return { exists: true, position: cs.position, zIndex: cs.zIndex, display: cs.display };
        }""")
        b.close()
    assert got["exists"], "FAB 미주입 — 화면에 수집 버튼이 없다"
    assert got["position"] == "fixed", f"FAB computed position={got['position']} (오너 증상 재현)"
    assert got["display"] != "none", got


def test_ci_actually_installs_browser():
    """게이트가 '있는 척'만 하지 않도록 — CI가 chromium을 실제로 설치하는지."""
    ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "playwright install" in ci, "CI가 브라우저를 설치하지 않으면 실브라우저 계약은 영구 skip이다"
    dev = Path("requirements-dev.txt").read_text(encoding="utf-8")
    assert "playwright" in dev
