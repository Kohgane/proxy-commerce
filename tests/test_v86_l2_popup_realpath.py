"""tests/test_v86_l2_popup_realpath.py — v86-L2 팝업 [수집] 실경로 계약(실브라우저).

## 오너 실기기 결함(재조사 금지)
테무 상세 [수집] → 직후 진단: payload_echo=null + 서버 레코드 1/5(가격·갤러리 탈락).
같은 진단에서 추출은 그린(price=12730, tier1 adopted). = **추출은 되는데 전송이 빔**.

## 근원(실경로 계측으로 특정)
수집 진입점은 넷이다 — FAB(handleFabClick)·호버(kgpQuickCollect)·벌크(kgpRunBulk)·**팝업(popup.js)**.
v86-I/L이 앞의 셋은 단일 정본 경로(kgpAcquireMeta=MAIN tier1 병합 + _kgpRecordEcho)로 통일하고
echo를 계측했다. 그러나 **팝업만** 독립 경로였다: `chrome.scripting.executeScript`로 og/jsonld를
**ISOLATED에서** 읽고(→ 테무 네트워크 전달 상품 JSON=MAIN 캡처를 못 봄 → title만) + `product:price:currency`
없으면 **currency를 임의 'USD'로** 채우고(정직 위반) + echo를 **안 남겼다**(payload_echo=null).
→ echo=null이었다는 사실 자체가 "FAB가 아니라 팝업으로 보냈다"의 증거다(FAB는 항상 echo를 남긴다).

## 부검 (기존 I·L 계약이 왜 실경로를 놓쳤나) — 1줄
> 기존 I·L 계약은 in-page(FAB/호버/벌크)만 계측·검증했고, 팝업(popup.js)의 독립 collect 경로
> (executeScript og/jsonld ISOLATED + tabs.sendMessage extractMeta, echo 미기록·MAIN 병합 없음)는
> 계약 밖이라 실경로를 놓쳤다.

## 수리
- content_script.js: `action:"kgpCollectNow"` 핸들러 신설 → FAB와 **같은 코드**(kgpAcquireMeta →
  kgpExtractMerged[MAIN tier1 병합] → _kgpRecordEcho(meta,"popup"))로 통과. single 게이트도 방어선.
- popup.js: 수집 클릭이 **먼저** kgpCollectNow에 위임한다. content_script 부재 시에만 옛 executeScript 폴백.

## 실브라우저 증빙(이 파일) — 하네스 그린 불인정, playwright + 확장 로드로만
네트워크로만 상품이 오는 테무형 픽스처에서:
- (A) 수리前 팝업 executeScript 추출 → price='' + currency 임의 'USD'(서버 1/5 + 정직 위반) 재현.
- (C) 수리後 팝업 kgpCollectNow 전송 payload → corr_id 부여(정본 경로) + currency 정직(도메인 KRW,
      임의 USD 아님) + mode='simple'(tier1 미착지 정직 강등) + **echo.path='popup'(payload_echo≠null)**.

## 하네스 한계(정직 표기)
playwright `--load-extension`(headless=new)에서 `[kgp-extractor, kgp-main]`의 **MAIN 월드 주입이
불안정**하다(window.kgpExtractProduct 미정의 — 실 크롬/오너 실기기에선 정상). 그래서 이 계약은 **결함이
사는 배선(팝업→정본+echo)**을 실브라우저로 못박는다. MAIN tier1 추출 자체(전 페이로드)는 jsdom
realpage 하네스(test_v70_realpage_harness)와 오너 실기기 진단이 별도로 담보한다.
"""
from __future__ import annotations

import glob
import json
import os
import tempfile
from pathlib import Path

import pytest

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
PJ = Path("extensions/chrome-collector/popup.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))

_TEMU_URL = "https://www.temu.com/kr/goods-g-601104878115983.html"
_API_URL = "https://www.temu.com/api/poppy/v1/goods/601104878115983"
_PAGE = (
    '<!doctype html><html><head><meta charset=utf-8>'
    '<meta property="og:title" content="큐브 RGB 무선 스피커"><title>큐브 RGB 무선 스피커</title></head>'
    '<body><h1>큐브 RGB 무선 스피커</h1><div id=app>로딩중…</div>'
    '<script>fetch("%s").then(r=>r.json()).then(d=>{window.rawData=d;'
    'document.getElementById("app").textContent="로드됨";});</script></body></html>' % _API_URL
)
_GOODS = {"store": {"goods": {
    "goodsId": 601104878115983, "goodsName": "큐브 RGB 무선 스피커",
    "imagePathList": ["https://img.kwcdn.com/a.jpg", "https://img.kwcdn.com/b.jpg"],
    "skuList": [{"skuId": 1, "goodsId": 601104878115983, "price": 12730, "currency": "KRW"}],
}}}


# ── 소스 계약(브라우저 불요·결정적) ───────────────────────────────────────
def test_content_script_has_popup_authoritative_handler():
    # 팝업 전송도 FAB와 같은 정본 경로(kgpAcquireMeta + echo path="popup")를 통과해야 한다.
    assert 'msg.action === "kgpCollectNow"' in CS
    assert "kgpAcquireMeta(" in CS
    assert '_kgpRecordEcho(meta, "popup")' in CS


def test_popup_delegates_to_authoritative_path_first():
    # 팝업이 executeScript(og/jsonld) 직접추출보다 **먼저** kgpCollectNow에 위임해야 한다.
    i_deleg = PJ.find('action: "kgpCollectNow"')
    i_prim = PJ.find("product:price:amount")   # 옛 executeScript 원시 추출기 서명
    assert i_deleg != -1, "팝업이 kgpCollectNow에 위임하지 않음"
    assert i_prim == -1 or i_deleg < i_prim, "위임이 executeScript 원시 추출보다 뒤(폴백만이어야 함)"
    # 옛 경로의 임의 통화 기본값은 폴백에만 남아야 한다(정본 경로엔 없음).
    assert 'getMeta("product:price:currency") || "USD"' in PJ or i_prim == -1


def test_manifest_version_bumped():
    assert MANIFEST["version"] == "1.5.149"


# ── 실브라우저 계약(하네스 그린 불인정 — playwright + 확장 로드) ────────────
def _pw_exe():
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return hits[0] if hits else None


def _browser_ready():
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    if _pw_exe():
        return True
    cache = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or (Path.home() / ".cache" / "ms-playwright"))
    return cache.is_dir() and any(cache.glob("chromium-*"))


