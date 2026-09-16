"""F28 계약 — 목록은 JS가 그린다. 그리고 실패 사유를 덮지 않는다.

## 실측 (오너 2026-09-16, 캡처 3장)

① 번역 탭: 「번역할 이미지를 골라 주세요」 아래 **목록 0장**(원본 5장은 존재).
② 사전검증: 쿠팡 실패(키·배송정보 미입력) · 스토어 심사중 · 11번가·WC 통과.
③ 통과한 2개 업로드 → **「이미지 처리에 실패했어요 — 잠시 후 다시 시도」**.

## 원인 둘

**①은 `goneNow` 미선언**(F27이 넣은 줄). 브라우저가 그 자리에서 ReferenceError를 던져
`map`이 끊기고 `host.innerHTML`이 **아예 대입되지 않는다.** 서버 HTML엔 `#imgkoList`가
멀쩡히 들어 있으므로 **렌더된 HTML만 읽는 계약은 이걸 못 본다.**

  → F23은 헤드리스 크로미움으로 이걸 잡았다. F27에서 나는 **정적 파싱으로 되돌아갔고**
    같은 탭을 다시 비웠다. 그래서 이 계약은 **브라우저를 띄운다.**

**③은 화면이 서버의 정직한 문장을 덮은 것.** 서버는 409로 사유를 보냈는데
`kgpFriendlyError`의 `[/이미지/i, …]` 규칙이 **낱말 하나만 보고** 통째로 갈아치웠다.
사유가 사라진 것보다 **틀린 조언**이 나쁘다 — 잠시 후 다시 시도하면 똑같이 막힌다.
(C-F3에서 '가격' 규칙에 똑같은 일이 있었다. 옆 줄의 같은 함정은 그대로 뒀다.)

라이브 API 호출 0 · 마켓 호출 0.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "src/seller_console/templates/collect_preview.html"
JS = ROOT / "src/seller_console/static/seller.js"


@pytest.fixture(autouse=True)
def _clean():
    from src.db import image_ko_blobs_pg as blobs
    blobs.reset_for_tests()
    yield
    blobs.reset_for_tests()


def _client():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "a@b.c"
    return c


def _row(extra):
    return {"id": "i1", "title": "수행방패", "url": "https://item.taobao.com/item.htm?id=1",
            "image_url": "", "price": "100", "currency": "CNY", "status": "ok",
            "extra_json": json.dumps(extra)}


def _pw_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    if glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"):
        return True
    try:
        with sync_playwright() as pw:
            return Path(pw.chromium.executable_path).exists()
    except Exception:
        return False


def _render_drawer(extra) -> str:
    import src.seller_console.views as V
    c = _client()
    with patch.object(V, "_get_owned_item", lambda i: _row(extra)):
        r = c.get("/seller/collect/preview/i1?drawer=1")
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def _drive(html: str, script: str):
    """진짜 브라우저에 태워 JS를 **실행**하고 그 결과를 돌려준다.

    네트워크는 전부 끊는다(이미지·폰트·CSS) — 이 계약이 재는 것은 **DOM을 그렸는가**이지
    바깥 자원이 오는가가 아니다. 대신 `pageerror`는 하나도 빠짐없이 모은다.
    """
    from playwright.sync_api import sync_playwright
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")
    opts = {"executable_path": hits[0]} if hits else {}
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     encoding="utf-8") as f:
        f.write(html)
        path = f.name
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(**opts)
            page = b.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.route("**/*", lambda route: (
                route.abort() if route.request.resource_type in
                ("image", "font", "stylesheet", "media") else route.continue_()))
            page.goto("file://" + path, wait_until="domcontentloaded")
            page.wait_for_timeout(600)
            out = page.evaluate(script)
            b.close()
        return out, errors
    finally:
        Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# ① 번역 탭 목록 — 번역본이 0장이어도 원본 N장은 항상 보인다
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_translate_tab_lists_originals_with_zero_translations():
    """★ **F28의 판정 지점** — 번역본 0장 상태에서 원본 5장 행이 그려진다.

    오너 화면이 딱 이 상태였다(원본 5장·번역본 0장 → 목록 0장).
    """
    html = _render_drawer({"images": [f"https://o/{i}.jpg" for i in range(5)],
                           "images_ko": []})
    out, errors = _drive(html, """() => ({
        rows: document.querySelectorAll('#imageRows .img-url').length,
        list: document.querySelectorAll('#imgkoList .pc-inset').length,
        empty: (document.getElementById('imgkoList') || {}).innerHTML === '',
    })""")
    assert not errors, f"페이지 에러 — 목록이 끊긴다: {errors[:3]}"
    assert out["rows"] == 5, out
    assert out["list"] == 5, f"원본 5장인데 목록 {out['list']}장 (empty={out['empty']})"


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_translate_tab_survives_gone_translations():
    """번역본이 **사라진** 상태에서도 목록은 그려진다(그때가 제일 필요한 순간이다)."""
    html = _render_drawer({
        "images": [f"https://o/{i}.jpg" for i in range(3)],
        "images_ko": [{"idx": 0, "status": "done", "use": True, "stored_by": "db",
                       "url": "/seller/collect/image-ko/i1/0", "warn": []}]})
    out, errors = _drive(html, """() => ({
        list: document.querySelectorAll('#imgkoList .pc-inset').length,
        gone: document.getElementById('imgkoList').innerHTML.indexOf('저장된 번역본이 없습니다') >= 0,
    })""")
    assert not errors, f"페이지 에러: {errors[:3]}"
    assert out["list"] == 3
    assert out["gone"], "사라진 번역본을 「번역됨」으로만 두면 사람이 이유를 모른다"


@pytest.mark.skipif(not _pw_ok(), reason="Playwright/chromium 미설치")
def test_drawer_has_no_page_errors_at_all():
    """서랍을 열었을 때 **JS 예외가 0개**. 하나 나면 그 아래 전부가 안 그려진다."""
    html = _render_drawer({"images": ["https://o/0.jpg"], "images_ko": []})
    _, errors = _drive(html, "() => 1")
    assert not errors, f"서랍에서 예외: {errors[:5]}"


def test_render_function_declares_every_name_it_uses():
    """정적 안전망 — `goneNow`가 **선언되고** 쓰인다.

    브라우저 계약이 스킵되는 환경(크로미움 없음)에서도 이 한 줄은 남는다.
    """
    src = TPL.read_text(encoding="utf-8")
    fn = re.search(r"function kgpImgkoRender\(\) \{.*?\n\}", src, re.S)
    assert fn, "kgpImgkoRender를 못 찾았다"
    body = "\n".join(l for l in fn.group(0).splitlines()
                     if not l.strip().startswith("//"))
    assert "goneNow" in body
    assert re.search(r"var\s+goneNow\s*=", body), "쓰기만 하고 선언이 없다(F28 재발)"


# ---------------------------------------------------------------------------
# ② 실패 사유 — 덮지 않는다
# ---------------------------------------------------------------------------

def _run_mapper(calls: list):
    """`kgpFriendlyError`를 **실제로 돌린다** — 소스 위치가 아니라 동작을 잰다."""
    js = JS.read_text(encoding="utf-8")
    fn = re.search(r"function kgpFriendlyError\(raw\) \{[\s\S]*?\n\}", js)
    assert fn, "kgpFriendlyError를 못 찾았다"
    harness = fn.group(0) + "\nconsole.log(JSON.stringify([%s].map(kgpFriendlyError)));" % \
        ",".join(json.dumps(c, ensure_ascii=False) for c in calls)
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write(harness)
        path = f.name
    try:
        r = subprocess.run(["node", path], capture_output=True, text=True, timeout=20)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        Path(path).unlink(missing_ok=True)


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="node 미설치")
def test_server_sentence_is_not_rewritten():
    """★ 서버가 `user_message`로 보낸 문장은 **그대로** 나간다 — 장 번호·응답코드 포함."""
    honest = ("등록 전 이미지 확인에서 막혔어요 — 2장을 마켓이 가져갈 수 없습니다 "
              "(갤러리 1번째 — 응답 403 · 갤러리 3번째 — 우리 서버 주소라 마켓이 가져갈 수 없습니다)")
    got = _run_mapper([{"ok": False, "error": honest, "user_message": True}])[0]
    assert got == honest, f"덮였다: {got!r}"
    assert "403" in got and "갤러리 1번째" in got


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="node 미설치")
def test_the_word_image_alone_no_longer_swallows_a_sentence():
    """낱말 하나로 문장을 바꾸지 않는다 — 표식이 없어도 그렇다."""
    got = _run_mapper([
        "등록 전 이미지 확인에서 막혔어요 — 갤러리 1번째",   # 실패 어형 아님 → 유지
        "이미지 5장을 담았어요",                             # 성공 문구 → 유지
        "이미지 변환에 실패했어요",                          # 진짜 실패 → 친절 문구
    ])
    assert "갤러리 1번째" in got[0], got[0]
    assert "담았어요" in got[1], got[1]
    assert "잠시 후 다시 시도" in got[2], got[2]


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="node 미설치")
def test_the_flag_is_not_a_licence_for_dev_messages():
    """`user_message`가 붙어도 스택트레이스는 못 지나간다 — 표식은 면허가 아니다."""
    got = _run_mapper([{"ok": False, "user_message": True,
                        "error": "Traceback (most recent call last): boom"}])[0]
    assert "Traceback" not in got
    assert "문제가 생겼" in got


def test_old_broad_image_rule_is_gone():
    """규칙 자체가 좁아졌는지 — 주석이 아니라 **규칙 줄**을 본다."""
    js = JS.read_text(encoding="utf-8")
    body = "\n".join(l for l in js.splitlines() if not l.strip().startswith("//"))
    assert "[/이미지/i," not in body, "낱말 하나만 보는 규칙이 남아 있다"


# ---------------------------------------------------------------------------
# ③ 게이트 문장 — 어느 장·무슨 응답
# ---------------------------------------------------------------------------

def test_gate_message_carries_page_and_status():
    """**발명 금지** — 장 번호와 응답코드는 실제 확인 결과에서만 온다."""
    from src.services import image_reachability as R
    msg = R.message({"ok": False, "bad": [
        {"url": "https://o/0.jpg", "label": "갤러리 1번째", "status": 403, "reason": "응답 403"},
        {"url": "/seller/collect/image-ko/i1/2", "label": "갤러리 3번째", "status": 0,
         "reason": "우리 서버 주소라 마켓이 가져갈 수 없습니다"},
    ]})
    assert "갤러리 1번째" in msg and "403" in msg
    assert "갤러리 3번째" in msg
    assert "우리 서버 주소" in msg
    assert "잠시 후" not in msg, "다시 시도하면 똑같이 막힌다 — 헛된 조언을 하지 않는다"


def test_gate_does_not_invent_a_status_code():
    """응답을 못 받은 장에 코드를 지어 붙이지 않는다."""
    from src.services import image_reachability as R
    line = R.describe({"url": "/seller/x", "label": "상세 2번째", "status": 0,
                       "reason": "우리 서버 주소라 마켓이 가져갈 수 없습니다"})
    assert line.startswith("상세 2번째 — ")
    assert not re.search(r"응답\s*\d", line), line


def test_labels_follow_the_page_order():
    """라벨이 주소와 **같은 순서**로 붙는다 — 어긋나면 엉뚱한 장을 고치게 한다."""
    from src.services import image_reachability as R
    with patch.object(R, "check_one", lambda u: {"url": u, "ok": False, "status": 404,
                                                 "content_type": "", "reason": "응답 404"}):
        out = R.check_all(["https://a/1.jpg", "https://b/2.jpg"],
                          labels=["갤러리 1번째", "상세 1번째"])
    assert [b["label"] for b in out["bad"]] == ["갤러리 1번째", "상세 1번째"]


def test_upload_409_ships_the_pages_and_the_flag():
    """라우트가 **장별 결과와 표식**을 함께 보낸다(화면이 펼칠 수 있게)."""
    import src.seller_console.views as V
    from src.db import image_ko_blobs_pg as blobs
    blobs.put("i1", 0, b"\xff\xd8-img", seller_id="u1")
    extra = {"images": ["https://o/0.jpg"],
             "images_ko": [{"idx": 0, "status": "done", "use": True,
                            "url": "/seller/collect/image-ko/i1/0", "warn": []}]}
    sent = {}

    class _Dispatcher:
        def dispatch(self, product_data, markets):
            sent["product"] = dict(product_data)
            return type("R", (), {"to_dict": lambda self: {"results": []}})()

    c = _client()
    with patch.object(V, "_get_owned_item",
                      lambda i: {"id": "i1", "extra_json": json.dumps(extra)}), \
         patch.object(V, "_get_upload_dispatcher", lambda: _Dispatcher()):
        r = c.post("/seller/collect/upload", json={
            "item_id": "i1", "markets": ["coupang"],
            "product": {"title": "수행방패", "price": "100", "images": extra["images"]},
        })
    assert r.status_code == 409
    d = r.get_json()
    assert d.get("user_message") is True, "표식이 없으면 화면이 또 덮는다"
    assert d.get("step") == "도달성 확인", "어느 단계에서 막혔는지 말한다"
    assert d["unreachable"][0]["label"] == "갤러리 1번째"
    assert not sent, "막혔는데 디스패처가 불렸다"


def test_drawer_renders_the_per_page_reason():
    """화면이 `unreachable`을 **펼친다** — 한 줄 요약만으로는 어느 장인지 모른다."""
    src = TPL.read_text(encoding="utf-8")
    fn = re.search(r"function renderUploadResults\(data\) \{.*?\n\}", src, re.S)
    assert fn
    body = "\n".join(l for l in fn.group(0).splitlines()
                     if not l.strip().startswith("//"))
    assert "data.unreachable" in body
    assert "b.label" in body and "b.status" in body


# ---------------------------------------------------------------------------
# ④ 등록 배열 — 죽은 번역본 주소는 안 나간다
# ---------------------------------------------------------------------------

def test_upload_array_falls_back_to_original_when_bytes_are_gone():
    """★ F27 규칙이 **등록 경로에도** 적용되는지 — 바이트 없는 번역본은 원본으로."""
    import src.seller_console.views as V
    extra = {"images": ["https://o/0.jpg", "https://o/1.jpg"],
             # 「번역됨」이라고 적혀 있지만 바이트는 없다(D1 시절 파일이 사라진 상태)
             "images_ko": [{"idx": 0, "status": "done", "use": True, "stored_by": "db",
                            "url": "/seller/collect/image-ko/i1/0", "warn": []}]}
    sent = {}

    class _Dispatcher:
        def dispatch(self, product_data, markets):
            sent["product"] = dict(product_data)
            return type("R", (), {"to_dict": lambda self: {"results": []}})()

    class _Resp:
        status_code = 200
        headers = {"Content-Type": "image/jpeg"}

        def close(self):
            pass

    class _Sess:
        cookies = type("C", (), {"clear": lambda self: None})()

        def head(self, *a, **k):
            return _Resp()

        def close(self):
            pass

    c = _client()
    with patch.object(V, "_get_owned_item",
                      lambda i: {"id": "i1", "extra_json": json.dumps(extra)}), \
         patch.object(V, "_get_upload_dispatcher", lambda: _Dispatcher()), \
         patch("requests.Session", lambda: _Sess()):
        r = c.post("/seller/collect/upload", json={
            "item_id": "i1", "markets": ["coupang"],
            "product": {"title": "수행방패", "price": "100", "images": extra["images"]},
        })
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    imgs = sent["product"]["images"]
    assert imgs == ["https://o/0.jpg", "https://o/1.jpg"], imgs
    assert not any(u.startswith("/seller/") for u in imgs), "죽은 주소가 마켓으로 나갔다"


def test_client_effective_images_also_falls_back():
    """화면이 만드는 배열도 같은 규칙 — 서버와 화면이 다른 답을 내면 안 된다."""
    src = TPL.read_text(encoding="utf-8")
    fn = re.search(r"function kgpEffectiveImages\(originals\) \{.*?\n\}", src, re.S)
    assert fn
    body = "\n".join(l for l in fn.group(0).splitlines()
                     if not l.strip().startswith("//"))
    assert "plan.gone" in body and "return u" in body
