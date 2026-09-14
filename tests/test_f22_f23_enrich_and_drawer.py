"""F22 · F23 계약 — 보강 502 · 서랍 이미지 소실.

## F22 — 요청 안에서 남의 서버 이미지를 내려받고 있었다

실측(오너 2026-09-14): 초안 1060535477134가 「보강 막힘 — 3회 시도 실패 —
서버 보강 실패 HTTP 502」. 같은 시각 다른 2건은 완료.

원인 대조(코드 원문):
  · `POST /api/v1/collect/enrich`가 응답 안에서 이미지를 내려받아 워터마크를 찾고
    리사이즈하고 WebP로 바꿨다(`_store_image_copies`).
  · 예산 8초는 **벽시계 예산이 아니었다** — 마감을 장과 장 **사이**에서만 봤다.
    실측: 장당 3초 × 12장 = 9.0초(예산 초과 +1.0초). 한 장이 길면 그 한 장은 안 끊긴다.
  · 내려받기의 `timeout=10`은 **소켓 타임아웃**이지 전송 총량 마감이 아니다.
  · gunicorn `--timeout 120` 초과 → 워커 SIGKILL → 프록시 502.
  · **그리고 `slow_request`는 이때 안 찍힌다** — `after_request`에서 나오는데
    워커가 죽으면 그 코드가 실행되지 않는다. 로그에 없다 = 느리지 않았다가 **아니다**.

## F23 — 목록 계약은 초록인데 서랍이 비었다

실측: 목록 행 썸네일은 뜨는데 서랍 「썸네일」·「이미지 번역」 탭이 「이미지가 없습니다」.
헤드리스 실측으로 갈랐다 — 썸네일 탭은 5장 픽스처에서 **정상 렌더**,
이미지 번역 탭은 **데이터가 있어도 빈 상태**였다(선택자 `input[name="images"]`가
그 문서에 없다). 화면이 둘이면 계약도 둘이어야 한다.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# F22-1 · 예산은 벽시계여야 한다
# ---------------------------------------------------------------------------

class _Res:
    cdn_uploaded = False
    processed_url = ""


def test_per_image_budget_is_wall_clock():
    """한 장이 예산을 넘기면 **그 장을 버리고** 넘어간다.

    예전엔 마감을 장과 장 사이에서만 봐서, 한 장이 분 단위로 가도 아무도 안 끊었다.
    """
    from src.api.extension_api import _copy_one

    def never_returns(url, **kw):
        time.sleep(30)
        return _Res()

    t0 = time.monotonic()
    out = _copy_one(never_returns, "https://img.example/a.jpg", 0.4)
    elapsed = time.monotonic() - t0
    assert out is None, "예산을 넘긴 장은 결과로 쓰지 않는다"
    assert elapsed < 3.0, f"예산 0.4초인데 {elapsed:.1f}초 걸렸다 — 벽시계 예산이 아니다"


def test_copy_skips_entirely_without_cdn():
    """둘 데가 없으면 **한 장도 내려받지 않는다**.

    예전엔 미설정이어도 내려받고·검사하고·바꾼 다음에야 「올릴 데가 없다」를 알았다.
    버릴 것을 만드느라 워커를 잡고 있었던 셈이다.
    """
    from src.api import extension_api as ea
    calls = []

    def spy(url, **kw):
        calls.append(url)
        return _Res()

    with patch.object(ea, "_cdn_configured", return_value=False), \
         patch("src.media.image_pipeline.process_image", spy):
        out = ea._store_image_copies([f"https://img/{i}.jpg" for i in range(5)])
    assert calls == [], "CDN이 없는데 이미지를 내려받았다"
    assert "CDN 미설정" in out.get("images_stored_note", "")


def test_store_copies_uses_a_name_that_exists():
    """저장본이 실제로 생겼을 때 쓰는 이름이 **모듈에 있는 이름**이어야 한다.

    예전 코드는 `_union`을 불렀는데 그 이름은 `collect_enrich` 함수 **안에만** 있었다 —
    CDN을 켜는 날 처음 터졌을 잠복 NameError였다.
    """
    from src.api import extension_api as ea

    class Ok:
        cdn_uploaded = True
        processed_url = "https://cdn.example/x.jpg"

    with patch.object(ea, "_cdn_configured", return_value=True), \
         patch("src.media.image_pipeline.process_image", lambda u, **kw: Ok()):
        out = ea._store_image_copies(["https://img/0.jpg"], already=["https://cdn.example/old.jpg"])
    assert out.get("images_stored"), "저장본이 기록되지 않았다"
    assert "https://cdn.example/x.jpg" in out["images_stored"]


# ---------------------------------------------------------------------------
# F22-2 · 응답 경로에 이미지 복사가 없다
# ---------------------------------------------------------------------------

def test_enrich_route_does_not_copy_images_in_request():
    """`/enrich` 본문이 `_store_image_copies`를 **부르지 않는다**.

    이게 이번 502의 뿌리다. 응답을 기다리는 자리에서 남의 서버 사정을 떠안지 않는다.
    """
    import ast
    src = (ROOT / "src/api/extension_api.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "collect_enrich")
    called = {n.func.id for n in ast.walk(fn)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_store_image_copies" not in called, \
        "보강 요청 안에서 다시 이미지를 내려받고 있다 — 502가 돌아온다"


def test_queue_is_not_created_without_a_consumer():
    """CDN이 없으면 **접수도 하지 않는다** — 아무도 못 비우는 큐는 가짜 큐다."""
    src = (ROOT / "src/api/extension_api.py").read_text(encoding="utf-8")
    assert 'extra["images_copy_state"] = "queued"' in src
    # 접수는 반드시 `_cdn_configured()` 안쪽에서만 일어난다.
    seg = src.split('if changed.get("images")', 1)[1][:900]
    assert "_cdn_configured()" in seg
    assert seg.index("_cdn_configured()") < seg.index('"queued"')


def test_image_copy_cron_is_registered_and_guarded():
    """큐에 **소비자가 있다**. 그리고 비용을 쓰는 라우트는 시크릿 뒤에 둔다."""
    from src.order_webhook import app
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/cron/image-copies" in rules, "큐를 비울 사람이 없다"

    c = app.test_client()
    assert c.post("/cron/image-copies").status_code == 403, "시크릿 없이 열려 있다"


def test_image_copy_cron_says_zero_honestly_without_cdn(monkeypatch):
    """CDN이 없으면 「0건」이 거짓이 아니라 사실이다 — 그렇게 말한다."""
    monkeypatch.setenv("CRON_SECRET", "s3cr3t")
    from src.order_webhook import app
    from src.api import extension_api as ea
    with patch.object(ea, "_cdn_configured", return_value=False):
        r = app.test_client().post("/cron/image-copies", headers={"X-Cron-Secret": "s3cr3t"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True and d["picked"] == 0
    assert "CDN 미설정" in (d.get("note") or "")


# ---------------------------------------------------------------------------
# F22-4 · 상태코드는 셀러의 말이 아니다 (같은 규칙, 두 번째 화면)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,forbidden", [
    ("3회 시도 실패 — 서버 보강 실패 HTTP 502", "502"),
    ("서버 보강 실패 HTTP 500", "500"),
    ("실패 (HTTP 429)", "429"),
])
def test_block_reason_never_shows_status_code(raw, forbidden):
    from src.collectors.collect_status import humanize_block_reason
    out = humanize_block_reason(raw)
    assert forbidden not in out, f"셀러 화면에 상태코드가 남았다: {out!r}"
    assert "HTTP" not in out


def test_block_reason_keeps_the_human_part():
    """사람이 읽을 부분은 지우지 않는다 — 지우기만 하면 무엇이 막혔는지 모른다."""
    from src.collectors.collect_status import humanize_block_reason
    assert humanize_block_reason("로그인 벽") == "로그인 벽"
    assert "3회 시도 실패" in humanize_block_reason("3회 시도 실패 — 서버 보강 실패 HTTP 502")
    assert "서버가 받지 못했어요" in humanize_block_reason("서버 보강 실패 HTTP 502")


def test_enrich_axes_reason_goes_through_one_place():
    """읽는 자리가 여럿이어도 사유를 **한 곳에서만** 다듬는다(F14와 같은 규칙)."""
    from src.collectors.collect_status import enrich_axes
    ax = enrich_axes({"enrich_state": "blocked", "enrich_attempts": 3,
                      "enrich_blocked_reason": "3회 시도 실패 — 서버 보강 실패 HTTP 502"})
    assert "502" not in ax["reason"]


def test_extension_does_not_put_status_code_in_user_text():
    """확장이 애초에 상태코드가 든 문장을 **만들지 않는다**(저장되면 화면에 실린다)."""
    js = (ROOT / "extensions/chrome-collector/background.js").read_text(encoding="utf-8")
    assert '"서버 보강 실패 HTTP " + r.status' not in js
    # 숫자는 콘솔에만 남는다 — 부검은 여전히 가능해야 한다.
    assert "console.warn" in js


# ---------------------------------------------------------------------------
# F22-3 · 막힘을 다시 줄 세울 수 있다
# ---------------------------------------------------------------------------

def _drawer_client(row):
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    import src.seller_console.views as V
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "a@b.c"
    return app, c, V


def test_enrich_retry_resets_attempts_and_requeues():
    """시도를 0으로 되돌리면 **폴러가 다시 집는다**. 그게 이 버튼의 전부다."""
    saved = {}
    row = {"id": "r1", "title": "라오치엔펑", "url": "https://item.taobao.com/item.htm?id=1",
           "extra_json": json.dumps({"enrich_state": "blocked", "enrich_attempts": 3,
                                     "enrich_blocked_reason": "서버 보강 실패 HTTP 502",
                                     "price": "76.86", "images": []})}
    app, c, V = _drawer_client(row)

    def fake_update(item_id, **kw):
        saved.update(kw)
        return True

    with patch.object(V, "_get_owned_item", lambda i: dict(row)), \
         patch("src.seller_console.collect_history_store.update", fake_update):
        r = c.post("/seller/collect/r1/enrich-retry")
    assert r.status_code == 200 and r.get_json()["ok"] is True
    ex = json.loads(saved["extra_json"])
    assert ex["enrich_attempts"] == 0
    assert "enrich_blocked_reason" not in ex
    assert ex["enrich_state"] == "pending", "다시 대기로 돌아가야 폴러가 집는다"


def test_retry_button_exists_on_both_screens():
    """서랍과 「이미지 처리 대기」 **둘 다**에 있어야 한다 — 한쪽에만 있으면 못 찾는다."""
    drawer = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    queue = (ROOT / "src/seller_console/templates/media_queue.html").read_text(encoding="utf-8")
    assert "enrich-retry" in drawer and "kgpEnrichRetry" in drawer
    assert "enrich-retry" in queue and "kgp-requeue" in queue


# ---------------------------------------------------------------------------
# F23 · 화면 두 개는 계약도 두 개
# ---------------------------------------------------------------------------

FIVE = [f"https://img.alicdn.com/f{i}.jpg" for i in range(5)]


def _five_image_row():
    return {"id": "d1", "title": "라오치엔펑", "url": "https://item.taobao.com/item.htm?id=1",
            "image_url": FIVE[0], "price": "76.86", "currency": "CNY", "status": "ok",
            "extra_json": json.dumps({"images": FIVE, "gallery_images": FIVE,
                                      "enriched": True, "enrich_state": "done"})}


def test_drawer_render_carries_all_five_images():
    """서랍 렌더 HTML에 5장이 **그대로** 실려 나간다(목록 계약과 별개)."""
    row = _five_image_row()
    app, c, V = _drawer_client(row)
    with patch.object(V, "_get_owned_item", lambda i: dict(row)):
        r = c.get("/seller/collect/preview/d1?drawer=1")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for u in FIVE:
        assert u in html, f"서랍에 {u}가 실려 나가지 않았다"


def test_image_translate_tab_reads_a_selector_that_exists():
    """이미지 번역 탭이 **실재하는 요소**를 읽는다.

    D1에서 `input[name="images"]`를 찾게 해 뒀는데 그런 요소가 그 문서에 없다 —
    5장이 담긴 상품에서도 늘 「이미지가 없습니다」였다. 목록 계약은 초록인 채로.
    """
    tpl = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    # **주석은 걷어 내고 잰다.** 왜 그렇게 뒀는지 설명한 문장을 코드로 읽고 빨개지는 함정을
    #   C-F17b·D1에서 두 번 밟았다 — 재는 것은 실행되는 줄이다.
    code = "\n".join(ln for ln in tpl.splitlines()
                     if not ln.lstrip().startswith(("//", "{#", "#")))
    assert 'input[name="images"]' not in code, "존재하지 않는 선택자를 다시 읽고 있다"
    # 썸네일 탭과 **같은 모델**을 읽어야 한다(읽는 자리를 둘로 두지 않는다).
    body = code.split("function kgpImgkoRender()", 1)[1][:700]
    assert "_kgpImageUrls" in body


def test_image_inputs_have_no_name_attribute():
    """위 계약이 무엇을 재는지 고정한다 — 이미지 입력엔 `name`이 없다(클래스로 찾는다).

    이게 바뀌면 위 계약의 전제가 바뀐 것이므로 같이 보게 한다.
    """
    tpl = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    row_html = tpl.split("function addImageRow(url)", 1)[1][:800]
    assert "class=\"form-control form-control-sm img-url\"" in row_html
    assert not re.search(r"img-url[^>]*name=", row_html)


def test_empty_image_state_says_why():
    """「이미지가 없습니다」가 **왜 없는지**까지 말한다.

    서버가 센 장수와 화면이 그린 장수가 어긋나면 그건 데이터가 없는 게 아니라
    화면이 못 읽은 것이다 — 둘이 같은 문장으로 보이면 다음에도 추측으로 푼다.
    """
    tpl = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "function kgpNoImagesHtml()" in tpl
    assert "_KGP_IMG_COUNT" in tpl
    body = tpl.split("function kgpNoImagesHtml()", 1)[1][:900]
    assert "서버에는 이미지" in body, "화면이 못 읽은 경우를 구분하지 않는다"
    assert "보강이 멈춰" in body, "막힘 상태를 구분하지 않는다"
    # 빈 상태 문구는 **한 자리**에서만 만든다.
    assert tpl.count("이미지가 없습니다. 아래") == 1


def test_drawer_seeds_server_side_image_count():
    """서버가 센 장수가 실제로 서랍에 실려 나간다(위 판정의 재료)."""
    row = _five_image_row()
    app, c, V = _drawer_client(row)
    with patch.object(V, "_get_owned_item", lambda i: dict(row)):
        html = c.get("/seller/collect/preview/d1?drawer=1").get_data(as_text=True)
    assert "var _KGP_IMG_COUNT = 5;" in html


def test_tencent_sdk_never_loads_on_the_enrich_or_drawer_path():
    """F23-3: 새 의존성이 보강·서랍 요청에 실리지 않는다(실측 import 128.6ms).

    공급사 SDK는 **번역을 실제로 부르는 두 라우트 안에서만** 불러온다.
    모듈 최상위로 올라가면 그 비용이 모든 요청에 붙고, 설치가 깨진 날 **전부** 죽는다.
    """
    import ast
    for path, names in (
        ("src/api/extension_api.py", ("collect_enrich",)),
        ("src/seller_console/views.py", ("collect_preview_by_id",)),
    ):
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        # 최상위 import에 없어야 한다.
        top = {a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names}
        top |= {n.module or "" for n in tree.body if isinstance(n, ast.ImportFrom)}
        assert not any("tencentcloud" in t or "image_translate_tencent" in t for t in top), \
            f"{path} 최상위가 공급사 SDK를 문다"
        for fname in names:
            fn = next(n for n in ast.walk(tree)
                      if isinstance(n, ast.FunctionDef) and n.name == fname)
            mods = {n.module or "" for n in ast.walk(fn) if isinstance(n, ast.ImportFrom)}
            assert not any("tencent" in m for m in mods), f"{fname}이 공급사 SDK를 문다"


def test_drawer_shows_retry_when_blocked():
    """막힌 항목을 열면 서랍에서 바로 다시 줄 세울 수 있다."""
    row = {"id": "b1", "title": "수행방패", "url": "https://item.taobao.com/item.htm?id=2",
           "image_url": "", "price": "10", "status": "ok",
           "extra_json": json.dumps({"images": [], "enrich_state": "blocked",
                                     "enrich_attempts": 3,
                                     "enrich_blocked_reason": "3회 시도 실패 — 서버 보강 실패 HTTP 502"})}
    app, c, V = _drawer_client(row)
    with patch.object(V, "_get_owned_item", lambda i: dict(row)):
        html = c.get("/seller/collect/preview/b1?drawer=1").get_data(as_text=True)
    assert 'id="enrichRetryBtn"' in html
    assert "502" not in html, "서랍에 상태코드가 그대로 실렸다"
    assert "서버가 받지 못했어요" in html