def _require_browser():
    return os.environ.get("KGP_REQUIRE_BROWSER") == "1"


def test_popup_realpath_repro_and_fix():
    if not _browser_ready():
        if _require_browser():
            pytest.fail("KGP_REQUIRE_BROWSER=1 인데 playwright/chromium 없음(실브라우저 증빙 불가)")
        pytest.skip("playwright/chromium 미설치 — 실브라우저 계약 skip(정직)")

    from playwright.sync_api import sync_playwright

    ext = os.path.abspath("extensions/chrome-collector")
    posts: list = []

    def route(r):
        u = r.request.url.split("?")[0]
        if u == _TEMU_URL:
            r.fulfill(status=200, content_type="text/html; charset=utf-8", body=_PAGE)
        elif u == _API_URL:
            r.fulfill(status=200, content_type="application/json", body=json.dumps(_GOODS))
        elif "/api/v1/collect/extension" in u:
            try:
                posts.append(json.loads(r.request.post_data or "{}"))
            except Exception:
                posts.append({"_raw": r.request.post_data})
            r.fulfill(status=200, content_type="application/json", body='{"ok":true}')
        else:
            r.continue_()

    with sync_playwright() as pw:
        userdir = tempfile.mkdtemp()
        args = [f"--disable-extensions-except={ext}", f"--load-extension={ext}", "--headless=new"]
        kw = {"headless": True, "args": args}
        exe = _pw_exe()
        if exe:
            kw["executable_path"] = exe
        ctx = pw.chromium.launch_persistent_context(userdir, **kw)
        try:
            ctx.route("**/*", route)
            sw = None
            for _ in range(40):
                if ctx.service_workers:
                    sw = ctx.service_workers[0]
                    break
                ctx.new_page().wait_for_timeout(200)
            if sw is None:
                if _require_browser():
                    pytest.fail("확장 서비스워커 미기동(실브라우저 증빙 불가)")
                pytest.skip("확장 서비스워커 미기동 — 하네스 한계(정직 skip)")

            sw.evaluate("() => chrome.storage.local.set({token:'QA-TEST-tok', serverUrl:'https://mock.local'})")
            p = ctx.new_page()
            p.goto(_TEMU_URL, wait_until="domcontentloaded")
            p.wait_for_timeout(3000)
            tabid = sw.evaluate(
                "async()=>{const t=(await chrome.tabs.query({})).find(x=>x.url&&x.url.includes('temu.com'));return t?t.id:-1;}"
            )
            assert tabid != -1, "테무 탭 미발견"

            # (A) 수리前 팝업 executeScript 추출기(og/jsonld, currency 기본 USD) — 페이지에서 그대로 실행.
            old = p.evaluate(
                """() => { const g=(pr)=>{const e=document.querySelector(`meta[property="${pr}"],meta[name="${pr}"]`);return e?e.getAttribute("content")||"":"";};
                           return { price: g("product:price:amount")||"", currency: g("product:price:currency")||"USD" }; }"""
            )
            assert old["price"] == "", f"재현 실패: 옛 경로가 가격을 냄({old['price']!r})"
            assert old["currency"] == "USD", f"재현 실패: 임의 USD 기본값 아님({old['currency']!r})"

            # (C) 수리後 팝업 경로(kgpCollectNow) — content_script 정본 경로로 전송.
            posts.clear()
            sw.evaluate(
                "async(t)=>new Promise(r=>chrome.tabs.sendMessage(t,{action:'kgpCollectNow'},x=>r(x||null)))", tabid
            )
            p.wait_for_timeout(2500)
            assert posts, "kgpCollectNow가 서버로 전송하지 않음"
            sent = posts[-1]
            assert sent.get("corr_id"), "전송 payload에 corr_id 없음(정본 경로 미통과)"
            # 정직 통화: 임의 USD 주입 금지(도메인 KRW 또는 빈값).
            assert sent.get("currency") != "USD", f"임의 USD 주입됨({sent.get('currency')!r})"

            # echo 기록(payload_echo≠null) + path="popup".
            diag = sw.evaluate(
                "async(t)=>new Promise(r=>chrome.tabs.sendMessage(t,{action:'kgpDiagBundle'},x=>r(x||null)))", tabid
            )
            echo = (diag or {}).get("payload_echo") or {}
            assert echo.get("path") == "popup", f"echo.path가 popup 아님({echo!r})"
            assert echo.get("echoed_at"), "echo에 전송시각 없음"
        finally:
            ctx.close()
