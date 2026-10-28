"""순찰 118b(감독 10-26 14:35 · 재게시 10-28) — 배포 뒤 「떴지만 안 받는」 날 스스로 알아채고 스스로 다시 뜬다.

재현 기록: 10-25 19:34(159분) · 10-26 13:56 — 둘 다 docs만 바뀐 배포 직후, `rss:restart`에 워커 boot 줄이 하나 모자라고
공개 `/health`·`/`가 TCP 타임아웃(포트는 열렸는데 받는 프로세스가 없다). 둘 다 빈 커밋 재배포로만 풀렸다.

- **3단계 줄:** 마스터 준비(`when_ready`) · 포크 시작/끝(`pre_fork`) · 워커 준비(`post_worker_init`)를 **로컬 파일**에 적는다
  (DB 아님 — 포크 직전 마스터가 DB·스레드 잠금을 쥐지 않게). 워커가 뜨면 그 단계를 `boot` 줄에 같이 싣는다.
- **마스터 감시(데몬 스레드 하나 · 잠만 잔다):** 아래면 `boot_stuck` 한 줄을 남기고 워커를 죽인 뒤 마스터가 나간다 → Render가 컨테이너를
  다시 띄운다(빈 커밋 재배포와 같은 효과를 사람 없이).
  - 포크가 `FORK_STUCK_SEC`(60) 넘게 안 끝남 = 마스터가 포크 전에서 멈춤(이러면 gunicorn 자기 감시도 안 돈다)
  - 포크 뒤 `READY_SEC`(180 — gunicorn timeout 120 뒤 한 번 더 갈아끼울 틈) 넘게 어떤 워커도 준비 안 됨
  - 워커 준비 뒤 `PROBE_WINDOW_SEC`(600) 동안 자기 `/health`를 `PROBE_EVERY_SEC`(60)마다 쳐서 한 번 붙으면 끝 ·
    `PROBE_FAILS`(3)번 연속 안 붙으면(TCP 타임아웃 = 그 증상) 나간다. 바쁜 운영 중에는 치지 않는다(부팅 창에서만).
- `KGP_BOOT_WATCH=0`이면 감시를 안 띄운다 · `KGP_BOOT_WATCH_EXIT=0`이면 줄만 남기고 나가지 않는다.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

STAGES = ("master_ready", "fork_start", "fork_done", "worker_ready")


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default)) or default))
    except ValueError:
        return default


def stage_file() -> str:
    return os.getenv("KGP_BOOT_STAGE_FILE", "/tmp/kgp_boot_stages.json")


def fork_stuck_sec() -> int:
    return _int_env("KGP_BOOT_FORK_STUCK_SEC", 60)


def ready_sec() -> int:
    return _int_env("KGP_BOOT_READY_SEC", 180)


def probe_window_sec() -> int:
    return _int_env("KGP_BOOT_PROBE_WINDOW_SEC", 600)


def probe_every_sec() -> int:
    return _int_env("KGP_BOOT_PROBE_EVERY_SEC", 60)


def probe_fails() -> int:
    return _int_env("KGP_BOOT_PROBE_FAILS", 3)


def read() -> Dict[str, Any]:
    try:
        with open(stage_file(), encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def mark(stage: str, **kw: Any) -> None:
    """한 단계를 적는다(벽시계 초 · pid). 파일 하나를 통째로 다시 쓴다 — 잠금 없음, 실패해도 부팅은 그대로."""
    if stage not in STAGES:
        return
    cur = read() if stage != "master_ready" else {}
    cur[stage] = {"t": time.time(), "pid": os.getpid(), **kw}
    if stage == "fork_done":                                      # 이번 포크 묶음에서 아직 준비 안 된 첫 포크 끝 시각
        cur.setdefault("unready_since", cur[stage]["t"])
    if stage == "worker_ready":
        cur.pop("unready_since", None)
    try:
        tmp = stage_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cur, fh)
        os.replace(tmp, stage_file())
    except OSError as exc:
        logger.debug("[부팅 감시] 단계 기록 실패 %s: %s", stage, exc)


def summary(st: Optional[Dict[str, Any]] = None, now: Optional[float] = None) -> Dict[str, Any]:
    """`boot` 줄에 싣는 단계 요약 — 마스터 준비부터 각 단계까지 초."""
    st = read() if st is None else st
    now = time.time() if now is None else now
    base = (st.get("master_ready") or {}).get("t")
    out: Dict[str, Any] = {}
    for s in STAGES:
        t = (st.get(s) or {}).get("t")
        if t is not None:
            out[s] = round(t - base, 1) if base else 0.0
    if base:
        out["master_age_sec"] = round(now - base, 1)
    return out


def verdict(st: Dict[str, Any], now: float) -> Optional[Dict[str, Any]]:
    """멈춤 판정(순수 함수) — `{stage, since_sec}` 또는 None.

    - `pre_fork`: 포크 시작이 포크 끝보다 늦고 `fork_stuck_sec` 넘게 지남
    - `worker_init`: 포크 끝 뒤 어떤 워커도 준비 안 된 채 `ready_sec` 넘게 지남(gunicorn이 갈아끼워도 묶음의 처음부터 잰다)
    """
    fs, fd, wr = (st.get(k) or {} for k in ("fork_start", "fork_done", "worker_ready"))
    if fs.get("t") and (not fd.get("t") or fd["t"] < fs["t"]) and now - fs["t"] >= fork_stuck_sec():
        return {"stage": "pre_fork", "since_sec": round(now - fs["t"], 1)}
    since = st.get("unready_since")
    if fd.get("t") and since and (not wr.get("t") or wr["t"] < since) and now - since >= ready_sec():
        return {"stage": "worker_init", "since_sec": round(now - since, 1)}
    return None


def _probe(port: str, timeout: float = 15.0) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as resp:
            return 0 < int(resp.status) < 600                    # 503(틱 공백)도 「받는다」 — 여기서 보는 건 닿느냐
    except Exception as exc:                                       # noqa: BLE001
        code = getattr(exc, "code", None)
        return bool(code)                                          # HTTPError(503 등) = 응답은 왔다


def _record(row: Dict[str, Any], wait: float = 10.0) -> None:
    """DB 한 줄 — 따로 스레드에서, `wait`초만 기다린다(DB가 멎어도 나가는 길은 막지 않는다)."""
    def _w():
        from src.utils import restart_log as _rl
        _rl.append("boot_stuck", **row)
    t = threading.Thread(target=_w, name="boot-stuck-record", daemon=True)
    t.start()
    t.join(wait)


def bail(server: Any, why: Dict[str, Any], *, exit_fn: Callable[[int], None] = os._exit) -> Dict[str, Any]:
    """멈춤 — 줄을 남기고(워커 pid·단계 요약) 워커를 죽이고 마스터가 나간다(`KGP_BOOT_WATCH_EXIT=0`이면 줄만)."""
    workers = sorted(int(p) for p in (getattr(server, "WORKERS", None) or {}))
    row = dict(why, pid=os.getpid(), workers=workers, stages=summary(), exit=os.getenv("KGP_BOOT_WATCH_EXIT", "1") != "0")
    logger.critical("[부팅 감시] 멈춤 — %s %.0f초 · 워커 %s → %s", why.get("stage"), why.get("since_sec") or 0, workers,
                    "마스터 종료(Render가 다시 띄움)" if row["exit"] else "기록만")
    _record(row)
    if row["exit"]:
        for p in workers:
            try:
                os.kill(p, signal.SIGKILL)
            except OSError:
                pass
        exit_fn(3)
    return row


def _loop(server: Any, port: str, *, sleep: Callable[[float], None] = time.sleep, stop: Optional[threading.Event] = None) -> None:
    probe_gen, fails, last_probe = None, 0, 0.0
    while not (stop and stop.is_set()):
        sleep(5)
        now = time.time()
        st = read()
        why = verdict(st, now)
        if why:
            bail(server, why)
            return
        wr = st.get("worker_ready") or {}
        if not wr.get("t") or now - wr["t"] > probe_window_sec():
            continue
        gen = (wr.get("pid"), wr.get("t"))
        if gen == probe_gen and fails < 0:                         # 이 워커 세대는 이미 한 번 붙었다
            continue
        if gen != probe_gen:
            probe_gen, fails, last_probe = gen, 0, 0.0
        if now - last_probe < probe_every_sec():
            continue
        last_probe = now
        if _probe(port):
            fails = -1
            continue
        fails += 1
        logger.warning("[부팅 감시] 자기 /health 안 닿음 %d/%d (워커 %s)", fails, probe_fails(), wr.get("pid"))
        if fails >= probe_fails():
            bail(server, {"stage": "no_response", "since_sec": round(now - wr["t"], 1), "probe_fails": fails})
            return


def start(server: Any) -> Optional[threading.Thread]:
    """`when_ready`에서 한 번 — 마스터 준비를 적고 감시 스레드를 띄운다."""
    mark("master_ready")
    if os.getenv("KGP_BOOT_WATCH", "1") == "0":
        return None
    port = os.getenv("PORT", "8000")
    try:
        addr = getattr(getattr(server, "cfg", None), "bind", None) or []
        if addr and ":" in str(addr[0]):
            port = str(addr[0]).rsplit(":", 1)[1]
    except Exception:                                              # noqa: BLE001
        pass
    t = threading.Thread(target=_loop, args=(server, port), name="boot-watch", daemon=True)
    t.start()
    return t
