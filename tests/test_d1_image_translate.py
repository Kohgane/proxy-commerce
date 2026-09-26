"""tests/test_d1_image_translate.py — D1: 텐센트 이미지 번역.

## 계약이 라이브 API를 부르지 않는다

장당 과금이고, 네트워크에 기대는 계약은 CI에서 조용히 느려지거나 빨개진다.
그래서 **SDK를 목으로 바꿔 끼우고** 요청 파라미터·응답 파싱·실패 갈래를 잰다.

## 스펙 출처

문서가 아니라 **공식 SDK 모델 클래스**(D0에서 확인). 특히:
  · 요청에 `Source`가 **없다** — 자동 감지다. 없는 필드를 만들어 보내지 않는다.
  · 실패는 예외 **클래스명 그대로** 올린다(발명 0).
"""
from __future__ import annotations

import base64
import json
import sys
import types

import pytest


# ── SDK 목 ────────────────────────────────────────────────────────────────────

class _FakeException(Exception):
    """`TencentCloudSDKException`과 같은 모양(code/message/requestId)."""

    def __init__(self, code="", message="", requestId=""):
        super().__init__(message)
        self.code, self.message, self.requestId = code, message, requestId


class _Box:
    X, Y, Width, Height = 1, 2, 3, 4


class _Detail:
    SourceLineText = "爆款 여름 신상"
    TargetLineText = "최고 인기 여름 신상"
    BoundingBox = _Box()


class _Resp:
    Data = base64.b64encode(b"\xff\xd8\xff-fake-jpeg").decode()
    Source = "zh"
    Target = "ko"
    SourceText = "爆款"
    TargetText = "최고 인기"
    Angle = 0.0
    RequestId = "req-1"
    TransDetails = [_Detail()]


@pytest.fixture()
def tc(monkeypatch):
    """텐센트 클라이언트 — SDK 호출만 목으로. 우리 코드는 그대로 돈다."""
    from src.services import image_translate_tencent as mod

    monkeypatch.setenv("TENCENT_SECRET_ID", "id-x")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "key-x")
    monkeypatch.delenv("TENCENT_REGION", raising=False)
    monkeypatch.delenv("TENCENT_TMT_ENDPOINT", raising=False)

    sent = {}

    class _Client:
        def ImageTranslateLLM(self, request):          # noqa: N802 — SDK 이름 그대로
            sent["payload"] = request._serialize()        # 전선에 실제로 나가는 것
            if sent.get("raise"):
                raise sent["raise"]
            return _Resp()

    monkeypatch.setattr(mod, "_client", lambda timeout_sec: _Client())
    # F25: URL이 와도 **우리가 내려받아** Data로 보낸다(공급사가 URL 입력을 거절했다).
    #   그래서 이 픽스처도 다운로드를 목으로 둔다 — 계약이 밖으로 나가면 안 된다.
    monkeypatch.setattr(mod, "fetch_image", lambda url: (b"\xff\xd8\xff-img", ""))
    monkeypatch.setattr(mod, "MIN_INTERVAL_SEC", 0.0)      # 간격은 F25 계약이 따로 잰다
    mod._LAST_CALL[0] = 0.0
    mod._sent = sent
    return mod


# ── 1. 요청 파라미터 ──────────────────────────────────────────────────────────

def test_request_carries_only_fields_the_sdk_defines(tc):
    """★ 요청에 **`Source`가 없다** — 자동 감지다. 없는 필드를 지어 보내지 않는다."""
    tc.translate_image(url="https://img/1.jpg")
    p = tc._sent["payload"]

    assert p["Target"] == "ko"
    assert p["Mode"] == 0
    assert "Source" not in p, f"요청 모델에 없는 필드를 보냈다: {sorted(p)}"
    # F25 실측: SDK 주석대로 `Url` + `Data:""`를 보냈더니 공급사가
    #   **「Data: is required」**로 거절했다(빈 문자열을 「없음」으로 본다).
    #   그래서 이제 우리가 내려받아 Data를 채운다.
    assert p["Data"], "Data가 비어 있다 — 공급사가 거절한 그 모양이다"
    assert "Url" not in p, "거절당하는 Url 필드를 다시 보내고 있다"


