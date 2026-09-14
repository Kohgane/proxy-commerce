"""F25 계약 — 첫 라이브가 잡은 두 가지.

## 실측 (오너 2026-09-14, 이미지 번역 5장)

| 장 | 결과 | ms |
|---|---|---|
| 1 | `Data: is required` | 155 |
| 2~5 | `您当前每秒请求 N 次，超过了每秒频率上限 1` | 37~42 |

인증·리전은 통과했다. 막힌 것은 **입력 형식**과 **초당 한도** 둘이다.

## 계약이 왜 못 잡았나

D1 계약 20개는 SDK를 **목**으로 잰다. 목은 형식을 검사하지 않고 한도도 없다 —
그래서 「Url을 보내면 된다」와 「나란히 보내도 된다」가 둘 다 초록으로 남았다.
**목으로 재는 계약은 「우리가 스스로 어긴 약속」만 잡는다.** 공급사가 무엇을 거절하는지는
못 잡는다. 그래서 여기서는 **우리 쪽 규율**(무엇을 보내는가·얼마나 자주·어디서 도는가)을 잰다.

라이브 호출 0 — 이 파일은 어디에도 나가지 않는다(장당 과금).
"""
from __future__ import annotations

import ast
import time
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean():
    from src.services import image_translate_bench as bench
    from src.services import image_translate_job as job
    job.reset_for_tests()
    bench.reset_for_tests()
    yield
    job.reset_for_tests()
    bench.reset_for_tests()


# ---------------------------------------------------------------------------
# ① 입력 형식 — Data를 채운다, Url은 보내지 않는다
# ---------------------------------------------------------------------------

def test_limits_come_from_the_sdk_docstring():
    """상한은 **SDK 원문**이다 — 「经Base64编码后不超过 9M」."""
    from tencentcloud.tmt.v20180321 import models
    import inspect
    src = inspect.getsource(models.ImageTranslateLLMRequest)
    assert "不超过 9M" in src, "SDK 원문이 바뀌었다 — 상한을 다시 재야 한다"
    from src.services.image_translate_tencent import MAX_BASE64_BYTES
    assert MAX_BASE64_BYTES == 9 * 1024 * 1024


def test_payload_carries_data_and_never_url(monkeypatch):
    """URL이 와도 **우리가 내려받아** Data로 보낸다.

    옛 코드가 보낸 것은 `{'Data': '', 'Target': 'ko', 'Url': '…', 'Mode': 0}`이었다
    (직렬화 실측). SDK 주석이 시킨 그대로다 — 「Url을 쓸 때 Data에 ""를 넣으라」.
    그런데 공급사는 **빈 문자열을 「없음」으로 보고** 「Data: is required」로 거절했다.

    **주석과 실제 동작이 다르면 실제 동작을 따른다.**
    """
    from src.services import image_translate_tencent as tc
    seen = {}

    class _Resp:
        Data = "aW1n"
        Source, Target, SourceText, TargetText = "zh", "ko", "原文", "원문"
        TransDetails, RequestId, Angle = [], "req-1", 0

    class _Cli:
        def ImageTranslateLLM(self, req):
            # **실제로 나가는 것**을 잰다. `to_json_string()`은 안 보내는 None까지 찍어서
            #   「Url을 보낸다」는 거짓 빨강을 만든다(내가 처음에 그렇게 썼다).
            seen.update(req._serialize())
            return _Resp()

    monkeypatch.setenv("TENCENT_SECRET_ID", "id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "key")
    with patch.object(tc, "_client", lambda *_a, **_k: _Cli()), \
         patch.object(tc, "fetch_image", lambda u: (b"\xff\xd8imgbytes", "")):
        out = tc.translate_image(url="https://img.example/a.jpg")

    assert out["ok"] is True
    assert seen.get("Data"), "Data가 비어 있다 — 공급사가 거절한 그 모양이다"
    assert "Url" not in seen, "거절당하는 Url 필드를 다시 보내고 있다"
    assert seen.get("Target") == "ko"
    assert "Source" not in seen, "요청 모델에 없는 필드다"


def test_fetch_refuses_oversized_images():
    """상한을 넘으면 **보내기 전에** 멈춘다 — 보내고 거절당하면 그 왕복이 낭비다."""
    from src.services import image_translate_tencent as tc

    class _R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=None): return b"x" * (n or 1)

    with patch("urllib.request.urlopen", lambda *a, **k: _R()):
        raw, why = tc.fetch_image("https://img.example/big.jpg")
    assert raw == b"" and "너무 큽니다" in why


def test_fetch_failure_is_honest_not_an_exception():
    from src.services import image_translate_tencent as tc

    def boom(*a, **k):
        raise TimeoutError("slow")

    with patch("urllib.request.urlopen", boom):
        raw, why = tc.fetch_image("https://img.example/a.jpg")
    assert raw == b"" and "TimeoutError" in why


