"""Y15 순찰 73(오너 2026-10-24) — 재시작 사유·시간 기록(`rss:restart`) · 요청 없음 감시 · 틱 공백 경고 20분 · 화면 등록 메모리 측정."""
import importlib.util
import os
from datetime import datetime, timedelta, timezone


def _mem(monkeypatch):
    from src.db import image_translate_queue_pg as st
    monkeypatch.setattr(st, "_enabled", lambda: False)
    monkeypatch.setattr(st, "_MEM_STATE", {})
    return st


def test_boot_pairs_with_our_exit_or_says_outside(monkeypatch):
    _mem(monkeypatch)
    from src.utils import restart_log as R
    R.note_exit("인스턴스 합계", pid=73, worker_mb=343, inst_mb=421, worker_limit=380, inst_limit=420)
    t = datetime.fromisoformat(R.rows()[-1]["at"])
    b = R.note_boot(203, 150, now=t + timedelta(seconds=12))
    assert b["after_exit_sec"] == 12.0 and b["reason"] == "인스턴스 합계" and b["prev_pid"] == 73
    # 우리 상한 기록 없이 뜬 부팅(배포·Render 재시작) — 「바깥」이라고 적는다
    b2 = R.note_boot(301, 150, now=datetime.now(timezone.utc) + timedelta(hours=1))
    assert b2["outside"] is True and "after_exit_sec" not in b2
    assert [r["kind"] for r in R.rows()] == ["exit", "boot", "boot"]


def test_quiet_is_noted_once_per_gap_and_reset_by_a_request(monkeypatch):
    _mem(monkeypatch)
    from src.utils import restart_log as R
    monkeypatch.setenv("HTTP_QUIET_MIN", "10")
    R.touch_request()
    base = R._LAST_REQ["at"]
    assert R.check_quiet(base + 9 * 60) is None                     # 9분 — 아직
    row = R.check_quiet(base + 26 * 60)                             # 10-24 01:21~01:48과 같은 26분
    assert row["idle_min"] == 26.0 and row["threads"] and isinstance(row["active"], list)
    assert R.check_quiet(base + 31 * 60) is None                     # 같은 공백은 한 줄
    R.touch_request()
    assert R.check_quiet(R._LAST_REQ["at"] + 11 * 60)["idle_min"] == 11.0
    assert [r["kind"] for r in R.rows()] == ["quiet", "quiet"]


def test_tick_gap_alert_default_is_20_minutes(monkeypatch):
    from src.services import tick_watch as T
    monkeypatch.delenv("TICK_GAP_ALERT_MIN", raising=False)
    assert T.gap_alert_min() == 20
    now = datetime(2026, 10, 24, 1, 45, tzinfo=timezone.utc)
    st = lambda _n: {"seen": True, "age_min": 25, "last_at": "2026-10-24T01:20:42+00:00"}   # noqa: E731
    sent = []
    r = T.check_gap(now, status_fn=st, take_fn=lambda k, n: (True, 1), send_fn=lambda m, lv: sent.append(m) or True)
    assert r["alert"] and "25분 공백" in sent[0]                   # 30분 기준이면 이 25분은 조용했다


def _gunicorn_conf():
    p = os.path.join(os.path.dirname(__file__), "..", "gunicorn.conf.py")
    spec = importlib.util.spec_from_file_location("gconf_p73", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_rss_restart_writes_reason_and_mb(monkeypatch, tmp_path):
    _mem(monkeypatch)
    from src.utils import restart_log as R
    g = _gunicorn_conf()
    monkeypatch.setattr(g, "_RSS_LIMIT_MB", 380)
    monkeypatch.setattr(g, "_RSS_STAMP", str(tmp_path / "stamp"))
    monkeypatch.setattr(g, "_worker_rss_mb", lambda: 395)
    monkeypatch.setattr(g, "_active_jobs", lambda: [])

    class _Log:
        def warning(self, *a, **k):
            pass

    class _W:
        alive, pid, log = True, 4242, _Log()
    w = _W()
    g.post_request(w, None, None, None)
    assert w.alive is False
    row = R.rows()[-1]
    assert row["kind"] == "exit" and row["reason"] == "워커 RSS" and row["worker_mb"] == 395 and row["worker_limit"] == 380


def test_screen_register_measures_but_oneshot_register_does_not_double(monkeypatch):
    from src.seller_console import views as V
    from src.services import oneshot_ops as O
    from src.utils import render_worker as RW
    from src.utils import rss
    monkeypatch.setenv("MEMPROBE", "1")
    got = []
    monkeypatch.setattr(RW, "record", lambda kind, **kw: got.append((kind, kw)))
    monkeypatch.setattr(rss, "release", lambda reason="": (330, 210))
    mp0 = V._reg_mem_before()
    V._reg_mem_after(mp0, "df0f8a8c-73a3", ["coupang:gogane", "smartstore:chezgoga"])
    kind, kw = got[-1]
    assert kind == "reg_job" and kw["item"] == "df0f8a8c" and (kw["rel_before_mb"], kw["rel_after_mb"]) == (330, 210)
    # 무엇이 늘었는지(type 상위)는 힙에 따라 다르다 — 큰 힙(전체 스위트)에선 다른 type이 위로 온다. 여기선 표의 모양만
    assert isinstance(kw["types"], list) and all(len(t) == 3 for t in kw["types"]) and isinstance(kw["caches"], list)
    tok = O._CURRENT_ROW.set({"op": "register"})
    try:
        assert V._reg_mem_before() is None                          # 일회성 줄은 op_job이 이미 잰다
    finally:
        O._CURRENT_ROW.reset(tok)
