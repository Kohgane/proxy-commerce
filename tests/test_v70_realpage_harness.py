"""tests/test_v70_realpage_harness.py — v70 STEP5: 실페이지 추출 하네스(CI 게이트).

fixtures/realpages/<name>.html 에 라이브 kgp-extractor.js(=run.js 코어)를 **실 크로미움 DOM**에 물려
kgpExtractProduct() 결과를 <name>.expected.json 스냅샷과 비교한다. 추출 로직을 바꾸면 이 하네스가
통과해야 한다(CLAUDE.md 규약). 호스트로 추출 분기 결정(amazon.* → 갤러리 스코프) 위해 page.route로
가짜 URL을 픽스처로 채운다(네트워크 없이 렌더된 DOM).
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
FIX_DIR = Path("fixtures/realpages")
FIXTURES = sorted(glob.glob(str(FIX_DIR / "*.expected.json")))


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


def test_fixtures_present():
    # 최소 1개 픽스처가 있어야 하네스가 의미 있는 게이트(합성 픽스처라도).
    assert FIXTURES, "fixtures/realpages/*.expected.json 없음"


def test_snapshot_infra_source_contract():
    import json as _json
    cs = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
    pj = Path("extensions/chrome-collector/popup.js").read_text(encoding="utf-8")
    ph = Path("extensions/chrome-collector/popup.html").read_text(encoding="utf-8")
    # content_script: 진단 스냅샷 핸들러(현재 DOM outerHTML 반환).
    assert 'msg.action === "kgpSnapshot"' in cs
    assert "document.documentElement.outerHTML" in cs
    # popup: 버튼 + sendMessage + blob 다운로드.
    assert 'id="btnSnapshot"' in ph
    assert '{ action: "kgpSnapshot" }' in pj and "URL.createObjectURL" in pj
    assert "kgp-snapshot-" in pj
    # 하네스 스크립트/픽스처/규약 존재.
    assert Path("scripts/extract_harness.js").exists()
    assert (FIX_DIR / "README.md").exists()
    assert "실페이지 하네스 통과 필수" in Path("CLAUDE.md").read_text(encoding="utf-8")
    # manifest bump.
    mani = _json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
    assert mani["version"] == "1.5.93"


def _extract_via_browser(expected):
    from playwright.sync_api import sync_playwright

    name = Path(expected).name.replace(".expected.json", "")
    spec = json.loads(Path(expected).read_text(encoding="utf-8"))
    html = (FIX_DIR / (name + ".html")).read_text(encoding="utf-8")
    url = spec["url"]
    exe = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        opts = {"executable_path": exe}
        if px:
            opts["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**opts)
        page = b.new_context().new_page()

        def handler(route):
            if route.request.url.split("#")[0] == url:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            else:
                route.abort()   # 이미지 등 서브리소스 네트워크 차단(픽스처만)

        page.route("**/*", handler)
        page.goto(url, wait_until="domcontentloaded")
        result = page.evaluate("(ex)=>{ (0,eval)(ex); return window.kgpExtractProduct(); }", EX)
        b.close()
    return spec, result


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
@pytest.mark.parametrize("expected", FIXTURES, ids=[Path(f).name for f in FIXTURES])
def test_realpage_snapshot(expected):
    spec, r = _extract_via_browser(expected)
    ctx = {"fixture": Path(expected).name, "extracted": r}

    if "title_contains" in spec:
        assert spec["title_contains"] in (r.get("title") or ""), ctx
    if "price" in spec:
        assert (r.get("price") or "") == spec["price"], ctx
    if "currency" in spec:
        assert (r.get("currency") or "") == spec["currency"], ctx

    opts = {o["name"]: o["values"] for o in (r.get("options") or [])}
    # v71 STEP2 계약: 옵션 값에 "[object" 또는 "http"(URL) 오염 금지(모든 픽스처 공통).
    for o in (r.get("options") or []):
        for v in (o.get("values") or []):
            assert "[object" not in v and "http" not in v, ("옵션 오염", o.get("name"), v, ctx)
    for name, values in (spec.get("options") or {}).items():
        assert name in opts, ctx
        assert opts[name] == values, (name, opts.get(name), ctx)
    for name in (spec.get("no_option_names") or []):
        assert name not in opts, (name, ctx)

    imgs = r.get("images") or []
    if "images_min" in spec:
        assert len(imgs) >= spec["images_min"], (len(imgs), ctx)
    if "images_max" in spec:
        assert len(imgs) <= spec["images_max"], (len(imgs), ctx)
    for sub in (spec.get("images_exclude_substr") or []):
        assert not any(sub in u for u in imgs), (sub, imgs, ctx)

    if "description_contains" in spec:
        assert spec["description_contains"] in (r.get("description") or ""), ctx
