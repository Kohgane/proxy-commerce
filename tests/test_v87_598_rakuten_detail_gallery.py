"""tests/test_v87_598_rakuten_detail_gallery.py — 백로그 #598: 라쿠텐 상세 갤러리 1장 → n장.

프리즈 해제: 실 상세 스냅샷(fixtures/realpages/diag/kgp-snapshot-item-rakuten*.html, TSUMUGI 상세).
근원(실크롬 실측): 라쿠텐은 **같은 상품 이미지 경로를 여러 CDN 미러 호스트로 서빙**한다
  (og=shop.r10s.jp, 갤러리=image.rakuten.co.jp·tshop.r10s.jp — path 동일 `/receno/…/tsumugi-tama/img`).
  v80 STEP3 폴더 스코프의 `_rakutenFolder`가 폴더 키에 **호스트를 포함**해, og(한 호스트) 폴더와 갤러리(다른
  미러) 폴더가 갈려 (c) CDN 스윕이 갤러리를 전량 제외 → **1장**에 그쳤다.
수리: ① `_rakutenFolder`를 **경로(path)만**으로 판정(미러 호스트 무관, 타상품 경로는 여전히 상이 → 교차 오염 0).
      ② `hiRes`가 라쿠텐 `?_ex=`만 지우고 `&s=0&r=1` 고아를 남겨 같은 이미지가 다른 URL로 중복되던 것 →
         라쿠텐/r10s 이미지는 확장자 뒤 쿼리 통째 제거(원본 해상도 + 쿼리 변이 dedupe).
계약: 갤러리 ≥8장(수리 전 1) · 전부 현 상품 폴더(교차 오염 0) · 호스트무관 중복 0 · 전부 라쿠텐 CDN.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

from tests import _pw

EXT = Path("extensions/chrome-collector")
EXTRACTOR = (EXT / "kgp-extractor.js").read_text(encoding="utf-8")
MANIFEST = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
_FIX = glob.glob("fixtures/realpages/diag/kgp-snapshot-item-rakuten*.html")
_URL = "https://item.rakuten.co.jp/receno/tsumugi-tama-s/"


def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.149"


def test_source_contract():
    # ① 폴더 키를 경로만으로(호스트 제거) → CDN 미러 호스트 변이에 무관.
    seg = EXTRACTOR.split("function _rakutenFolder")[1].split("\n  }")[0]
    assert 'replace(/^https?:\\/\\/[^\\/]+/i, "")' in seg, "폴더 키에서 호스트를 제거하지 않는다(미러 호스트 전량 제외)"
    # ② hiRes: 라쿠텐/r10s 이미지 확장자 뒤 쿼리 제거(&s=0&r=1 고아 dedupe).
    assert 'r10s\\.jp|rakuten\\.co\\.jp' in EXTRACTOR
    assert '(\\.(?:jpg|jpeg|png|gif|webp))(?:[?&][^\\/]*)?$' in EXTRACTOR


def _pw_ok():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return bool(_pw.chromium_hits())


_INJECT = r"""(code)=>{ window.module={exports:{}}; (0,eval)(code);
  const r = window.kgpExtractProduct ? window.kgpExtractProduct({}) : null;
  const imgs = (r && r.images) || [];
  const path = u => String(u).replace(/^https?:\/\/[^\/]+/i, '').split('?')[0].split('&')[0];
  const folder = u => path(u).replace(/\/[^\/]*$/, '');
  const keys = imgs.map(path);
  const RAK = /(thumbnail|image)\.rakuten\.co\.jp|r\.r10s\.jp|tshop\.r10s\.jp/i;
  return {
    n: imgs.length,
    dup: keys.length - new Set(keys).size,
    folders: Array.from(new Set(imgs.map(folder))),
    nonRakuten: imgs.filter(u => !RAK.test(u)).length,
    images: imgs,
  };
}"""
_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="600" height="600">'
        '<rect width="600" height="600" fill="#ccc"/></svg>')


@pytest.mark.skipif(not _FIX, reason="라쿠텐 상세 스냅샷 픽스처 없음")
@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_rakuten_detail_gallery_multi_realpage():
    HTML = Path(_FIX[0]).read_text(encoding="utf-8", errors="ignore")
    from playwright.sync_api import sync_playwright
    exe = _pw.chromium_hits()[0]
    with sync_playwright() as pw:
        px = os.environ.get("HTTPS_PROXY")
        o = {"executable_path": exe}
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()

        def h(route):
            u = route.request.url.split("#")[0]
            if u.rstrip("/") == _URL.rstrip("/"):
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=HTML)
            elif route.request.resource_type == "image":
                route.fulfill(status=200, content_type="image/svg+xml", body=_SVG)
            else:
                route.abort()
        page.route("**/*", h)
        page.goto(_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        r = page.evaluate(_INJECT, EXTRACTOR)
        b.close()
    # 수리 전 1장 → 갤러리 다장(캐러셀 전량).
    assert r["n"] >= 8, ("라쿠텐 상세 갤러리가 여전히 소수", r)
    # 호스트 무관 중복 0(미러/쿼리 변이 dedupe).
    assert r["dup"] == 0, ("미러 호스트/쿼리 변이가 중복 저장됨", r)
    # 교차 오염 0 — 전부 현 상품 폴더 하나(타상품 폴더 혼입 없음).
    assert len(r["folders"]) == 1, ("여러 폴더(타상품) 혼입", r)
    assert "/receno/cabinet/bowl/tsumugi-tama/img" in r["folders"][0], r
    # 전부 라쿠텐 CDN.
    assert r["nonRakuten"] == 0, ("라쿠텐 CDN 아닌 이미지 혼입", r)
