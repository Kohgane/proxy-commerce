"""순찰 106-A(오너 2026-10-26) — 메모리 바닥: 인스턴스 합계가 부팅 ~215MB → 틱만 도는 몇 시간 뒤 ~300MB에서 멈췄다.

원인 둘(로컬 실측 — preload + 워커에서 틱 경로 import, PSS 합 185 → 136MB):
- anthropic SDK: AI 한 번이면 import돼 워커에 +37~40MB 눌러앉음 → Messages API를 `requests`로 직접.
- preload 공유 페이지: 워커 gc가 세대 2를 훑으며 마스터 페이지를 복사 → 포크 직전 `gc.freeze`.
그리고 다음 판단에 쓸 숫자 둘: `rss:gate` 줄의 출처(PSS 합·cgroup·워커 RSS) · 자동 다듬기 돌림/미룸 하루 카운터.
"""
import pathlib
import subprocess
import sys


def test_no_anthropic_sdk_import_anywhere_in_src():
    hits = [str(p) for p in pathlib.Path("src").rglob("*.py")
            if "import anthropic" in p.read_text(encoding="utf-8") or "from anthropic" in p.read_text(encoding="utf-8")]
    assert hits == []


def test_ai_call_path_leaves_sdk_out_of_the_process():
    code = (
        "import sys, os\n"
        "os.environ['ANTHROPIC_API_KEY']='k'; os.environ.pop('ADAPTER_DRY_RUN', None)\n"
        "import requests\n"
        "class R:\n"
        "    status_code = 200\n"
        "    def json(self):\n"
        "        return {'content': [{'type': 'text', 'text': '좋아요'}], 'usage': {'input_tokens': 5, 'output_tokens': 2}}\n"
        "requests.post = lambda *a, **k: R()\n"
        "from src.ai import llm, budget\n"
        "budget.BudgetGuard.can_spend = lambda self, estimated_cost_usd=0: True\n"
        "budget.BudgetGuard.record = lambda self, **k: None\n"
        "r = llm.complete('hi', purpose='t', providers=['anthropic'])\n"
        "print(r['text'], r['provider'], 'anthropic' in sys.modules)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=".", timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    assert out.stdout.strip().splitlines()[-1] == "좋아요 anthropic False"


class _Resp:
    def __init__(self, code, body=None, headers=None):
        self.status_code, self._body, self.headers, self.text = code, body or {}, headers or {}, str(body)

    def json(self):
        return self._body


def test_messages_create_retries_overload_once_then_raises_with_status(monkeypatch):
    import requests
    from src.ai import llm
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr("time.sleep", lambda s: None)
    seq = [_Resp(529, {"error": {"type": "overloaded_error", "message": "busy"}}, {"retry-after": "2"}),
           _Resp(200, {"content": [{"type": "text", "text": "ok"}], "usage": {}})]
    calls = []
    monkeypatch.setattr(requests, "post", lambda *a, **k: calls.append(k["json"]) or seq.pop(0))
    assert llm.response_text(llm.messages_create({"model": "m", "max_tokens": 5, "messages": []}, 5)) == "ok"
    assert len(calls) == 2

    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(400, {"error": {"type": "invalid_request_error",
                                                                                "message": "effort not supported"}}))
    try:
        llm.messages_create({"model": "m"}, 5)
        raise AssertionError("400은 예외여야 한다")
    except llm.AnthropicHTTPError as exc:
        assert exc.status_code == 400 and exc.error_type == "invalid_request_error" and "effort" in str(exc)


def test_failed_anthropic_attempt_carries_status_code(monkeypatch):
    import requests
    from src.ai import llm, budget
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    monkeypatch.setattr("time.sleep", lambda s: None)
    monkeypatch.setattr(budget.BudgetGuard, "can_spend", lambda self, estimated_cost_usd=0: True)
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp(401, {"error": {"type": "authentication_error",
                                                                                "message": "invalid x-api-key"}}))
    r = llm.complete("hi", purpose="t")
    assert r["text"] == "" and r["attempts"][0]["status"] == 401 and "authentication_error" in r["attempts"][0]["error"]


def test_anthropic_ready_is_the_key_alone(monkeypatch):
    from src.ai import llm
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert llm.anthropic_ready() is True
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert llm.anthropic_ready() is False


def test_gunicorn_freezes_gc_before_fork(monkeypatch):
    import gc
    ns = {"__name__": "gunicorn_conf"}
    exec(compile(pathlib.Path("gunicorn.conf.py").read_text(encoding="utf-8"), "gunicorn.conf.py", "exec"), ns)
    assert ns["preload_app"] is True and callable(ns["pre_fork"])

    class S:
        class log:
            @staticmethod
            def warning(*a):
                raise AssertionError(a)
    gc.unfreeze()
    try:
        ns["pre_fork"](S, None)
        assert gc.get_freeze_count() > 0
        gc.unfreeze()
        monkeypatch.setenv("KGP_GC_FREEZE", "0")
        ns["pre_fork"](S, None)
        assert gc.get_freeze_count() == 0
    finally:
        gc.unfreeze()


def _mem_state(monkeypatch):
    from src.db import image_translate_queue_pg as st
    monkeypatch.setattr(st, "_enabled", lambda: False)
    monkeypatch.setattr(st, "_MEM_STATE", {})
    return st


def test_auto_polish_counts_ran_and_deferred_by_kst_day(monkeypatch):
    _mem_state(monkeypatch)
    from datetime import datetime, timedelta, timezone
    from src.services import image_polish, image_translate_auto as A
    from src.utils import rss
    ran = []
    monkeypatch.setattr(image_polish, "polish_job", lambda *a: ran.append(a))
    monkeypatch.setenv("IMAGE_POLISH_AUTO_MAX_MB", "300")
    mb = iter([320, 320, 250])                       # 넘음(gc 뒤 다시 재도 넘음) → 미룸 · 다음은 아래 → 돌림
    monkeypatch.setattr(rss, "instance_mb", lambda: next(mb))
    assert A._maybe_polish("i1", "u", "detail", 0) is False
    assert A._maybe_polish("i1", "u", "detail", 1) is True and len(ran) == 1
    day = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")
    assert A.polish_auto_counts(day) == {"day": day, "ran": 1, "deferred": 1, "deferred_pct": 50.0}
    assert A.polish_auto_counts("2000-01-01")["deferred_pct"] is None


def test_gate_row_records_where_the_total_comes_from(monkeypatch):
    st = _mem_state(monkeypatch)
    from src.utils import bg_job, rss
    monkeypatch.setattr(rss, "instance_parts", lambda: {"pss": 231, "cg": 240, "w": 180})
    bg_job._gate_log("tick-idle", True, 240, 420)
    row = st.state_get(bg_job.GATE_KEY)["rows"][-1]
    assert (row["job"], row["mb"], row["pss"], row["cg"], row["w"]) == ("tick-idle", 240, 231, 240, 180)
    monkeypatch.undo()
    real = rss.instance_parts()                                  # 실제 함수(gunicorn 밖 = 이 프로세스 PSS · cgroup은 -1)
    assert set(real) == {"pss", "cg", "w"} and real["pss"] > 0 and real["cg"] == -1