def test_bytes_go_as_base64(tc):
    tc.translate_image(data=b"\x89PNG-raw")
    p = tc._sent["payload"]
    assert base64.b64decode(p["Data"]) == b"\x89PNG-raw"
    assert "Url" not in p or not p.get("Url")


# ── 2. 응답 파싱 ──────────────────────────────────────────────────────────────

def test_response_parsing_keeps_every_field_we_promised(tc):
    r = tc.translate_image(url="https://img/1.jpg")
    assert r["ok"] is True
    assert base64.b64decode(r["image_b64"]).startswith(b"\xff\xd8\xff")
    assert r["source_lang"] == "zh" and r["target_lang"] == "ko"
    assert r["source_text"] == "爆款" and r["target_text"] == "최고 인기"
    assert r["request_id"] == "req-1"
    # F33: `line_height`·`lines_count`가 늘었다(SDK `TransDetail`에 실재하는 필드).
    #   벤치 C축의 **참고 수치**로 쓴다 — 점수로는 쓰지 않는다(박스는 원문 문단의 자리다).
    assert r["lines"] == [{"source": "爆款 여름 신상", "target": "최고 인기 여름 신상",
                           "box": {"x": 1, "y": 2, "w": 3, "h": 4},
                           "line_height": None, "lines_count": None}]
    assert isinstance(r["ms"], int)


def test_empty_image_is_not_called_success(tc):
    """★ 200인데 이미지가 비면 **성공이라 부르지 않는다**(가짜 성공 0)."""
    class _Empty(_Resp):
        Data = ""

    tc._sent["raise"] = None
    import src.services.image_translate_tencent as mod

    class _C:
        def ImageTranslateLLM(self, request):          # noqa: N802
            return _Empty()

    mod._client = lambda timeout_sec: _C()
    r = tc.translate_image(url="https://img/1.jpg")
    assert r["ok"] is False and r["error_class"] == "EmptyImage"


# ── 3. 실패 갈래 ──────────────────────────────────────────────────────────────

def test_failure_reports_the_exception_class_name_verbatim(tc):
    tc._sent["raise"] = _FakeException(code="FailedOperation.DownloadErr",
                                       message="download failed", requestId="req-err")
    r = tc.translate_image(url="https://img/x.jpg")

    assert r["ok"] is False
    assert r["error_class"] == "_FakeException", "예외 클래스명을 그대로 올려야 한다"
    assert r["error_code"] == "FailedOperation.DownloadErr"
    assert r["request_id"] == "req-err"
    assert "내려받지" in r["hint"], "SDK errorcodes에 있는 코드는 사람 말로 풀어 준다"


def test_hints_only_cover_codes_that_exist_in_the_sdk():
    """★ 힌트 표의 코드는 **전부 SDK `errorcodes.py`에 실재**해야 한다(발명 0)."""
    from src.services.image_translate_tencent import ERROR_HINTS
    try:
        from tencentcloud.tmt.v20180321 import errorcodes
    except Exception:                     # SDK 미설치 환경에선 건너뛴다(설치는 requirements가 강제)
        pytest.skip("tencentcloud SDK 미설치")
    real = {v for k, v in vars(errorcodes).items() if k.isupper() and isinstance(v, str)}
    invented = sorted(set(ERROR_HINTS) - real)
    assert not invented, f"SDK에 없는 에러 코드를 지어냈다: {invented}"


def test_unconfigured_is_a_state_not_an_error(monkeypatch):
    """★ env가 없으면 **「공급사 미연결」**이다 — 예외를 던지지 않는다."""
    from src.services import image_translate_tencent as mod
    monkeypatch.delenv("TENCENT_SECRET_ID", raising=False)
    monkeypatch.delenv("TENCENT_SECRET_KEY", raising=False)

    assert mod.is_configured() is False
    st = mod.status()
    assert st["configured"] is False and "TENCENT_SECRET_ID" in st["missing"]

    r = mod.translate_image(url="https://img/1.jpg")
    assert r["ok"] is False and r["error_class"] == "NotConfigured"


