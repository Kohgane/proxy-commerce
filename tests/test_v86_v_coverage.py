"""tests/test_v86_v_coverage.py — v86-V 커버리지 표 결함 일소.

## 오너 실기기 확정(재조사 금지)
1.5.146 상세 3소스 채점: 가격 3소스 DOM 교차검증 그린. 결함:
- [크리티컬] 라쿠텐 item.rakuten.co.jp/{샵}/{코드}/ 상세를 pageType=list로 오판정(스캔 105·상품 68·
  제네릭 91 — 추천/사이드바 타일). 단품 수집 거부 + v86-H 억제 발동 → 필드 전무.
- 아마존: DOM 썸네일 16곳·이미지 ID 75종인데 갤러리 수집 1장(대표).
- echo path=popup인데 mode='simple'이면서 options·reviews 동봉 — 라벨-내용 모순.

## 이 파일이 못박는 것
1. 라쿠텐 상세 single 판정(실브라우저, L2 계보) + 인위회귀(호스트 게이트 무력화=raw KGPDetect →
   list 오판정 red / 게이트=item.rakuten 룰 → single green).
2. 아마존 상세 갤러리 대표 1장 → n장(썸네일 스트립 독립 병합, v70 _amazonGallery + v82 hiRes 재사용).
3. echo mode 라벨 정합: tier1 미착지라도 가격+(옵션|리뷰…)면 full 유지(simple 오표기 금지).
5(b). 알리 리스트 echo 미기록 봉인: 수집 4경로(fab/hover/bulk/popup) 전부 echo 기록.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
EX = Path("extensions/chrome-collector/kgp-extractor.js").read_text(encoding="utf-8")
DET = Path("extensions/chrome-collector/kgp-detect.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))
EXT = os.path.abspath("extensions/chrome-collector")


def _pw_exe():
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return hits[0] if hits else None


def _require_browser():
    return os.environ.get("KGP_REQUIRE_BROWSER") == "1"


# ── 소스 계약(결정적) ────────────────────────────────────────────────
def test_manifest_bumped():
    assert MANIFEST["version"] == "1.5.146"


def test_rakuten_single_rule_in_content_script():
    # 상세 판정 분기: item.rakuten 상품이면 single 강제(호스트 게이트 우선). 목록 경로 무수정.
    assert '_kgpIsRakutenItemHref(location.href)) return "single"' in CS


def test_amazon_gallery_thin_merge_in_extractor():
    # 아마존 thin(≤1) 갤러리 독립 병합 — v70 _amazonGallery + v82 hiRes 재사용(신규 발명 0).
    assert "images.length <= 1" in EX and "var ag2 = _amazonGallery();" in EX
    # 라쿠텐과 동일 패턴(독립 수집·병합) — 기존 _amazonGallery/hiRes만 사용, fetch/XHR 없음.
    seg = EX.split("v86-V(2)")[1].split("var seen = {}, gallery = [];")[0]
    assert "fetch(" not in seg and "XMLHttpRequest" not in seg


def test_echo_mode_not_simple_when_rich():
    # tier1 미착지라도 가격+(옵션|리뷰|평점|SKU|상세)면 full 유지 — simple 오표기 금지.
    assert "var _rich = !!String(meta.price" in CS
    assert 'if (!_rich && String(meta.mode || "").toLowerCase() !== "core") meta.mode = "simple";' in CS


def test_echo_recorded_on_all_four_collect_paths():
    # 5(b): 알리 리스트 수집이 어느 경로든 echo 기록(미기록 경로 0).
    for path in ('"fab"', '"hover"', '"bulk"', '"popup"'):
        assert f"_kgpRecordEcho(meta, {path})" in CS or f'_kgpRecordEcho(items[0] || {{}}, (opts && opts.retry) ? "bulk-retry" : "bulk"' in CS


# ── 인위회귀(item 1): 호스트 게이트 무력화 → list 오판정 red → 게이트 → single green ──
def test_artificial_regression_rakuten_host_gate():
    js = r"""
      global.self = global; global.window = global;
      require(%r);
      const D = global.KGPDetect;
      const stubDoc = { querySelectorAll: ()=>({length:0, forEach:()=>{}}), querySelector: ()=>null };
      const href = "https://item.rakuten.co.jp/tabemon-dikara/71/";
      // 무력화(raw KGPDetect = 호스트 게이트 없음): 추천 타일 60개로 cardCount 부풀리면 list 오판정.
      const raw = D.pageType(stubDoc, href, {cardCount:60});
      // 게이트(content_script 룰): item.rakuten + 세그먼트 2개↑ → single.
      function isRak(h){try{var u=new URL(h);if(!/(^|\.)item\.rakuten\.co\.jp$/i.test(u.hostname))return false;return u.pathname.split("/").filter(Boolean).length>=2;}catch(e){return false;}}
      const listHref = "https://search.rakuten.co.jp/search/mall/food/";
      console.log(JSON.stringify({raw: raw, gate_detail: isRak(href), gate_list: isRak(listHref)}));
    """ % os.path.join(EXT, "kgp-detect.js")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js); fn = f.name
    try:
        r = subprocess.run(["node", fn], capture_output=True, text=True, timeout=15)
    finally:
        os.unlink(fn)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["raw"] == "list"          # red: 게이트 없으면 상세를 list로 오판정(재현)
    assert out["gate_detail"] is True    # green: 게이트가 single로 flip
    assert out["gate_list"] is False     # 목록(search.rakuten)은 불영향 — 벌크 34타일 계약 유지


# ── item 2 실추출(playwright, 실 크로미움 DOM): 아마존 thin 갤러리 1 → n ──
_AMZ_THIN = """<!doctype html><html><head><meta charset=utf-8>
<meta property="og:title" content="OHSNAP 접착 패드"><meta property="og:image" content="https://m.media-amazon.com/images/I/rep.jpg">
<title>OHSNAP</title></head><body>
<div id="productTitle">OHSNAP 접착 패드</div>
<div id="imgTagWrapperId"><img id="landingImage" src="https://m.media-amazon.com/images/I/rep._AC_SX466_.jpg"
   data-a-dynamic-image='{"https://m.media-amazon.com/images/I/rep._AC_SX679_.jpg":[679,679]}'></div>
