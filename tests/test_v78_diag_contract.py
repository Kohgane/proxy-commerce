"""tests/test_v78_diag_contract.py — v78 STEP5: 진단 extracted를 공식 계약층으로.

오너가 확장 팝업 '이 페이지 수집이 이상해요'로 내려받는 진단 파일(kgp-diagnostic-*.html)은
스냅샷 HTML + 임베드 JSON(`<script id="kgp-diagnostic">{url, extracted, ...}</script>`)이다.
`extracted`는 캡처 시점 kgpExtractProduct() 결과.

STEP5: 하네스 어서션을 **진단 extracted 포맷과 동일 스키마**로 통일 → 오너가 그 파일 하나를
`fixtures/realpages/diag/`에 넣으면 곧바로 회귀 테스트가 된다. 하네스는:
  ① 파일의 임베드 JSON에서 기록된 extracted(계약 스냅샷)를 읽고,
  ② 같은 HTML을 재-추출한 뒤,
  ③ **계약 필드(진단 extracted 스키마 그대로)가 일치**하는지 대조.
즉 '이 HTML은 이 결과로 계속 추출돼야 한다'를 오너 파일 자체가 못박는다.
"""
from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

import pytest

EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
DIAG_DIR = Path("fixtures/realpages/diag")
# v86-H: 계약 파일 = 진단 임베드(kgp-diagnostic)가 있는 '진단 파일'만. 팝업 '진단 스냅샷 저장'이 내리는
#   순수 DOM 스냅샷(kgp-snapshot-*, 임베드 없음)은 계약 baseline이 없으므로 회귀 계약 대상이 아니다
#   (그 파일들은 realpages 하네스 픽스처용). embed 유무로 필터 → 스냅샷 오글로빙 제외.
def _has_embed(p):
    try:
        return 'id="kgp-diagnostic"' in Path(p).read_text(encoding="utf-8")
    except Exception:
        return False
DIAG_FILES = sorted(f for f in glob.glob(str(DIAG_DIR / "*.html")) if _has_embed(f))
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))

# 진단 임베드 블록 파서(팝업과 동일 이스케이프 규칙: </script> → <\/script>).
_EMBED_RE = re.compile(
    r'<script type="application/json" id="kgp-diagnostic">([\s\S]*?)</script>', re.I)


def _parse_diag(path):
    txt = Path(path).read_text(encoding="utf-8")
    m = _EMBED_RE.search(txt)
    assert m, ("진단 임베드(kgp-diagnostic) 블록 없음", path)
    payload = m.group(1).replace("<\\/script>", "</script>")
    return json.loads(payload), txt


def _contract_view(e):
    """진단 extracted 스키마에서 결정적(재현 가능) 계약 필드만 투영 — 하네스 어서션 스키마 = 진단 스키마."""
    e = e or {}
    return {
        "title": (e.get("title") or "").strip(),
        "price": e.get("price") or "",
        "currency": e.get("currency") or "",
        "price_status": e.get("price_status") or "",
        "field_sources": e.get("field_sources") or {},
        "desc_source": e.get("desc_source") or "",
        "options": [{"name": o.get("name"), "values": list(o.get("values") or [])}
                    for o in (e.get("options") or [])],
        "skus_len": len(e.get("skus") or []),
        "images_len": len(e.get("images") or []),
        "detail_images_len": len(e.get("detail_images") or []),
        "reviews_len": len(e.get("reviews") or []),
        "rating": e.get("rating") or "",
        "review_count": e.get("review_count") or "",
    }


def test_manifest_version_pinned():
    # STEP5는 확장 런타임 무변경(하네스·픽스처만) → 버전 유지(1.5.120).
    assert MANIFEST["version"] == "1.5.137"


def test_diag_dir_and_readme():
    # 최소 1개 진단 파일 + README에 drop-in 규약 명시.
    assert DIAG_FILES, "fixtures/realpages/diag/*.html 없음(진단 계약 파일)"
    readme = (DIAG_DIR / "README.md")
    assert readme.exists(), "diag/README.md 없음"
    txt = readme.read_text(encoding="utf-8")
    assert "kgp-diagnostic" in txt and "회귀" in txt


def test_contract_view_schema_matches_extracted_fields():
    """계약 뷰 키가 진단 extracted 필드명과 동일(스키마 통일) — 임의 별칭 아님."""
    diag, _ = _parse_diag(DIAG_FILES[0])
    e = diag.get("extracted") or {}
    view = _contract_view(e)
    # 투영 키는 전부 extracted에 실존하는 필드(또는 그 길이 파생) — 스키마 일치.
    for k in ("title", "price", "currency", "price_status", "field_sources", "desc_source",
              "options", "rating", "review_count"):
        assert k in e, ("진단 extracted에 계약 필드 없음", k)
    for k in ("skus", "images", "detail_images", "reviews"):
        assert k in e, ("진단 extracted에 리스트 필드 없음", k)
    assert view  # 투영 성공


def _playwright_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"))


def _reextract(url, body):
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
            if r.request.url.split("#")[0] == url:
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(url, wait_until="domcontentloaded")
        res = page.evaluate("(ex)=>{ (0,eval)(ex); return window.kgpExtractProduct(); }", EX)
        b.close()
    return res


@pytest.mark.skipif(not _playwright_ok(), reason="Playwright/chromium 미설치")
@pytest.mark.parametrize("path", DIAG_FILES, ids=[Path(f).name for f in DIAG_FILES])
def test_diag_bundle_is_regression_contract(path):
    """오너 진단 파일 = 회귀 테스트: 임베드된 extracted(계약 스냅샷) == 같은 HTML 재-추출(계약 뷰)."""
    diag, full = _parse_diag(path)
    recorded = diag.get("extracted") or {}
    url = diag.get("url") or "https://example.com/diag"
    # 진단 임베드(우리 메타)는 페이지 콘텐츠가 아니다 → 재-추출 전에 제거(추출기의 application/json 워크가
    #   임베드 blob을 페이지 데이터로 오인하지 않도록). 남는 건 오너가 캡처한 스냅샷 HTML 그대로.
    snapshot = _EMBED_RE.sub("", full)
    reextracted = _reextract(url, snapshot)
    got = _contract_view(reextracted)
    want = _contract_view(recorded)
    assert got == want, {"fixture": Path(path).name, "want": want, "got": got}