def test_region_has_no_invented_default(monkeypatch):
    """★ SDK에 리전 목록이 없다 → **기본값을 두지 않는다**(확인 못 한 값은 발명이다)."""
    from src.services import image_translate_tencent as mod
    monkeypatch.delenv("TENCENT_REGION", raising=False)
    assert mod.region() == ""
    # 엔드포인트는 반대다 — SDK에서 확인한 값이라 기본값을 둔다.
    assert mod.endpoint() in mod.ENDPOINTS.values()


def test_endpoints_match_the_installed_sdk():
    """엔드포인트 기본값이 **SDK가 쓰는 값**과 같은지 — 기억이 아니라 패키지에서 확인."""
    from src.services.image_translate_tencent import ENDPOINTS
    try:
        from tencentcloud.tmt.v20180321 import tmt_client
    except Exception:
        pytest.skip("tencentcloud SDK 미설치")
    assert tmt_client.TmtClient._endpoint in ENDPOINTS.values()
    assert tmt_client.TmtClient._apiVersion == "2018-03-21"
    assert hasattr(tmt_client.TmtClient, "ImageTranslateLLM")


def test_no_live_network_in_this_file():
    """★ 계약은 **라이브 API를 부르지 않는다** — 장당 과금이고 CI가 네트워크에 기대면 안 된다.

    소스를 정규식으로 훑으면 **이 파일이 자기 금지어 목록을 읽고 빨개진다**(C-F17b에서 밟은 함정).
    그래서 AST로 **코드 안의 호출·import만** 본다.
    """
    import ast
    from pathlib import Path

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    banned_mods = {"requests", "httpx", "urllib"}
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits += [a.name for a in node.names if a.name.split(".")[0] in banned_mods]
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in banned_mods:
                hits.append(node.module)
    assert not hits, f"계약이 네트워크 모듈을 들인다: {hits}"


# ── 4. 저장 — 원본 불변 · 장별 상태 · 금칙어 warn ─────────────────────────────

@pytest.fixture()
def store(monkeypatch):
    """D2: 번역본 바이트는 **로컬 파일이 아니라 DB**에 둔다(PG 없으면 인메모리).

    D1에선 `tmp_path`에 디렉터리를 갈아끼웠는데, 그 자리 자체가 사라졌다 —
    Render는 배포마다 그 디스크를 버리므로 「저장했다」고 부를 수 없었기 때문이다.
    """
    from src.db import image_ko_blobs_pg as blobs
    from src.services import image_translate_store as mod
    blobs.reset_for_tests()
    monkeypatch.setattr(mod, "_store_via_cdn", lambda raw, label=None: ("", ""))  # 0-b: 이름표 인자  # CDN 미설정 상황(F31: (url, error))
    yield mod
    blobs.reset_for_tests()


def _ok_result(target="최고 인기"):
    return {"ok": True, "vendor": "tencent", "ms": 120,
            "image_b64": base64.b64encode(b"\xff\xd8\xff-x").decode(),
            "target_text": target, "source_text": "爆款", "lines": [{}]}


def test_entry_records_status_and_keeps_the_translation_addressable(store):
    e = store.build_entry(2, _ok_result(), item_id="it1", seller_id="u1")
    assert e["idx"] == 2 and e["status"] == "done"
    assert e["url"] == "/seller/collect/image-ko/it1/2"
    # D2: 갈래는 cdn·db 둘뿐이다(로컬 파일은 없앴다 — 배포에 사라지는 자리다).
    assert e["stored_by"] == "db" and e["bytes"] > 0
    assert store.read_translated("it1", 2).startswith(b"\xff\xd8\xff")
    # 「어디에 뒀는지 말한다」는 규율은 그대로다. 휘발 경고는 **저장소가 없을 때만** —
    #   늘 띄우면 아무도 안 읽고, 이제는 사실도 아니다(배너는 `imgko_storage`가 판단).
    assert e["stored_by"] in ("db", "cdn"), "어디에 뒀는지 말하지 않는다"


