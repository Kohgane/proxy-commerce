"""tests/test_v75_diag_bundle.py — v75 STEP3: 스냅샷 제출 경로 정식화(진단 파일).

확장 스냅샷 버튼 옆 '이 페이지 수집이 이상해요' → 스냅샷 HTML + 추출 결과 + 감지 로그를 하나의 진단
파일로 다운로드. 파일 하나(HTML=픽스처 + 임베드 JSON=실제 추출 결과)만 전달하면 하네스가 그대로 재현.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
POPUP_JS = Path("extensions/chrome-collector/popup.js").read_text(encoding="utf-8")
POPUP_HTML = Path("extensions/chrome-collector/popup.html").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.110"


# ── source-contract: 진단 번들 메시지 + 팝업 버튼/다운로드 ──
def test_diag_bundle_source():
    assert 'msg.action === "kgpDiagBundle"' in CS       # content_script 핸들러
    assert "window.kgpExtractProduct()" in CS           # 추출 결과 포함
    assert "detection" in CS and "ext_version" in CS    # 감지 로그·버전 포함
    # 팝업: '이 페이지 수집이 이상해요' 버튼 + 진단 파일 다운로드.
    assert 'id="btnDiagBundle"' in POPUP_HTML
    assert "이 페이지 수집이 이상해요" in POPUP_HTML
    assert 'action: "kgpDiagBundle"' in POPUP_JS
    assert 'id="kgp-diagnostic"' in POPUP_JS             # 스냅샷 HTML에 추출결과 JSON 임베드
    assert 'kgp-diagnostic-' in POPUP_JS                 # 파일명
    assert "URL.createObjectURL" in POPUP_JS


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
ALI = Path("fixtures/realpages/ali-detail.html").read_text(encoding="utf-8")


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
def test_diag_bundle_data_is_reproducible():
    """진단 번들이 묶는 두 데이터(스냅샷 HTML + 실제 추출 결과)가 산출 가능 → 파일 하나로 하네스 재현.
    임베드 JSON을 다시 파싱해 스냅샷 HTML과 추출 결과가 한 파일에서 복원됨을 실증."""
    from playwright.sync_api import sync_playwright
    url = "https://www.aliexpress.com/item/1005006620123.html"
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
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=ALI)
            else:
                route.abort()
        page.route("**/*", handler)
        page.goto(url, wait_until="domcontentloaded")
        # 확장 없이 순수 추출기만 eval(네비게이션 유발 코드 회피) → 번들 데이터(html+extracted) 산출.
        bundle = page.evaluate("""(ex) => {
            (0, eval)(ex);
            const extracted = window.kgpExtractProduct();
            const html = '<!doctype html>\\n' + document.documentElement.outerHTML;
            // 팝업과 동일 방식으로 임베드 → 한 파일.
            const diag = { url: location.href, extracted: extracted, ext_version: 'x' };
            const embed = '\\n<script type="application/json" id="kgp-diagnostic">'
                + JSON.stringify(diag).replace(/<\\/script>/gi, '<\\\\/script>') + '<\\/script>\\n';
            const file = html + embed;
            // 재파싱: 임베드 블록에서 추출 결과 복원.
            const m = file.match(/<script type="application\\/json" id="kgp-diagnostic">([\\s\\S]*?)<\\/script>/);
            const reparsed = m ? JSON.parse(m[1].replace(/<\\\\\\/script>/gi, '<\\/script>')) : null;
            return { hasHtml: file.indexOf('<!doctype') === 0, price: extracted.price,
                     reparsedPrice: reparsed && reparsed.extracted && reparsed.extracted.price,
                     fixtureUsable: file.indexOf('runParams') > 0 };
        }""", EX)
        b.close()
    assert bundle["hasHtml"] is True                       # 파일이 유효 HTML(픽스처로 바로 사용)
    assert bundle["fixtureUsable"] is True                 # 스냅샷 상태 JSON(runParams) 보존 → 추출 재현
    assert bundle["price"] == "6620"                       # 실제 추출 결과
    assert bundle["reparsedPrice"] == "6620"               # 임베드에서 추출 결과 복원(대조용) — 파일 하나로 재현
