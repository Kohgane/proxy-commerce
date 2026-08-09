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


def _pw_executable():
    """샌드박스 사전설치 크로미움 경로. 없으면 None → Playwright 기본 설치 경로 사용."""
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return hits[0] if hits else None


def _playwright_ok():
    """v84: 예전엔 /opt/pw-browsers 글롭만 봐서 **GitHub CI에선 항상 skip**이었다(= 이 하네스가 CI 게이트라는
    CLAUDE.md 기술이 실제로는 거짓). CI는 `playwright install chromium`으로 기본 경로(~/.cache/ms-playwright)에
    깔리므로 그 경우도 인정한다. 둘 다 없으면 정직하게 skip."""
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    if _pw_executable():
        return True
    cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or (Path.home() / ".cache" / "ms-playwright"))
    return cache.is_dir() and any(cache.glob("chromium-*"))


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
    assert mani["version"] == "1.5.141"


def _extract_via_browser(expected):
    from playwright.sync_api import sync_playwright

    name = Path(expected).name.replace(".expected.json", "")
    spec = json.loads(Path(expected).read_text(encoding="utf-8"))
    html = (FIX_DIR / (name + ".html")).read_text(encoding="utf-8")
    url = spec["url"]
    exe = _pw_executable()
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        opts = {"executable_path": exe} if exe else {}   # v84: CI 기본 설치 경로면 Playwright가 알아서 찾는다
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
    # v76 STEP1: 제목에 사이트명 0(접두/접미 새니타이저) — 명시 목록 + 공통 사이트명 셋.
    _title = r.get("title") or ""
    for sub in (spec.get("title_excludes") or []):
        assert sub not in _title, ("제목 사이트명 오염", sub, _title, ctx)
    if "price" in spec:
        assert (r.get("price") or "") == spec["price"], ctx
    if "currency" in spec:
        assert (r.get("currency") or "") == spec["currency"], ctx
    # v83 STEP1: 통화 사다리 근거(tier1|domain|domain+symbol|symbol|locale) + 번역 DOM 플래그.
    if "currency_source" in spec:
        assert (r.get("currency_source") or "") == spec["currency_source"], \
            ("통화 근거 불일치", r.get("currency_source"), spec["currency_source"], ctx)
    if "translated_dom" in spec:
        assert bool(r.get("translated_dom")) is bool(spec["translated_dom"]), \
            ("번역 DOM 판정 불일치", r.get("translated_dom"), ctx)
    # v78 STEP4: 가격 출처(어댑터 패리티) — 아마존 buybox 어댑터 매치 시 field_sources.price=buybox(모순 해소).
    if "price_source" in spec:
        assert (r.get("field_sources") or {}).get("price") == spec["price_source"], \
            ("가격 출처 불일치", (r.get("field_sources") or {}).get("price"), spec["price_source"], ctx)

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
    # v83 STEP2/3: 옵션·sku 최소 개수(알리 소생) + 어떤 축에도 있으면 안 되는 값(색상 '1').
    if "options_min" in spec:
        assert len(r.get("options") or []) >= spec["options_min"], ("옵션 부족", r.get("options"), ctx)
    if "skus_min" in spec:
        assert len(r.get("skus") or []) >= spec["skus_min"], ("sku 부족", len(r.get("skus") or []), ctx)
    for bad in (spec.get("option_values_exclude") or []):
        for o in (r.get("options") or []):
            assert bad not in (o.get("values") or []), ("옵션 금지값", o.get("name"), bad, ctx)

    imgs = r.get("images") or []
    if "images_min" in spec:
        assert len(imgs) >= spec["images_min"], (len(imgs), ctx)
    if "images_max" in spec:
        assert len(imgs) <= spec["images_max"], (len(imgs), ctx)
    for sub in (spec.get("images_exclude_substr") or []):
        assert not any(sub in u for u in imgs), (sub, imgs, ctx)

    # v76 STEP5: 상세이미지(A+/설명/장식 영역) — 갤러리와 별도 버킷. 픽스처별 di 기준치.
    det = r.get("detail_images") or []
    if "detail_images_min" in spec:
        assert len(det) >= spec["detail_images_min"], ("상세이미지 부족", len(det), det, ctx)
    if "detail_images_max" in spec:
        assert len(det) <= spec["detail_images_max"], ("상세이미지 초과", len(det), det, ctx)
    for sub in (spec.get("detail_images_exclude_substr") or []):
        assert not any(sub in u for u in det), ("상세이미지 오염", sub, det, ctx)
    # 갤러리↔상세 상호배타(같은 URL 양쪽 중복 금지).
    if spec.get("detail_images_min") or spec.get("images_exclude_substr"):
        _dupe = set(imgs) & set(det)
        assert not _dupe, ("갤러리·상세 중복", _dupe, ctx)

    if "description_contains" in spec:
        assert spec["description_contains"] in (r.get("description") or ""), ctx

    # v78 STEP3: 상세설명 소스 사다리(어댑터>ldjson>meta) — meta SEO 접두 금지 + 어댑터 불릿 포함.
    _desc = r.get("desc_text") or r.get("description") or ""
    for sub in (spec.get("desc_text_excludes") or []):
        assert not _desc.lstrip().startswith(sub) and sub not in _desc[:40], ("상세설명 meta SEO 오염", sub, _desc[:60], ctx)
    for sub in (spec.get("desc_text_contains") or []):
        assert sub in _desc, ("상세설명에 어댑터 불릿 없음", sub, _desc[:80], ctx)
    if "desc_source" in spec:
        assert (r.get("desc_source") or "") == spec["desc_source"], ("desc_source 불일치", r.get("desc_source"), ctx)
    # v83 STEP2/3: 상세설명 오염 금지(판매자 블록·HTML 주석·CSS 조각) + 스펙 표 위생(프로모·공유링크·날짜).
    for sub in (spec.get("desc_excludes") or []):
        assert sub not in _desc, ("상세설명 오염", sub, _desc[:120], ctx)
    for sub in (spec.get("specs_exclude_substr") or []):
        for sp in (r.get("detail_specs") or []):
            assert sub not in str(sp.get("k") or "") and sub not in str(sp.get("v") or ""), \
                ("detail_specs 오염", sub, sp, ctx)

    # v76 STEP6: 리뷰(페이지 내 존재분·DOM 폴백) — 개수 기준 + 본문 텍스트 존재(빈 리뷰 금지).
    revs = r.get("reviews") or []
    if "reviews_min" in spec:
        assert len(revs) >= spec["reviews_min"], ("리뷰 부족", len(revs), ctx)
        assert all((rv.get("text") or "").strip() for rv in revs), ("빈 리뷰", revs, ctx)
    if "reviews_contains" in spec:
        assert any(spec["reviews_contains"] in (rv.get("text") or "") for rv in revs), (spec["reviews_contains"], revs, ctx)

    # v78 STEP2: 리뷰 메타 정직 — rating은 (1,5] 또는 없음(0·1 더미 금지), review_count는 실 리뷰 수 이상.
    _rating = (r.get("rating") or "").strip()
    # v83 STEP4: 리뷰가 있는데 rating 공란이던 텔레메트리 결손 — DOM 집계 평점으로 채웠는지 계약.
    if "rating" in spec:
        assert _rating == spec["rating"], ("rating 불일치", _rating, spec["rating"], ctx)
    if spec.get("rating_no_dummy"):
        assert _rating not in ("0", "1"), ("rating 더미(0·1) 저장!", _rating, ctx)
        if _rating:
            assert 1.0 < float(_rating) <= 5.0, ("rating 범위 밖!", _rating, ctx)
    if spec.get("review_count_gte_reviews"):
        _rc = (r.get("review_count") or "").strip()
        if _rc:
            assert int(_rc) >= len(revs), ("review_count < 실제 리뷰 수(스테일)!", _rc, len(revs), ctx)