def test_failed_entry_says_why(store):
    e = store.build_entry(0, {"ok": False, "vendor": "tencent", "ms": 90,
                              "error_class": "TencentCloudSDKException",
                              "error_code": "FailedOperation.DecodeErr",
                              "error_message": "decode", "hint": "이미지를 해독하지 못했습니다"},
                          item_id="it1", seller_id="u1")
    assert e["status"] == "failed"
    assert e["error_class"] == "TencentCloudSDKException"
    assert e["error_code"] == "FailedOperation.DecodeErr" and e["hint"]


def test_banned_words_warn_but_do_not_block_saving(store, monkeypatch):
    """★ 금칙어가 걸려도 **번역은 저장한다** — 경고만 남기고 등록 때 말한다(오너 지시).

    조용히 지우면 무엇이 바뀌었는지 아무도 모른다.
    """
    monkeypatch.setattr("src.seller_console.word_rules.apply_rules",
                        lambda text, seller_id=None, rules=None: {
                            "text": text, "substituted": [], "removed": ["최고"], "changed": True})
    e = store.build_entry(0, _ok_result("최고 인기 상품"), item_id="it1", seller_id="u1")
    assert e["status"] == "done", "경고는 저장을 막지 않는다"
    assert e["warn"] == ["최고"]
    assert "최고" in e["target_text"], "번역문을 조용히 고치지 않는다"


def test_merge_keeps_pages_translated_earlier(store):
    extra = {"images_ko": [{"idx": 0, "status": "done"}, {"idx": 5, "status": "failed"}]}
    merged = store.merge_images_ko(extra, [{"idx": 5, "status": "done"}, {"idx": 2, "status": "done"}])
    assert [m["idx"] for m in merged] == [0, 2, 5]
    assert next(m for m in merged if m["idx"] == 5)["status"] == "done", "새 결과가 이긴다"
    assert next(m for m in merged if m["idx"] == 0)["status"] == "done", "앞서 한 장이 사라지면 안 된다"


# ── 5. 서랍 경로 — 원본 불변이 **실제로** 지켜지나 ────────────────────────────

def test_drawer_translation_never_touches_the_originals(monkeypatch, store, tmp_path):
    """★★ 원본 `images`는 **영구 보존**이다 — 번역을 돌려도 그대로 남아야 한다."""
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    from src.seller_console import views as v
    from src.services import image_translate_tencent as tcmod

    originals = ["https://img/a.jpg", "https://img/b.jpg", "https://img/c.jpg"]
    state = {"extra": {"images": list(originals), "title": "책상"}}

    monkeypatch.setattr(v, "_get_owned_item",
                        lambda item_id: {"id": "it1", "title": "책상",
                                         "extra_json": json.dumps(state["extra"], ensure_ascii=False)},
                        raising=False)

    def _update(item_id, seller_ids=None, extra_json=None, **kw):
        state["extra"] = json.loads(extra_json)
        return True

    from src.seller_console import collect_history_store as chs
    monkeypatch.setattr(chs, "update", _update, raising=False)

    # F25: 접수도 저장소를 읽는다(고른 장이 실제로 있는지 본다) — 읽기도 목으로.
    def _get(item_id, seller_ids=None, seller_id=None):
        return {"id": "it1", "title": "책상",
                "extra_json": json.dumps(state["extra"], ensure_ascii=False)}

    monkeypatch.setattr(chs, "get", _get, raising=False)
    monkeypatch.setattr(tcmod, "is_configured", lambda: True)
    monkeypatch.setattr(tcmod, "translate_image", lambda **kw: _ok_result())

    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"
            s["user_email"] = "u1@example.com"
            s["user_role"] = "seller"
        r = c.post("/seller/collect/it1/translate-images", json={"indices": [0, 2]})

    # F25: 초당 1장이 계정 한도라 응답 안에서 돌리지 않는다 — **접수(202)**다.
    assert r.status_code == 202, r.get_data(as_text=True)[:300]
    body = r.get_json()
    assert body["ok"] is True and body["accepted"] == 2

    # 뒤에서 도는 일을 **여기서 직접** 돌려 결과까지 확인한다(스레드 타이밍에 기대지 않는다).
    from src.services import image_translate_job as job
    job._run("it1", "u1", [0, 2], {"u1"})

    assert state["extra"]["images"] == originals, "원본이 바뀌었다"
    assert [e["idx"] for e in state["extra"]["images_ko"]] == [0, 2]
    assert all(e["status"] == "done" for e in state["extra"]["images_ko"])


