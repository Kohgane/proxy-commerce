"""tests/test_v72b_ali_button_isolation.py — v72b STEP4: 알리 호버 버튼 자식 격리 + 확장 신선도 배너.

증상: 알리에서 '수집' 호버 알약이 여전히 과대. 근본: v72 STEP4는 버튼 '루트'만 all:initial 격리했으나
자식 span(아이콘·라벨)은 사이트의 **직접** `span{…!important}` 규칙에 노출 → auto-width 폭주. 수리:
자식 span에도 all:initial+고정 !important를 인라인으로 박아 캐스케이드 최상위로 차단. + 콘솔에 확장
신선도 배너(content_script가 각인한 설치 버전 vs 최신 대조 → 구버전이면 재로딩 안내).
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
HISTORY = Path("src/seller_console/templates/collect_history.html").read_text(encoding="utf-8")
VIEWS = Path("src/seller_console/views.py").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.118"


# ── source-contract: 자식 격리 + 버전 각인 + 배너 ──
def test_quick_button_children_isolated_source():
    # 자식 span 헬퍼가 _KGP_RESET(all:initial) + 고정 !important를 인라인으로.
    assert "function _kgpQuickIconSpan()" in CS
    assert "function _kgpQuickLabelSpan(text)" in CS
    seg = CS.split("function _kgpQuickIconSpan()")[1].split("function kgpQuickBtnStyle")[0]
    assert "_KGP_RESET +" in seg
    assert "font:800 " in seg and "!important" in seg
    assert 'class="kgp-q-label"' in seg
    # 호버 버튼 innerHTML이 헬퍼 사용(원시 span 미사용).
    assert "q.innerHTML = _kgpQuickIconSpan() + _kgpQuickLabelSpan(" in CS


def test_ext_version_stamped_source():
    # content_script가 설치 버전을 documentElement에 각인.
    assert "_kgpStampExtVersion" in CS
    assert 'setAttribute("data-kgp-ext"' in CS
    assert "getManifest().version" in CS or "getManifest && chrome.runtime.getManifest().version" in CS


def test_console_freshness_banner_source():
    # 뷰가 최신 버전 주입 + 템플릿 배너 + 대조 로직.
    assert "expected_ext_version=_chrome_extension_version()" in VIEWS
    assert 'id="extFreshBanner"' in HISTORY
    assert 'data-expected="{{ expected_ext_version }}"' in HISTORY
    assert "getAttribute('data-kgp-ext')" in HISTORY
    assert "재로딩" in HISTORY                        # 구버전 안내
    assert "최신 버전입니다" in HISTORY               # 최신 확인(이모지 금지 — bi-check-circle 아이콘)


# ── node: 배너 버전 비교(semver-ish, 1.5.9 < 1.5.89) ──
@pytest.mark.skipif(shutil.which("node") is None, reason="node 미설치")
def test_banner_version_compare_node():
    m = re.search(r"function cmp\(a, b\) \{.*?\n    \}", HISTORY, re.S)
    assert m, "cmp 함수 추출 실패"
    harness = (
        m.group(0) + "\n"
        "var out={a:cmp('1.5.9','1.5.118'), b:cmp('1.5.118','1.5.118'), c:cmp('1.6.0','1.5.118')};\n"
        "console.log(JSON.stringify(out));\n"
    )
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    f.write(harness); f.close()
    try:
        r = subprocess.run(["node", f.name], capture_output=True, text=True, timeout=15)
        assert r.returncode == 0, r.stderr
        out = json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(f.name).unlink()
    assert out["a"] == -1        # 1.5.9 < 1.5.118(구버전 감지 — 숫자 비교, 문자열 아님)
    assert out["b"] == 0         # 동일 = 최신
    assert out["c"] == 1         # 1.6.0 > 1.5.118


# ── Playwright: 적대적 직접 span 규칙 하에서 호버 라벨이 우리 스펙 유지 ──
def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


_CHROME_STUB = """
window.chrome = {
  runtime: { id: 'x', onMessage: { addListener(){} }, sendMessage(){}, getURL: u => u, lastError: null,
             getManifest: () => ({ version: '1.5.118' }) },
  storage: {
    local: { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } },
    sync:  { get: (k, cb) => cb && cb({}), set(){}, onChanged: { addListener(){} } }
  }
};
"""

# 적대적 사이트 CSS(알리식) — **직접 span 규칙**: 자식 span 폰트·폭·라인높이를 !important로 폭주시킨다.
#   버튼 루트만 all:initial이면 자식 span은 이 규칙에 직접 매칭 → 폭주. 자식도 격리해야 방어.
_HOSTILE = ("<style>span{font-size:80px !important;width:600px !important;"
            "line-height:5 !important;letter-spacing:9px !important;}</style>")


def _cards_html():
    c = ""
    for i in range(1, 6):
        c += ('<div class="card"><a href="/item/%d.html"><img width="200" height="200" src="https://ae01.alicdn.com/c%d.jpg"></a>'
              '<div class="title">상품 %d</div><div class="price">US $12.30</div></div>' % (i, i, i))
    return c


SITES = [
    ("aliexpress", "https://www.aliexpress.com/w/wholesale-desk.html"),
    ("temu",       "https://www.temu.com/search_result.html?q=desk"),
    ("amazon",     "https://www.amazon.com/s?k=desk"),
]


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
@pytest.mark.parametrize("site,url", SITES, ids=[s[0] for s in SITES])
def test_hover_button_label_isolated_from_direct_span_rule(site, url):
    """3사이트 모두: 적대적 `span{80px!important}` 하에서 호버 라벨 = 우리 스펙 15px·버튼 폭 봉인."""
    from playwright.sync_api import sync_playwright

    html = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">' + _HOSTILE +
            '</head><body><div class="grid">' + _cards_html() + '</div></body></html>')
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()
        page.add_init_script(_CHROME_STUB)

        def handler(route):
            if route.request.url.split("#")[0] == url:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            else:
                route.abort()
        page.route("**/*", handler)
        page.goto(url, wait_until="domcontentloaded")
        page.evaluate("(cs)=>{ (0,eval)(cs); }", CS)
        page.wait_for_timeout(800)
        info = page.evaluate("""() => {
            const q = document.querySelector('.kgp-card-quick');
            if (!q) return { quick: false };
            const lbl = q.querySelector('.kgp-q-label');
            const lcs = lbl ? getComputedStyle(lbl) : null;
            return {
                quick: true,
                labelFont: lcs ? lcs.fontSize : null,
                btnW: q.getBoundingClientRect().width,
                btnH: q.getBoundingClientRect().height,
            };
        }""")
        b.close()
    assert info["quick"], (site, info)
    # 라벨 폰트 = 우리 스펙 15px(사이트 80px 직접 규칙 무력화 — 자식 격리 증명).
    assert info["labelFont"] == "15px", (site, info)
    # 버튼 폭이 사이트 width:600px 오염으로 폭주하지 않음(봉인).
    assert info["btnW"] < 220, (site, info)
    # 버튼 높이가 line-height:5 오염으로 부풀지 않음(max-height 44 클램프).
    assert info["btnH"] <= 46, (site, info)
