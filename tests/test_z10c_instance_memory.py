"""Z10-C(오너 2026-10-13 20:09 KST — Render 512MB OOM): 잡은 상한 아래였는데 **워커 2개 합계**가 넘었다.

실측: 20:02 pv_job_peak 301(base 158 · +143) · 20:09 308(base 162 · +146) — 두 잡이 서로 다른 워커에서 돌았고
각 워커가 base 160에 잡 몫까지 쥔 채 남았다. 그래서:
  ① 워커 1개 · 스레드 8(gthread) — `GUNICORN_MAX_WORKERS`(기본 1)로 묶는다(대시보드에 옛 2가 남아 있어도).
  ② 문지기는 **인스턴스 합계**(master + 워커 전부의 PSS, 운영에선 cgroup 익명 메모리와 큰 쪽):
     새 잡·크론은 420MB 이상이면 거부(「메모리 여유 없음 — 잠시 후」), 도는 잡은 460MB 넘으면 멈춤.
  ③ 기본 RSS 줄이기 — 병음 사전(pypinyin 구 사전 +44MB)을 끄고, anthropic SDK는 실제 호출 때만 올린다.
  ④ 실측 하네스(`scripts/z10c_measure.py`): 실제 gunicorn + 실제 BLACKHOLES 5장으로 동시 2건 합계 피크.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _limits_on(monkeypatch):
    """conftest는 테스트 프로세스(500MB+)가 거부되지 않게 문지기를 꺼 둔다 — 여기선 운영 기본값으로 켠다."""
    monkeypatch.setenv("INSTANCE_MEM_START_MAX_MB", "420")
    monkeypatch.delenv("PREVALIDATE_RSS_LIMIT_MB", raising=False)
    monkeypatch.delenv("INSTANCE_MEM_ABORT_MB", raising=False)


# ── ② 인스턴스 합계 ──────────────────────────────────────────────────────────────────────────

def test_outside_gunicorn_counts_only_this_process():
    """테스트·CI·개발 셸에선 이 프로세스만 센다 — 같은 기계의 다른 프로세스(브라우저·다른 셸)를 더하지 않는다."""
    from src.utils import rss
    assert rss.under_gunicorn() is False
    assert rss.family_pids() == [os.getpid()]
    cur = rss.instance_mb()
    own = rss.read_mb()[0]
    assert 0 < cur <= own + 5                       # PSS ≤ RSS


def test_under_gunicorn_sums_master_and_every_worker(monkeypatch):
    from src.utils import rss
    monkeypatch.setattr(rss, "under_gunicorn", lambda: True)
    monkeypatch.setattr(rss._os, "getppid", lambda: 100)
    monkeypatch.setattr(rss, "_children", lambda pid: [101, 102] if pid == 100 else [])
    pss = {100: 60 * 1024, 101: 170 * 1024, 102: 165 * 1024}                       # master + 워커 둘(KB)
    monkeypatch.setattr(rss, "_pss_kb", lambda pid: pss[pid])
    monkeypatch.setattr(rss, "cgroup_mb", lambda: 380)
    assert rss.family_pids() == [100, 101, 102]
    assert rss.processes_pss_mb() == 395
    assert rss.instance_mb() == 395                                                # PSS 합과 cgroup 중 큰 쪽
    monkeypatch.setattr(rss, "cgroup_mb", lambda: 430)
    assert rss.instance_mb() == 430


def test_cgroup_counts_anonymous_memory_not_file_cache(monkeypatch):
    """cgroup 사용량 전체(파일 캐시 포함)로 재면 캐시만으로 「여유 없음」이 된다 — 익명 메모리(anon + shmem)만."""
    from src.utils import rss
    stat = {("/sys/fs/cgroup/memory.stat", "anon"): 300 * 1048576, ("/sys/fs/cgroup/memory.stat", "shmem"): 4 * 1048576,
            ("/sys/fs/cgroup/memory.stat", "file"): 900 * 1048576}
    monkeypatch.setattr(rss, "_stat_value", lambda path, key: stat.get((path, key), -1))
    assert rss.cgroup_mb() == 304
    v1 = {("/sys/fs/cgroup/memory/memory.stat", "total_rss"): 200 * 1048576,
          ("/sys/fs/cgroup/memory/memory.stat", "total_shmem"): 0,
          ("/sys/fs/cgroup/memory/memory.stat", "total_cache"): 800 * 1048576}
    monkeypatch.setattr(rss, "_stat_value", lambda path, key: v1.get((path, key), -1))
    assert rss.cgroup_mb() == 200


def test_under_gunicorn_needs_gunicorn_as_the_parent_program(monkeypatch, tmp_path):
    """셸 명령 문자열 어딘가에 'gunicorn'이 들어 있다고(예: `bash -c "… gunicorn …"`) 운영으로 보지 않는다."""
    from src.utils import rss
    real_open = open

    def fake_open(path, *a, **k):
        if str(path).endswith("/cmdline") and "/proc/" in str(path):
            return real_open(tmp_path / "cmd", *a, **k)
        return real_open(path, *a, **k)
    monkeypatch.setattr("builtins.open", fake_open)
    (tmp_path / "cmd").write_bytes(b"/bin/bash\0-c\0cd x && gunicorn src.order_webhook:app\0")
    assert rss.under_gunicorn() is False
    (tmp_path / "cmd").write_bytes(b"/usr/bin/python3\0/usr/local/bin/gunicorn\0src.order_webhook:app\0")
    assert rss.under_gunicorn() is True
    (tmp_path / "cmd").write_bytes(b"gunicorn: master [src.order_webhook:app]\0")
    assert rss.under_gunicorn() is True


def test_start_and_abort_limits(monkeypatch):
    from src.utils import rss
    monkeypatch.delenv("INSTANCE_MEM_START_MAX_MB", raising=False)
    assert rss.start_limit_mb() == 420 and rss.job_limit_mb() == 460
    monkeypatch.setattr(rss, "instance_mb", lambda: 419)
    assert rss.start_ok() == (True, 419, 420)
    monkeypatch.setattr(rss, "instance_mb", lambda: 420)
    assert rss.start_ok() == (False, 420, 420)
    monkeypatch.setenv("INSTANCE_MEM_START_MAX_MB", "0")                            # 0 = 끈다
    assert rss.start_ok()[0] is True
    # 옛 이름(대시보드에 남은 값)은 새 이름이 없을 때만 쓴다
    monkeypatch.setenv("PREVALIDATE_RSS_LIMIT_MB", "400")
    assert rss.job_limit_mb() == 400
    monkeypatch.setenv("INSTANCE_MEM_ABORT_MB", "460")
    assert rss.job_limit_mb() == 460


def test_running_job_stops_on_instance_total_not_own_rss(monkeypatch):
    """이 워커는 작아도(150) 인스턴스 합계가 460을 넘으면 그 잡을 멈춘다 — 20:09의 경우."""
    from src.utils import rss
    for k in ("INSTANCE_MEM_ABORT_MB", "PREVALIDATE_RSS_LIMIT_MB"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(rss, "read_mb", lambda: (150, 160))
    monkeypatch.setattr(rss, "instance_mb", lambda: 455)
    tok = rss.JOB.set("z10c-job")
    try:
        rss.guard("image_fetch")                                                    # 455 ≤ 460 — 계속
        monkeypatch.setattr(rss, "instance_mb", lambda: 471)
        with pytest.raises(rss.MemoryCapExceeded) as e:
            rss.guard("image_fetch", "사진 2/5장째")
        assert "인스턴스 합계 471MB" in str(e.value) and "상한 460MB" in str(e.value)
    finally:
        rss.JOB.reset(tok)


# ── ② 거부: 사전검증 · 크론 · 이미지 번역 큐 ──────────────────────────────────────────────────

def _client(seller):
    from src.order_webhook import app
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    return c


def test_prevalidate_full_instance_waits_and_retries_once(monkeypatch):
    """Y11-O(오너 2026-10-15): 503 「잠시 후 다시 눌러」 대신 — 잡을 받고(202) 30초 뒤 한 번 더 스스로 잰다. 그래도 차 있으면
    마켓 줄 「검증 못 함 — 메모리 여유가 없어요(… 30초 뒤 다시 재도 같았어요)」."""
    import src.seller_console.views as V
    from src.utils import rss
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: object())
    monkeypatch.setattr(V, "_PV_MEM_RETRY_SEC", 0.05)
    seen = []
    monkeypatch.setattr(rss, "instance_mb", lambda: seen.append(1) or 433)
    c = _client("z10c-pv")
    r = c.post("/seller/collect/prevalidate", json={"product": {"title": "x", "price": 1}, "markets": ["elevenst"]})
    d = r.get_json()
    assert r.status_code == 202 and d["job_id"]
    for _ in range(200):
        d2 = c.get(d["poll"]).get_json()
        if d2.get("state") == "done":
            break
        time.sleep(0.05)
    row = d2["results"][0]
    assert row["transport"] == "memory" and "30초 뒤 다시 재도 같았어요" in row["message"] + " ".join(row.get("details") or [])
    mw = V._pv_store().state_get(V._PV_JOB_KEY + d["job_id"])["mem_wait"]
    assert mw["retry"] is True and mw["first_mb"] == 433 and mw["second_mb"] == 433 and mw["limit_mb"] == 420


def test_prevalidate_memory_frees_within_retry_then_runs(monkeypatch):
    """첫 잼엔 433MB, 30초 뒤엔 300MB — 스스로 다시 시작한다(오너가 다시 누르지 않아도)."""
    import src.seller_console.views as V
    from src.utils import rss
    ran = []
    monkeypatch.setattr(V, "_pv_job_body", lambda job_id, data, markets, dispatcher: ran.append(job_id) or V._pv_update(job_id, state="done"))
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: object())
    monkeypatch.setattr(V, "_PV_MEM_RETRY_SEC", 0.05)
    vals = iter([433] + [300] * 50)
    monkeypatch.setattr(rss, "instance_mb", lambda: next(vals))
    c = _client("z10c-pv2")
    d = c.post("/seller/collect/prevalidate", json={"product": {"title": "x", "price": 1}, "markets": ["elevenst"]}).get_json()
    for _ in range(200):
        if ran:
            break
        time.sleep(0.05)
    assert ran == [d["job_id"]]
    mw = V._pv_store().state_get(V._PV_JOB_KEY + d["job_id"])["mem_wait"]
    assert mw["retry"] is True and mw["first_mb"] == 433 and mw["second_mb"] == 300


def test_queued_prevalidate_does_not_start_if_memory_filled_while_waiting(monkeypatch):
    """줄 서 있던 사이 메모리가 찼으면 시작하지 않는다 — 마켓 줄은 「검증 못 함 — 메모리 여유 없음」, 자리는 바로 돌려준다."""
    monkeypatch.setenv("PREVALIDATE_JOB_CONCURRENCY", "1")
    import src.seller_console.views as V
    from src.utils import rss
    started, gate = threading.Event(), threading.Event()
    real_body = V._pv_job_body

    def body(job_id, data, markets, dispatcher):
        if data["product"]["title"] == "a":
            started.set()
            gate.wait(5)
            V._pv_update(job_id, state="done")
            return
        return real_body(job_id, data, markets, dispatcher)                    # 안 불려야 한다
    monkeypatch.setattr(V, "_pv_job_body", body)
    monkeypatch.setattr(V, "_get_upload_dispatcher", lambda: object())
    monkeypatch.setattr(rss, "instance_mb", lambda: 200)                         # 처음엔 여유(풀 스위트 프로세스는 500MB+)
    c = _client("z10c-q")
    j1 = c.post("/seller/collect/prevalidate", json={"product": {"title": "a"}, "markets": ["elevenst"]}).get_json()
    assert started.wait(5)
    j2 = c.post("/seller/collect/prevalidate", json={"product": {"title": "b"}, "markets": ["elevenst"]}).get_json()
    monkeypatch.setattr(rss, "instance_mb", lambda: 440)                         # 기다리는 사이 다른 일로 찼다
    monkeypatch.setattr(V, "_PV_MEM_RETRY_SEC", 0.05)                            # Y11-O: 30초 뒤 한 번 더(테스트는 짧게)
    gate.set()
    for _ in range(100):
        d2 = c.get(j2["poll"]).get_json()
        if d2.get("state") == "done":
            break
        time.sleep(0.05)
    row = d2["results"][0]
    assert d2["state"] == "done" and row["transport"] == "memory" and row["ok"] is False and row["hold"] is False
    assert "메모리 여유가 없어요" in row["message"] and "440MB" in row["message"] and "30초 뒤 다시 재도" in row["message"]
    assert c.get(j1["poll"]).get_json()["state"] == "done"
    assert V._pv_semaphore().acquire(timeout=2)                                 # 자리를 돌려줬다
    V._pv_semaphore().release()


def test_cron_job_refused_with_503(monkeypatch):
    from src.utils import bg_job, rss
    ran = []
    monkeypatch.setattr(rss, "instance_mb", lambda: 425)
    started, st = bg_job.start("z10c-cron", lambda: ran.append(1) or {"ok": True})
    assert started is False and st["busy_memory"] is True and st["state"] == "refused"
    assert st["error"] == rss.BUSY_MESSAGE
    from src.order_webhook import app
    with app.test_request_context():
        resp, code = bg_job.accepted("z10c-cron", started, st)
    assert code == 503 and resp.get_json()["memory_mb"] == 425
    time.sleep(0.1)
    assert ran == []


def test_image_translate_queue_waits_instead_of_starting(monkeypatch):
    from src.db import image_translate_queue_pg as q
    from src.services import image_translate_auto as A
    from src.utils import rss
    q.reset_for_tests()
    try:
        q.enqueue("z10c-u", "z10c-item", [("gallery", 0)])
        sent = []
        monkeypatch.setattr(A, "_translate_job", lambda job: sent.append(job) or ("done", ""))
        monkeypatch.setattr(rss, "instance_mb", lambda: 430)
        assert A._drain() == 0 and sent == []
        assert q.counts("z10c-item")["queued"] == 1                     # 대기로 남았다(사라지지 않음)
        monkeypatch.setattr(rss, "instance_mb", lambda: 200)
        assert A._drain() == 1 and len(sent) == 1
    finally:
        q.reset_for_tests()


# ── ③ 기본 RSS — 병음 사전 ─────────────────────────────────────────────────────────────────────

def test_romanize_does_not_load_the_phrase_dictionary():
    """pypinyin 구(句) 사전은 +44MB(실측 61 → 17). 브랜드 한자 병음엔 낱글자 사전으로 충분하다 — 결과가 같아야 한다."""
    code = ("import sys,os;sys.path.insert(0,os.getcwd());from src.collectors import ko_polish as K;"
            "print(K.romanize('北京故宫'));print('pypinyin.phrases_dict' in sys.modules)")
    env = {k: v for k, v in os.environ.items() if k != "PYPINYIN_NO_PHRASES"}
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
    lines = out.stdout.strip().splitlines()
    assert lines[-1] == "False", out.stderr[-500:]
    assert lines[-2].replace(" ", "").upper() == "BEIJINGGUGONG"


# ── ④ 실측: 실제 gunicorn(워커 1개) · 동시 2건 합계 피크 ≤ 450 ──────────────────────────────────

@pytest.mark.skipif(not Path("/proc/self/smaps_rollup").exists(), reason="리눅스 /proc 필요(PSS)")
def test_concurrent_prevalidate_and_preview_stay_under_450mb(tmp_path):
    pytest.importorskip("gunicorn")
    env = dict(os.environ, Z10C_QUICK="1", Z10C_CDN_DIR=str(tmp_path))
    for k in ("GUNICORN_WORKERS", "GUNICORN_MAX_WORKERS", "GUNICORN_THREADS", "INSTANCE_MEM_START_MAX_MB",
              "PREVALIDATE_RSS_LIMIT_MB", "INSTANCE_MEM_ABORT_MB"):
        env.pop(k, None)                                                        # 운영 기본값 그대로 띄운다
    out = subprocess.run([sys.executable, str(ROOT / "scripts/z10c_measure.py"), str(ROOT), "pytest"],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=240)
    assert out.returncode == 0, out.stderr[-2000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    assert d["workers"] == 1                                                    # 운영 설정 그대로 띄웠다
    assert d["prodload_workers_hit"] == 1                                       # 병음·anthropic·DB 드라이버까지 올린 뒤
    c = d["concurrent"][0]
    assert c["prevalidate_state"] == "done" and c["preview_status"] == 200
    assert d["concurrent_peak_max_mb"] <= 450, d