def test_drawer_refuses_when_vendor_is_not_connected(monkeypatch):
    """미연결은 **503 + 상태**로 말한다 — 사람이 무엇을 설정해야 하는지 알게."""
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    from src.seller_console import views as v
    from src.services import image_translate_tencent as tcmod

    monkeypatch.setattr(v, "_get_owned_item",
                        lambda item_id: {"id": "it1", "extra_json": '{"images":["https://x/1.jpg"]}'},
                        raising=False)
    monkeypatch.setattr(tcmod, "is_configured", lambda: False)
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"
            s["user_role"] = "seller"
        r = c.post("/seller/collect/it1/translate-images", json={"indices": [0]})
    assert r.status_code == 503
    assert (r.get_json() or {}).get("error") == "공급사 미연결"


# ── 6. 벤치 화면 ──────────────────────────────────────────────────────────────

def test_bench_is_admin_only(monkeypatch):
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    from src.seller_console import views as v

    monkeypatch.setattr(v, "_is_admin_user", lambda: False, raising=False)
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"
            s["user_role"] = "seller"
        assert c.get("/seller/admin/image-translate-bench").status_code in (301, 302)
        assert c.post("/seller/admin/image-translate-bench/run").status_code == 403


def test_bench_shows_not_connected_as_a_state(monkeypatch):
    """벤치도 미연결을 **화면 상태**로 그린다(실행 버튼 비활성)."""
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    from src.seller_console import views as v
    from src.services import image_translate_tencent as tcmod

    monkeypatch.setattr(v, "_is_admin_user", lambda: True, raising=False)
    monkeypatch.delenv("TENCENT_SECRET_ID", raising=False)
    monkeypatch.delenv("TENCENT_SECRET_KEY", raising=False)
    monkeypatch.setattr(tcmod, "is_configured", lambda: False)

    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"
            s["user_role"] = "admin"
        html = c.get("/seller/admin/image-translate-bench").get_data(as_text=True)
    assert "공급사 미연결" in html
    assert "disabled" in html


def test_usage_is_summed_from_rows_not_a_counter():
    """★ 카운터를 따로 두지 않는다 — 행을 더해서 낸다(카운터와 실제가 갈리면 답이 없다)."""
    from src.db import image_translate_usage_pg as usage
    usage.reset_for_tests()
    usage.add("u1", pages=3, ok_pages=2, ms=300)
    usage.add("u1", pages=1, ok_pages=1, ms=90)
    usage.add("u2", pages=2, ok_pages=0, ms=50)

    rows = {r["user_id"]: r for r in usage.daily_totals(14)}
    assert rows["u1"]["calls"] == 2 and rows["u1"]["pages"] == 4
    assert rows["u1"]["ok_pages"] == 3 and rows["u1"]["ms"] == 390
    assert rows["u2"]["ok_pages"] == 0
    usage.reset_for_tests()


def test_bench_scores_survive_where_files_would_not():
    """오너가 매긴 점수는 **사람이 만든 값**이라 파일이 아니라 저장소에 둔다."""
    from src.db import image_translate_usage_pg as usage
    usage.reset_for_tests()
    usage.save_run("bench-x", "u1", [{"status": "done"}, {"status": "failed"}])
    assert usage.save_scores("bench-x", {"accuracy": "4", "note": "배경 깔끔"}) is True
    run = usage.get_run("bench-x")
    assert run["scores"]["accuracy"] == "4"
    assert [r["ok"] for r in usage.list_runs()] == [1]
    usage.reset_for_tests()
