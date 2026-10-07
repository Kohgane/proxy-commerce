"""Y6-C B(오너 2026-10-07) — 쿠팡 노출 미리보기 「불러오지 못했어요 — 서버 오류·시간 초과 (HTTP 502)」.

원인(코드·실측): 미리보기 요청 안에서 대표 사진을 **내려받고 RapidOCR을 원본 해상도로** 돌렸다(로컬 4코어 800px 0.8초 ·
1920px 4.5초 — Render 작은 CPU에선 몇 배). 미리보기 라우트는 예외를 200 JSON으로 돌려주므로, 502는 앱 밖(워커가 gunicorn
120초를 넘겨 죽음 → 프록시 HTML)이다. 사전검증 쿠팡 보류(Y7)·이미지 번역 사전판정도 같은 OCR을 돌려 동시에 겹친다.
수리: 미리보기는 판정을 요청 밖(백그라운드)에서 · 화면은 3초마다 /check · 60초 넘으면 「일부 생략」 · OCR은 프로세스당 동시 1개.
미리보기는 등록 필수가 아니다 — 실패해도 「마켓에 등록」은 잠기지 않는다.
"""
from __future__ import annotations

import os
import shutil
import threading
import time

import pytest


@pytest.fixture
def cic(monkeypatch):
    from src.services import coupang_image_check as C
    monkeypatch.setenv("COUPANG_IMAGE_CHECK", "1")
    C.reset_cache()
    yield C
    C.reset_cache()


def _item(seller="y6c-b"):
    from src.seller_console import collect_history_store as S
    return S.append(source="share_text", url="https://item.taobao.com/item.htm?id=2", seller_id=seller, title="플리츠 세트",
                    price="168", currency="CNY",
                    extra={"title": "百褶套装", "images": ["https://img.alicdn.com/rep.jpg", "https://img.alicdn.com/2.jpg"],
                           "price": "168", "currency": "CNY"})


def _client(seller="y6c-b"):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c


def test_preview_request_does_not_wait_for_ocr(cic, monkeypatch):
    gate = threading.Event()

    def slow(url):
        gate.wait(5)
        return {"state": "ok", "w": 800, "h": 800, "square": True, "long_side": 800, "small": False, "white_pct": 40,
                "text": True, "seen": "SALE", "flags": [{"key": "text", "hold": True, "line": "텍스트 있음 — 반려 가능(읽은 글자 「SALE」)"}]}
    monkeypatch.setattr(cic, "check_url", slow)
    iid, c = _item(), _client()
    t0 = time.time()
    d = c.get(f"/seller/collect/{iid}/coupang-exposure").get_json()
    assert time.time() - t0 < 2 and d["ok"] and d["check"]["state"] == "pending" and d["hold"] is None
    assert d["rep"] == "https://img.alicdn.com/rep.jpg" and d["strip"]           # 카드·사진 줄은 먼저 나온다
    r = c.get(f"/seller/collect/{iid}/coupang-exposure/check", query_string={"rep": d["rep"]}).get_json()
    assert r["check"]["state"] == "pending"                                        # 아직 재는 중 — 두 번 시작하지 않는다
    gate.set()
    for _ in range(100):
        r = c.get(f"/seller/collect/{iid}/coupang-exposure/check", query_string={"rep": d["rep"]}).get_json()
        if r["check"]["state"] != "pending":
            break
        time.sleep(0.03)
    assert r["check"]["state"] == "ok" and r["check"]["text"] is True
    assert r["hold"] and r["hold"]["fix"] == "rep_image"                           # 결과가 오면 보류 줄도 그대로


def test_failure_reason_reaches_the_poll(cic, monkeypatch):
    monkeypatch.setattr(cic, "check_url", lambda u: {"state": "unknown", "why": "이미지를 내려받지 못했습니다(URLError)", "flags": []})
    iid, c = _item(), _client()
    d = c.get(f"/seller/collect/{iid}/coupang-exposure").get_json()
    for _ in range(100):
        r = c.get(f"/seller/collect/{iid}/coupang-exposure/check", query_string={"rep": d["rep"]}).get_json()
        if r["check"]["state"] != "pending":
            break
        time.sleep(0.03)
    assert r["check"] == {"state": "unknown", "why": "이미지를 내려받지 못했습니다(URLError)", "flags": []}


def test_ocr_runs_one_at_a_time(cic, monkeypatch):
    from src.services import image_text_precheck as P
    live, peak, lock = [0], [0], threading.Lock()

    def fake_all_text(raw):
        with lock:
            live[0] += 1
            peak[0] = max(peak[0], live[0])
        time.sleep(0.05)
        with lock:
            live[0] -= 1
        return False, ""
    monkeypatch.setattr(P, "all_text", fake_all_text)
    ts = [threading.Thread(target=cic._read_text, args=(b"x",)) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert peak[0] == 1


def test_preview_js_polls_and_ends_with_partial_badge():
    from pathlib import Path
    t = Path("src/seller_console/templates/_coupang_exposure.html").read_text(encoding="utf-8")
    assert "/coupang-exposure/check?rep=" in t and "}, 3000);" in t and "n >= 20" in t
    assert 'data-role="cpx-check-pending"' in t and 'data-role="cpx-check-partial"' in t and "일부 생략" in t
    # 미리보기 스크립트는 자기 영역 밖 버튼(마켓 등록·사전검증)을 건드리지 않는다
    assert "btnOpenUploadModal" not in t and "btnPrevalidate" not in t and "openUploadModal" not in t


@pytest.mark.skipif(not shutil.which("node") and not os.path.exists("/opt/pw-browsers/chromium"), reason="브라우저 없음")
def test_register_button_stays_enabled_when_preview_fails():
    """B3: 미리보기가 502로 실패해도 「마켓에 등록」은 잠기지 않는다(실브라우저)."""
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    iid, c = _item("y6c-b3"), _client("y6c-b3")
    html = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    exe = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": exe} if exe else {}))
        pg = b.new_page(viewport={"width": 390, "height": 900})

        def handle(route):
            u = route.request.url
            if "/coupang-exposure" in u:
                route.fulfill(status=502, content_type="text/html", body="<html><body>502 Bad Gateway</body></html>")
            elif u.endswith(f"/seller/collect/preview/{iid}"):
                route.fulfill(status=200, content_type="text/html", body=html)
            else:
                route.fulfill(status=200, content_type="application/json", body="{}")
        pg.route("**/*", handle)
        pg.goto(f"http://kgp.test/seller/collect/preview/{iid}")
        pg.evaluate("kgpEtab('cpx'); document.querySelector('[data-role=cpx]').scrollIntoView()")   # 보일 때만 불러온다
        pg.wait_for_function("(document.querySelector('[data-role=cpx-body]')||{}).textContent.indexOf('불러오지 못했어요') >= 0", timeout=5000)
        msg = pg.inner_text("[data-role=cpx-body]")
        disabled = pg.evaluate("document.getElementById('btnOpenUploadModal').disabled")
        b.close()
    assert "HTTP 502" in msg and disabled is False
