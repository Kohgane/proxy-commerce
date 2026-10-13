"""F25b 계약 — 프로세스 전역은 서버 전역이 아니다.

## 실측 (워커 수 원문)

    scripts/start_render.sh:30   --workers "${GUNICORN_WORKERS:-2}"
    gunicorn.conf.py:5-7         workers 2 · worker_class gthread · threads 4

**워커가 둘이다.** F25에서 건 직렬 게이트는 `threading.Lock` — **프로세스 전역**이다.
워커가 둘이면 잠금도 둘이고, 각자 「나는 하나씩 보낸다」고 믿으면서 **합쳐서 둘**이 나간다.
공급사 한도는 **계정 단위**라 합쳐서 세므로, 워커가 늘수록 정확히 그만큼 넘긴다.

## 그래서 재는 것

  ① 워커 수가 정말 2 이상인가(이 계약의 전제 — 1이 되면 전제가 바뀐 것이니 같이 보게 한다).
  ② **진짜 두 프로세스**에서 차례가 겹치지 않는가(목이 아니라 `multiprocessing`).
  ③ 차례표가 죽어도 번역이 멈추지 않는가(폴백) — 그리고 **범위가 바뀐 사실을 말하는가**.

PG가 없으면 ②는 건너뛴다. 프로세스 사이를 가로지르는 약속은 **공유 저장소 없이는 못 지킨다** —
지킬 수 없는 것을 지키는 척하지 않는다.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import re
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_PG = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
KEY_IV = 1.1


@pytest.fixture(autouse=True)
def _clean():
    from src.services import rate_slot
    rate_slot.reset_for_tests()
    yield
    rate_slot.reset_for_tests()


# ---------------------------------------------------------------------------
# ① 전제 — 워커가 둘 이상이다
# ---------------------------------------------------------------------------

def test_worker_count_is_more_than_one():
    """이 계약의 **전제** — Z10-C(2026-10-13 OOM)로 기본 워커는 1(상한 `GUNICORN_MAX_WORKERS`)이 됐다. 그래도 서버 전역
    차례표는 남긴다: 배포 순간 새·옛 인스턴스가 겹치고, 플랜을 올려 상한을 풀면 워커가 다시 둘 이상이 된다."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("gconf_z10c", ROOT / "gunicorn.conf.py")
    for env, want in (({}, 1), ({"GUNICORN_WORKERS": "2"}, 1), ({"GUNICORN_WORKERS": "2", "GUNICORN_MAX_WORKERS": "2"}, 2)):
        old = {k: os.environ.get(k) for k in ("GUNICORN_WORKERS", "GUNICORN_MAX_WORKERS")}
        try:
            for k in old:
                os.environ.pop(k, None)
            os.environ.update(env)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            assert mod.workers == want and mod.worker_class == "gthread" and mod.threads == 8
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    sh = (ROOT / "scripts/start_render.sh").read_text(encoding="utf-8")
    assert "--workers" not in sh and "--config gunicorn.conf.py" in sh       # 진입점이 conf 상한을 덮지 않는다


def test_translate_takes_a_server_wide_turn():
    """번역이 **서버 전역 차례표**를 탄다 — 프로세스 잠금만 있으면 워커 수만큼 넘긴다."""
    src = (ROOT / "src/services/image_translate_tencent.py").read_text(encoding="utf-8")
    assert "from src.services import rate_slot" in src
    assert "rate_slot.wait_turn(RATE_KEY" in src
    # 기다림은 잠금 **밖**이어야 한다(DB 연결을 붙잡은 채 자지 않는다).
    body = src.split("cli = _client(", 1)[1][:1200]
    # Z8: 잠금은 `try_lock(_GATE, …)`(5초 상한)으로 잡는다 — 차례 기다림은 여전히 그 **앞**(잠금 밖).
    assert body.index("rate_slot.wait_turn") < body.index("try_lock(_GATE")


# ---------------------------------------------------------------------------
# ② 진짜 두 프로세스
# ---------------------------------------------------------------------------

def _child(key, n, out):
    """자식 프로세스 — 부모와 **메모리를 공유하지 않는다**(그게 이 계약의 요점이다)."""
    import sys
    sys.path.insert(0, str(ROOT))
    from src.services import rate_slot
    got = []
    for _ in range(n):
        r = rate_slot.reserve(key, KEY_IV)
        got.append((time.time() + float(r["wait"]), r["backend"]))
    out.put(got)