# ---------------------------------------------------------------------------
# ② 초당 한도 — 직렬 + 간격 + 1회 재시도
# ---------------------------------------------------------------------------

def test_rate_limit_code_exists_in_the_sdk_table():
    """힌트는 **SDK 표에 실재하는 코드**에만 단다(발명 0)."""
    from tencentcloud.tmt.v20180321 import errorcodes as E
    codes = {v for k, v in vars(E).items() if not k.startswith("_") and isinstance(v, str)}
    assert "LimitExceeded" in codes
    from src.services.image_translate_tencent import ERROR_HINTS
    assert "초당 1장" in ERROR_HINTS["LimitExceeded"], "한도가 초당 1회라는 사실이 문장에 없다"


@pytest.mark.parametrize("code,msg", [
    ("LimitExceeded", ""),
    ("", "您当前每秒请求 5 次，超过了每秒频率上限 1"),
    ("", "Rate limit exceeded"),
])
def test_rate_limited_is_recognized(code, msg):
    from src.services.image_translate_tencent import _is_rate_limited
    assert _is_rate_limited(code, msg) is True


def test_other_errors_are_not_treated_as_rate_limit():
    from src.services.image_translate_tencent import _is_rate_limited
    assert _is_rate_limited("FailedOperation.DecodeErr", "decode failed") is False