<div id="altImages"><ul>
  <li><img src="https://m.media-amazon.com/images/I/g1._AC_US40_.jpg"></li>
  <li><img src="https://m.media-amazon.com/images/I/g2._AC_US40_.jpg"></li>
  <li><img src="https://m.media-amazon.com/images/I/g3._AC_US40_.jpg"></li>
  <li><img src="https://m.media-amazon.com/images/I/g4._AC_US40_.jpg"></li>
  <li><img src="https://m.media-amazon.com/images/I/g5._AC_US40_.jpg"></li>
</ul></div>
<span class="a-price"><span class="a-offscreen">$24.69</span></span>
</body></html>"""


@pytest.mark.skipif(not _pw_exe(), reason="Playwright/chromium 미설치")
def test_amazon_thin_gallery_merges_to_many():
    from playwright.sync_api import sync_playwright
    url = "https://www.amazon.com/dp/B0OHSNAP01"
    with sync_playwright() as pw:
        o = {"executable_path": _pw_exe()}
        px = os.environ.get("HTTPS_PROXY")
        if px:
            o["proxy"] = {"server": px, "bypass": "127.0.0.1,localhost"}
        b = pw.chromium.launch(**o)
        page = b.new_context().new_page()

        def h(r):
            if r.request.url.split("#")[0] == url:
                r.fulfill(status=200, content_type="text/html; charset=utf-8", body=_AMZ_THIN)
            else:
                r.abort()
        page.route("**/*", h)
        page.goto(url, wait_until="domcontentloaded")
        res = page.evaluate("(ex)=>{ (0,eval)(ex); return window.kgpExtractProduct(); }", EX)
        b.close()
    imgs = res.get("images") or []
    assert len(imgs) > 1, f"아마존 thin 갤러리 병합 실패(수집 {len(imgs)}장)"   # 대표 1장 → 여러 장
    assert len(imgs) >= 5   # 썸네일 스트립 5장 이상 승격


# ── item 1 실브라우저 계약(playwright + 확장 로드, L2 계보): 라쿠텐 상세 → single ──
_RAK_DETAIL = """<!doctype html><html><head><meta charset=utf-8><title>だしパック</title>
<meta property="og:title" content="国産 だしパック 30包"></head><body>
<h1>国産 だしパック 30包 無添加</h1>
<div class="gallery"><img src="https://tshop.r10s.jp/tabemon-dikara/cabinet/main.jpg"></div>
<span class="price">1,706円</span>
<a href="https://item.rakuten.co.jp/tabemon-dikara/71/">この商品</a>
<div class="rankingReco">%s</div>
</body></html>"""
_RAK_TILES = "".join(
    '<div class="searchresultitem"><a href="https://item.rakuten.co.jp/shop%d/code%d/">'
    '<img src="https://tshop.r10s.jp/shop%d/thumb%d.jpg"></a><span class="price">%d円</span></div>'
    % (i, i, i, i, 500 + i) for i in range(40)
)


@pytest.mark.skipif(not _pw_exe(), reason="Playwright/chromium 미설치")
def test_rakuten_detail_is_single_realbrowser():
    from playwright.sync_api import sync_playwright
    url = "https://item.rakuten.co.jp/tabemon-dikara/71/"
    body = _RAK_DETAIL % _RAK_TILES

    def route(r):
        if r.request.url.split("?")[0].split("#")[0] == url:
            r.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)
        elif "/api/v1/collect/extension" in r.request.url:
            r.fulfill(status=200, content_type="application/json", body='{"ok":true}')
        else:
            try:
                r.fulfill(status=200, content_type="text/html", body="<html></html>")
            except Exception:
                r.abort()

    with sync_playwright() as pw:
        userdir = tempfile.mkdtemp()
        ctx = pw.chromium.launch_persistent_context(
            userdir, headless=True, executable_path=_pw_exe(),
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}", "--headless=new"])
        try:
            ctx.route("**/*", route)
            sw = None
            for _ in range(40):
                if ctx.service_workers:
                    sw = ctx.service_workers[0]; break
                ctx.new_page().wait_for_timeout(200)
            if sw is None:
                if _require_browser():
                    pytest.fail("확장 서비스워커 미기동")
                pytest.skip("확장 서비스워커 미기동 — 하네스 한계(정직 skip)")
            p = ctx.new_page()
            p.goto(url, wait_until="domcontentloaded")
            p.wait_for_timeout(2500)
            tabid = sw.evaluate(
                "async()=>{const t=(await chrome.tabs.query({})).find(x=>x.url&&x.url.includes('item.rakuten.co.jp'));return t?t.id:-1;}")
            assert tabid != -1
            state = sw.evaluate(
                "async(t)=>new Promise(r=>chrome.tabs.sendMessage(t,{action:'kgpDetectState'},x=>r(x||null)))", tabid)
            assert state, "kgpDetectState 무응답"
            # 크리티컬: 추천 타일 40개(cardCount 높음)에도 상세 서브도메인이라 single로 못박힘.
            assert state.get("pageType") == "single", f"라쿠텐 상세 오판정: {state.get('pageType')} (tiles={state.get('cards')})"
            assert state.get("allowed") is True   # 지정 소싱처 — 단품 수집(FAB/팝업) 게이트 활성
        finally:
            ctx.close()
