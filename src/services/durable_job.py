"""오너 11-27 02:07 ②③ — 재시작에 죽지 않는 긴 작업(관리자 실행 화면 공용).

예전: `bg_job.start`(프로세스 안 스레드) 하나로 끝까지 돌았다 → 일꾼이 새로 뜨면 스레드가 사라지고 화면은 「도는 중」에 고정 · 실패 표시
없음 · 기록이 「running」으로 남아 다시 누르면 「이미 도는 중」으로 거부(셰고가 목록 만들기 17:37 · 타오바오 재보강 17:38).

이제 작업 한 건 = app_state 한 줄(`key`) — 그 안에 단계 커서·진행·하트비트(`heartbeat_at`)·잡은 일꾼(`holder`):
  · `begin` — 줄을 세우고 바로 이 일꾼 스레드에서 돈다(즉시 시작).
  · `drive` — 짧은 걸음(`step`, ~20초)마다 진행을 저장한다. 스레드가 죽어도 저장한 데까지는 남는다(처음부터 다시 안 함).
  · `tick` — 10분 틱·부팅 때 부른다. 하트비트가 `STALE_SEC` 넘게 멈춘 「running」 줄을 이어서 돌린다.
  · `status` — 화면용. 「running」인데 `STALL_SEC` 넘게 진전이 없으면 `stalled` → 화면 「멈췄어요 — 이어서 하기」(`resume`).
  · 끝나면(`done`·`failed`·`stopped`) 시작한 사람에게 푸시 한 통(키·기기 없으면 조용히 건너뜀).
마켓 전송 여부는 각 작업이 정한다(이 모듈은 돌리기만).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)

STALE_SEC = 180            # 하트비트가 이보다 오래 멈췄으면 다른 일꾼(틱)이 이어받는다
STALL_SEC = 300            # 화면이 「멈췄어요」라고 말하는 문턱(오너: 5분 넘게 진전 없으면)
STEP_SEC = 20.0            # 한 걸음 예산 — 걸음마다 저장
INDEX_KEY = "djob:index"   # {key: kind} — 틱이 훑는 목록
#: 이 모듈 전에 스레드로 돌다 끊긴 기록 — 틱이 처음 볼 때 종류를 달아 이어 돈다(오너 11-26 17:38 타오바오 1/26 등)
_LEGACY = {"taobao_reenrich:batch": "taobao_reenrich", "smartstore_relist:run:chezgoga": "relist_run",
           "smartstore_relist:run:gocosmos": "relist_run"}
_KINDS: Dict[str, Callable] = {}
#: 틱·부팅은 이 모듈만 부른다 — 작업 종류를 등록하는 모듈을 그때 불러온다(등록 전 「모르는 종류」로 실패하지 않게)
_KIND_MODULES = {"relist_build": "src.services.smartstore_relist", "relist_run": "src.services.smartstore_relist",
                 "taobao_reenrich": "src.services.taobao_reenrich_batch", "bulk_collect": "src.api.extension_api",
                 "ocr_census": "src.services.ocr_compare_diag", "ncat_table": "src.dashboard.admin_views"}
_ME = f"{os.getenv('RENDER_INSTANCE_ID', 'local')}:{os.getpid()}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _age(iso: str) -> float:
    try:
        return time.time() - datetime.fromisoformat(str(iso)).timestamp()
    except Exception:                                              # noqa: BLE001 — 시각이 없으면 아주 오래된 것으로
        return 10 ** 9


def _st():
    from src.db import image_translate_queue_pg as st
    return st


def get(key: str) -> Dict:
    return dict(_st().state_get(key) or {})


def save(key: str, rec: Dict) -> None:
    _st().state_set(key, rec)


def register(kind: str, step: Callable) -> None:
    """`step(key, rec, deadline) -> rec` — 마감 전까지 한 덩이 하고 진행·커서를 rec에 적어 돌려준다.
    끝났으면 `rec["state"]`를 done·failed·stopped로, 푸시 문구는 `rec["push"] = {title, body, path}`."""
    _KINDS[kind] = step


def _step_for(kind: str):
    if kind not in _KINDS and kind in _KIND_MODULES:
        import importlib
        importlib.import_module(_KIND_MODULES[kind])
    return _KINDS.get(kind)


def _index_add(key: str, kind: str) -> None:
    idx = dict(_st().state_get(INDEX_KEY) or {})
    if idx.get(key) != kind:
        idx[key] = kind
        _st().state_set(INDEX_KEY, idx)


def begin(key: str, kind: str, rec: Dict, *, by_uid: str = "", start: bool = True, bg_name: str = "") -> Dict:
    """새로 시작 — rec(작업별 재료·커서)를 줄에 세우고 바로 돌린다(`start=False`면 줄만 — 부른 쪽이 `drive`를 띄운다)."""
    rec = dict(rec)
    rec.update(state="running", kind=kind, started_at=rec.get("started_at") or _now(), heartbeat_at=_now(), holder="",
               by_uid=str(by_uid or rec.get("by_uid") or ""), steps=int(rec.get("steps") or 0),
               bg_name=str(bg_name or rec.get("bg_name") or ""))
    save(key, rec)
    _index_add(key, kind)
    started = kick(key) if start else False
    return {"ok": True, "started": started, "rec": rec}


def kick(key: str) -> bool:
    """이 일꾼에서 스레드 하나로 끝까지(걸음마다 저장). 메모리 문지기가 거절하면 False — 틱이 다시 깨운다."""
    from src.utils import bg_job
    name = str(get(key).get("bg_name") or "") or f"djob:{key}"
    started, _st_ = bg_job.start(name, lambda: drive(key))
    return bool(started)


def drive(key: str, budget: Optional[float] = None) -> Dict:
    """줄이 끝날 때까지(또는 `budget`초) 걸음을 잇는다. 다른 일꾼이 하트비트를 살려 잡고 있으면 손대지 않는다."""
    t0 = time.time()
    while True:
        rec = get(key)
        if rec.get("state") != "running":
            return rec
        holder = str(rec.get("holder") or "")
        if holder and holder != _ME and _age(rec.get("heartbeat_at")) < STALE_SEC:
            return rec                                             # 살아 있는 다른 일꾼이 돈다
        step = _step_for(str(rec.get("kind") or ""))
        if step is None:
            rec.update(state="failed", error=f"모르는 작업 종류: {rec.get('kind')}", finished_at=_now())
            save(key, rec)
            return rec
        rec.update(holder=_ME, heartbeat_at=_now())
        save(key, rec)
        try:
            rec = step(key, rec, time.time() + STEP_SEC) or rec
        except Exception as exc:                                   # noqa: BLE001 — 한 걸음 실패는 사유째 멈춤(조용히 사라지지 않게)
            logger.warning("[긴 작업] %s 걸음 실패: %s", key, exc)
            rec = get(key)
            rec.update(state="failed", error=f"{type(exc).__name__}: {str(exc)[:240]}", finished_at=_now())
        rec["steps"] = int(rec.get("steps") or 0) + 1
        rec["heartbeat_at"] = _now()
        rec["progress_at"] = rec["heartbeat_at"]
        try:
            from src.utils.rss import read_mb
            cur, _peak = read_mb()
            if cur > 0:
                rec["rss_mb"] = cur
                rec["rss_peak_mb"] = max(int(rec.get("rss_peak_mb") or 0), cur)
        except Exception:                                          # noqa: BLE001
            pass
        if rec.get("state") != "running":
            rec.setdefault("finished_at", _now())
            rec["holder"] = ""
            save(key, rec)
            _notify(rec)
            logger.info("[긴 작업] %s 끝 — %s (%s걸음)", key, rec.get("state"), rec.get("steps"))
            return rec
        save(key, rec)
        if budget is not None and time.time() - t0 >= budget:
            rec["holder"] = ""
            save(key, rec)
            return rec


def _notify(rec: Dict) -> None:
    p = rec.get("push") if isinstance(rec.get("push"), dict) else {}
    uid = str(rec.get("by_uid") or "")
    if not (p.get("title") and uid):
        return
    try:
        from src.notifications.apns import notify
        notify(uid, str(p["title"]), str(p.get("body") or ""), str(p.get("path") or ""))
    except Exception as exc:                                       # noqa: BLE001 — 푸시 실패가 작업 결과를 바꾸지 않는다
        logger.warning("[긴 작업] 푸시 실패: %s", exc)


def status(key: str) -> Dict:
    rec = get(key)
    if rec.get("state") == "running":
        age = _age(rec.get("progress_at") or rec.get("heartbeat_at"))
        rec["stalled"] = age >= STALL_SEC
        rec["idle_sec"] = int(age)
    return rec


def resume(key: str, kind: str = "") -> Dict:
    """「이어서 하기」 — 「running」인데 아무도 안 잡고 있거나 하트비트가 멈췄으면 이 일꾼이 이어 돈다(커서에서).
    `kind`를 주면 예전 스레드가 남긴 기록(종류·목록 등록 없음)도 받아서 잇는다."""
    rec = get(key)
    if rec.get("state") != "running":
        return {"ok": False, "error": "도는 작업이 없어요."}
    if kind and not rec.get("kind"):
        rec["kind"] = kind
        save(key, rec)
    if rec.get("kind"):
        _index_add(key, str(rec["kind"]))
    if rec.get("holder") and rec.get("holder") != _ME and _age(rec.get("heartbeat_at")) < STALE_SEC:
        return {"ok": True, "started": False, "note": "다른 일꾼이 돌고 있어요 — 곧 진행이 움직여요."}
    rec["holder"] = ""
    rec["heartbeat_at"] = "1970-01-01T00:00:00+00:00"
    save(key, rec)
    return {"ok": True, "started": kick(key)}


def tick() -> Dict:
    """10분 틱·부팅 — 하트비트가 멈춘 「running」 줄을 깨운다. 끝난 줄은 목록에서 뺀다."""
    idx = dict(_st().state_get(INDEX_KEY) or {})
    for key, kind in _LEGACY.items():                              # 예전 스레드가 「running」으로 남긴 기록 — 종류를 달아 받는다
        try:
            rec = get(key)
        except Exception:                                          # noqa: BLE001
            continue
        if rec.get("state") == "running" and not rec.get("kind"):
            rec["kind"] = kind
            save(key, rec)
            idx[key] = kind
            _st().state_set(INDEX_KEY, idx)
    woke, keep = [], {}
    for key, kind in idx.items():
        rec = get(key)
        if rec.get("state") != "running":
            continue
        keep[key] = kind
        if _age(rec.get("heartbeat_at")) >= STALE_SEC:
            if kick(key):
                woke.append(key)
    if keep != idx:
        _st().state_set(INDEX_KEY, keep)
    if woke:
        logger.warning("[긴 작업] 멈춘 줄을 이어서 돌림: %s", woke)
    return {"running": list(keep), "woke": woke}


def boot_resume(delay: float = 45.0) -> None:
    """부팅 뒤 잠깐 기다렸다가(옛 일꾼의 하트비트가 식게) 한 번 깨운다 — 10분 틱을 기다리지 않는다."""
    def _later():
        try:
            from src.utils import shutdown as sd
            if sd.wait(delay):
                return
        except Exception:                                          # noqa: BLE001
            time.sleep(delay)
        try:
            # 부팅 직후엔 옛 일꾼 하트비트가 아직 「살아 있음」일 수 있다 — STALE_SEC 지난 뒤 한 번 더
            tick()
            from src.utils import shutdown as sd2
            if not sd2.wait(STALE_SEC):
                tick()
        except Exception as exc:                                   # noqa: BLE001
            logger.warning("[긴 작업] 부팅 이어하기 실패: %s", exc)
    threading.Thread(target=_later, name="djob-boot", daemon=True).start()