def test_calls_are_serialized_with_an_interval(monkeypatch):
    """장 사이에 **최소 간격**이 선다 — 나란히 보내면 2번째부터 전부 한도에 걸린다."""
    from src.services import image_translate_tencent as tc
    monkeypatch.setattr(tc, "MIN_INTERVAL_SEC", 0.2)
    monkeypatch.setenv("TENCENT_SECRET_ID", "id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "key")
    stamps = []

    class _Resp:
        Data = "aW1n"
        Source, Target, SourceText, TargetText = "zh", "ko", "", ""
        TransDetails, RequestId, Angle = [], "r", 0

    class _Cli:
        def ImageTranslateLLM(self, req):
            stamps.append(time.monotonic())
            return _Resp()

    tc._LAST_CALL[0] = 0.0
    with patch.object(tc, "_client", lambda *_a, **_k: _Cli()), \
         patch.object(tc, "fetch_image", lambda u: (b"img", "")):
        for _ in range(3):
            tc.translate_image(url="https://img.example/a.jpg")

    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert all(g >= 0.18 for g in gaps), f"간격 없이 나갔다: {gaps}"


def test_rate_limit_retries_exactly_once(monkeypatch):
    """한도면 **한 번만** 쉬었다 다시. 그 외 오류는 재시도 0(장당 과금)."""
    from src.services import image_translate_tencent as tc
    monkeypatch.setattr(tc, "MIN_INTERVAL_SEC", 0.0)
    monkeypatch.setattr(tc, "RATE_RETRY_WAIT_SEC", 0.01)
    monkeypatch.setenv("TENCENT_SECRET_ID", "id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "key")

    class _Boom(Exception):
        code = "LimitExceeded"
        message = "超过了每秒频率上限 1"

    class _Resp:
        Data = "aW1n"
        Source, Target, SourceText, TargetText = "zh", "ko", "", ""
        TransDetails, RequestId, Angle = [], "r", 0

    calls = {"n": 0}

    class _Cli:
        def ImageTranslateLLM(self, req):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _Boom()
            return _Resp()

    tc._LAST_CALL[0] = 0.0
    with patch.object(tc, "_client", lambda *_a, **_k: _Cli()), \
         patch.object(tc, "fetch_image", lambda u: (b"img", "")):
        out = tc.translate_image(url="https://img.example/a.jpg")
    assert out["ok"] is True and calls["n"] == 2
    assert out.get("rate_retried") is True


def test_non_rate_errors_are_not_retried(monkeypatch):
    from src.services import image_translate_tencent as tc
    monkeypatch.setattr(tc, "MIN_INTERVAL_SEC", 0.0)
    monkeypatch.setenv("TENCENT_SECRET_ID", "id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "key")

    class _Boom(Exception):
        code = "FailedOperation.DecodeErr"
        message = "decode"

    calls = {"n": 0}

    class _Cli:
        def ImageTranslateLLM(self, req):
            calls["n"] += 1
            raise _Boom()

    tc._LAST_CALL[0] = 0.0
    with patch.object(tc, "_client", lambda *_a, **_k: _Cli()), \
         patch.object(tc, "fetch_image", lambda u: (b"img", "")):
        out = tc.translate_image(url="https://img.example/a.jpg")
    assert out["ok"] is False and calls["n"] == 1, "과금되는 재시도가 늘었다"


# ---------------------------------------------------------------------------
# ③ 요청 밖에서 돈다 (F22 교훈)
# ---------------------------------------------------------------------------

def test_translate_route_accepts_and_returns_202():
    """「선택 번역」은 **접수**다. 5장이면 6초가 넘어 응답에 담을 수 없다."""
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    import src.seller_console.views as V
    from src.services import image_translate_job as job

    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "a@b.c"

    with patch.object(V, "_get_owned_item", lambda i: {"id": i}), \
         patch("src.services.image_translate_tencent.is_configured", return_value=True), \
         patch.object(job, "accept", return_value={"ok": True, "accepted": 2,
                                                   "queued": [0, 1], "skipped": []}):
        r = c.post("/seller/collect/x1/translate-images", json={"indices": [0, 1]})
    assert r.status_code == 202, "응답을 붙잡고 번역하고 있다 — F22와 같은 자리다"
    assert r.get_json()["accepted"] == 2


def test_routes_do_not_call_the_vendor_inline():
    """라우트 본문에 **번역 호출이 없다.** 있으면 응답이 그 시간을 떠안는다."""
    src = (ROOT / "src/seller_console/views.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for name in ("collect_translate_images", "image_translate_bench_run"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == name)
        body = ast.unparse(fn)
        assert "translate_image(" not in body, f"{name}이 요청 안에서 공급사를 부른다"


def test_job_serializes_and_saves_each_page(monkeypatch):
    """한 장씩 돌고 **장마다 저장**한다 — 중간에 죽어도 앞선 장은 남는다."""
    import json as _json
    from src.services import image_translate_job as job

    extra = {"images": ["a.jpg", "b.jpg"]}
    saved = []

    def fake_get(item_id, seller_ids=None, seller_id=None):
        return {"id": item_id, "extra_json": _json.dumps(extra)}

    def fake_update(item_id, **kw):
        saved.append(_json.loads(kw["extra_json"]))
        extra.update(_json.loads(kw["extra_json"]))
        return True

    def fake_translate(*, url="", **kw):
        return {"ok": True, "image_b64": "aW1n", "vendor": "tencent", "ms": 5,
                "target_text": "한국어", "source_text": "中文", "lines": []}

    with patch("src.seller_console.collect_history_store.get", fake_get), \
         patch("src.seller_console.collect_history_store.update", fake_update), \
         patch("src.services.image_translate_tencent.translate_image", fake_translate), \
         patch("src.services.image_translate_store.store_translated",
               return_value={"url": "/x.jpg", "stored_by": "file", "bytes": 3, "note": ""}):
        job._run("i1", "u1", [0, 1], {"u1"})

    # 접수 1회 + 장마다 1회 = 최소 2회 저장(장별 저장이 실제로 일어났다).
    assert len(saved) >= 2, "다 끝나고 한 번만 저장했다 — 중간에 죽으면 전부 날아간다"
    assert [e["idx"] for e in saved[-1]["images_ko"]] == [0, 1]


def test_job_refuses_a_second_run_on_the_same_item():
    """같은 상품을 두 번 돌리면 같은 장을 두 번 번역하고 **두 번 청구된다.**"""
    import json as _json
    from src.services import image_translate_job as job
    with job._LOCK:
        job._RUNNING["i1"] = True
    with patch("src.seller_console.collect_history_store.get",
               return_value={"id": "i1", "extra_json": _json.dumps({"images": ["a.jpg"]})}):
        out = job.accept("i1", "u1", [0])
    assert out["ok"] is False and out.get("already_running") is True


def test_status_route_reports_queued_and_running():
    """화면이 **남은 장수**를 알아야 폴링을 멈출 때를 안다."""
    import json as _json
    from src.services import image_translate_job as job
    extra = {"images": ["a.jpg"], "images_ko": [{"idx": 0, "status": "queued"}]}
    with patch("src.seller_console.collect_history_store.get",
               return_value={"id": "i1", "extra_json": _json.dumps(extra)}):
        st = job.status("i1", {"u1"})
    assert st["ok"] is True
    assert st["summary"]["queued"] == 1
    assert st["running"] is False


def test_drawer_polls_instead_of_waiting():
    tpl = (ROOT / "src/seller_console/templates/collect_preview.html").read_text(encoding="utf-8")
    assert "kgpImgkoPoll" in tpl and "/images-ko" in tpl
    seg = tpl.split("function kgpImgkoPoll", 1)[1][:1200]
    assert "n > 200" in seg, "끝나지 않으면 영원히 두드린다"


def test_bench_polls_instead_of_waiting():
    tpl = (ROOT / "src/seller_console/templates/image_translate_bench.html").read_text(encoding="utf-8")
    assert "benchPoll" in tpl and "bench/status" in tpl


def test_no_live_calls_in_this_contract_file():
    """이 파일은 **어디에도 나가지 않는다** — 장당 과금이다."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    assert "requests" not in mods
