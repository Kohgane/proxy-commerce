"""M4 — 미리보기는 **아무 반응 없음**이 없다(오너 2026-09-28 「고가브릿지에서 미리보기가 안 된다」).

타오바오·티몰은 설계상 서버 미리보기가 없다(초안 + 확장으로 열기 배너) — 그건 결함이 아니다.
그 밖에서 눌렀을 때 결과 카드 아니면 **사유 문장**(어느 사이트라 안 되는지)이 반드시 뜬다:
  ① 서버 사유는 사이트 이름 + 이유 + 다음 행동이고, 표식(`user_message`)이 있어 화면이 일반 문장으로 덮지 않는다
  ② 서버가 JSON 대신 HTML을 줘도(프록시 502·로그인 만료) 화면에 문장이 뜬다
  ③ 90초 넘게 답이 없으면 멈추고 말한다(AbortController)
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path

import pytest

TPL = Path("src/seller_console/templates/manual_collect.html").read_text(encoding="utf-8")


def _client(monkeypatch):
    from src.order_webhook import app
    import src.seller_console.views as V
    monkeypatch.setattr(V, "_collect_real_draft", lambda url, translate=True: None)
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-m4"
    return c


@pytest.mark.parametrize("url,name,wall", [
    ("https://www.temu.com/kr/goods.html?goods_id=601099512345", "테무(www.temu.com)", True),
    ("https://www.amazon.com/dp/B0TEST0001", "아마존(www.amazon.com)", True),
    ("https://www.yoshidakaban.com/product/100.html", "요시다카반(www.yoshidakaban.com)", False),
    ("https://shop.example.org/p/1", "shop.example.org", False),
])
def test_failure_names_the_site_and_carries_the_marker(monkeypatch, url, name, wall):
    d = _client(monkeypatch).post("/seller/collect/preview", json={"url": url}).get_json()
    assert d["ok"] is False and d["user_message"] is True and d["manual_entry"] is True
    assert d["error"].startswith(name)
    assert ("(봇 차단)" in d["error"]) is wall and "고가수집기" in d["error"]   # 단정은 실측된 곳만


def test_pipeline_crash_still_names_the_host(monkeypatch):
    import src.seller_console.views as V
    c = _client(monkeypatch)
    monkeypatch.setattr(V, "_collect_real_draft", lambda url, translate=True: (_ for _ in ()).throw(RuntimeError("x")))
    r = c.post("/seller/collect/preview", json={"url": "https://shop.example.org/p/1"})
    d = r.get_json()
    assert r.status_code == 500 and d["user_message"] is True and "shop.example.org" in d["error"]


def test_client_keeps_the_marker_handles_html_and_times_out():
    assert "e.user_message = !!data.user_message;" in TPL                        # 서버 사유를 덮지 않는다
    assert "if (!ct.includes('json'))" in TPL and "로그인이 풀렸어요" in TPL      # HTML 응답도 문장으로
    assert "setTimeout(() => ctl.abort(), 90000)" in TPL and "90초 동안 답이 없었어요" in TPL
    assert "clearTimeout(timer)" in TPL


def test_feedback_lives_right_under_the_button():
    """실측(캡처): 오류 칸이 **일괄 수집 칸 아래**에 있어 미리보기를 누르면 화면 밖에서 떴다."""
    i_btn, i_err, i_bulk = TPL.index('id="extractBtn"'), TPL.index('id="errorAlert"'), TPL.index('id="bulkUrls"')
    i_spin = TPL.index('id="loadingSpinner"')
    assert i_btn < i_spin < i_err < i_bulk
    assert "kgpRevealEl('previewCard')" in TPL and "kgpRevealEl('errorAlert')" in TPL


def _chromium():
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    return hits[0] if hits else ""


@pytest.mark.skipif(not _chromium(), reason="chromium 없음")
@pytest.mark.parametrize("scenario,expect", [
    ("html502", "서버가 답을 제대로 주지 못했어요(응답 502)"),
    ("login", "로그인이 풀렸어요"),
    ("temu", "테무(www.temu.com)는 서버에서 상품 페이지를 읽을 수 없어요"),
])
def test_clicking_preview_always_shows_a_sentence(monkeypatch, scenario, expect):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    c = _client(monkeypatch)
    page_html = c.get("/seller/collect").get_data(as_text=True)
    temu = c.post("/seller/collect/preview", json={"url": "https://www.temu.com/kr/goods.html?goods_id=601099512345"}).get_json()
    seller_js = Path("src/seller_console/static/seller.js").read_text(encoding="utf-8")
    base = "http://kgp.test"

    def route(r):
        u = r.request.url
        if u == base + "/seller/collect":
            r.fulfill(status=200, content_type="text/html; charset=utf-8", body=page_html)
        elif u.endswith("/seller/static/seller.js"):
            r.fulfill(status=200, content_type="application/javascript", body=seller_js)
        elif u.endswith("/seller/collect/preview"):
            if scenario == "html502":
                r.fulfill(status=502, content_type="text/html", body="<html><body>Bad Gateway</body></html>")
            elif scenario == "login":
                r.fulfill(status=401, content_type="text/html", body="<html>login</html>")
            else:
                r.fulfill(status=200, content_type="application/json", body=json.dumps(temu))
        else:
            r.abort()

    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=_chromium())
        pg = b.new_page(viewport={"width": 1280, "height": 720})
        pg.route("**/*", route)
        pg.goto(base + "/seller/collect", wait_until="domcontentloaded")
        pg.fill("#productUrl", "https://www.temu.com/kr/goods.html?goods_id=601099512345")
        pg.click("#extractBtn")
        pg.wait_for_selector("#errorAlert:not(.d-none) [role=alert]", timeout=5000)
        text = pg.inner_text("#errorAlert")
        btn = pg.inner_text("#extractBtn")
        seen = pg.evaluate("() => { const r = document.getElementById('errorAlert').getBoundingClientRect();"
                           " return r.top >= 0 && r.bottom <= innerHeight; }")
        b.close()
    assert expect in text, text
    assert btn == "미리보기"                                                    # 스피너가 멈췄다
    assert seen is True                                                         # 문장이 **화면 안에** 있다