@pytest.mark.skipif(not _PG, reason="DATABASE_URL 미설정 — 프로세스 사이 약속은 공유 저장소가 있어야 잰다")
def test_two_processes_never_share_a_slot():
    """★ **두 프로세스**가 같은 줄을 선다 — 차례 사이가 1.0초 아래로 좁아지지 않는다.

    F25의 `threading.Lock`은 여기서 아무 일도 하지 않는다(메모리가 다르다).
    그래서 이 계약은 서버 전역 차례표가 **실제로** 있는지를 잰다.
    """
    from src.db import pg
    pg.init_schema()

    key = f"test:{time.time()}"
    ctx = mp.get_context("spawn")            # fork면 부모 메모리를 물려받아 재는 뜻이 흐려진다
    q = ctx.Queue()
    ps = [ctx.Process(target=_child, args=(key, 3, q)) for _ in range(2)]
    for p in ps:
        p.start()
    slots = []
    for _ in ps:
        slots.extend(q.get(timeout=60))
    for p in ps:
        p.join(timeout=60)

    assert len(slots) == 6
    assert all(b == "server" for _t, b in slots), "서버 차례표를 안 탔다"
    times = sorted(t for t, _b in slots)
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert all(g >= 1.0 for g in gaps), f"두 프로세스의 차례가 겹쳤다: {gaps}"


@pytest.mark.skipif(not _PG, reason="DATABASE_URL 미설정")
def test_first_caller_does_not_wait():
    """줄이 비어 있으면 **기다리지 않는다** — 안전을 이유로 늘 1초를 버리지 않는다."""
    from src.db import pg
    from src.services import rate_slot
    pg.init_schema()
    r = rate_slot.reserve(f"test:{time.time()}", KEY_IV)
    assert r["backend"] == "server"
    assert r["wait"] < 0.2, f"첫 호출이 {r['wait']}초를 기다린다"


# ---------------------------------------------------------------------------
# ③ 폴백 — 죽어도 멈추지 않되, 범위가 바뀐 사실은 말한다
# ---------------------------------------------------------------------------

def test_process_fallback_still_serializes_within_one_process(monkeypatch):
    """PG가 없으면 프로세스 범위로 지킨다. 워커가 하나인 개발 환경에선 그걸로 족하다."""
    from src.services import rate_slot
    monkeypatch.setattr(rate_slot, "_pg_ready", lambda: False)
    key = "local-test"
    a = rate_slot.reserve(key, 0.5)
    b = rate_slot.reserve(key, 0.5)
    assert a["backend"] == "process" and b["backend"] == "process"
    assert a["wait"] < 0.05
    assert b["wait"] >= 0.45, "같은 프로세스 안에서도 차례가 겹쳤다"


def test_backend_is_reported_not_assumed(monkeypatch):
    """**어느 범위로 지켰는지**를 돌려준다.

    「지키고 있다」와 「이 환경에선 그걸로 족하다」는 다른 말이다 —
    둘을 구분해 두지 않으면, 워커를 늘리는 날 아무도 이 차이를 떠올리지 못한다.
    """
    from src.services import rate_slot
    monkeypatch.setattr(rate_slot, "_pg_ready", lambda: False)
    assert rate_slot.reserve("k", 0.0)["backend"] == "process"


def test_broken_slot_table_does_not_block_translation(monkeypatch):
    """차례표가 죽어도 번역을 막지 않는다 — 다만 **범위가 좁아진 채로** 계속한다."""
    from src.services import rate_slot

    class _Boom:
        def __enter__(self): raise RuntimeError("db down")
        def __exit__(self, *a): return False

    monkeypatch.setattr(rate_slot, "_pg_ready", lambda: True)
    monkeypatch.setattr("src.db.pg.tx", lambda: _Boom())
    out = rate_slot.reserve("k", 0.0)
    assert out["backend"] == "process", "차례표가 죽자 번역까지 멈췄다"


def test_a_very_long_queue_is_reported_instead_of_slept(monkeypatch):
    """줄이 비정상적으로 길면 **자지 않고 알린다** — 요청이 1분 넘게 잠들어 있지 않게."""
    from src.services import rate_slot
    monkeypatch.setattr(rate_slot, "reserve",
                        lambda k, iv: {"wait": 999.0, "backend": "server"})
    t0 = time.monotonic()
    out = rate_slot.wait_turn("k", 1.1)
    assert time.monotonic() - t0 < 1.0, "긴 줄인데 그대로 잤다"
    assert out.get("too_long") is True and out["waited"] == 0.0


def test_translate_says_so_when_the_queue_is_too_long(monkeypatch):
    """줄이 길어 못 보냈으면 **가짜 성공이 아니라** 사유를 돌려준다."""
    from src.services import image_translate_tencent as tc
    monkeypatch.setenv("TENCENT_SECRET_ID", "id")
    monkeypatch.setenv("TENCENT_SECRET_KEY", "key")
    monkeypatch.setattr("src.services.rate_slot.wait_turn",
                        lambda k, iv: {"wait": 999.0, "backend": "server", "too_long": True})
    monkeypatch.setattr(tc, "fetch_image", lambda u: (b"img", ""))
    out = tc.translate_image(url="https://img.example/a.jpg")
    assert out["ok"] is False
    assert out["error_class"] == "RateQueueTooLong"
    assert "줄이 깁니다" in out["error_message"]


def test_stage11_is_applied_at_boot():
    src = (ROOT / "src/db/pg.py").read_text(encoding="utf-8")
    assert "schema_stage11.sql" in src
    sql = (ROOT / "src/db/schema_stage11.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS api_rate_slots" in sql
    assert "next_at" in sql
