"""W2(오너 2026-10-03) — 백그라운드 워커 **단일 실행**.

같은 DB를 Render 서비스 셋(본 `proxy-commerce` · `kohganeproxxxxy-singapore` · staging)이 쓴다.
워커가 요청을 받은 서비스마다 떠서, 번역 공급사 한도를 여러 서비스가 나눠 쓰고 누가 돌았는지 알 수 없었다.

- **게이트** `workers_enabled()`: 배포 컨테이너에선 `WORKERS_ENABLED=1`인 서비스만 워커를 띄운다(나머지는 **접수만**
  — 큐에 남고 사라지지 않는다). 로컬·테스트(배포 아님)는 예전처럼 돈다. `WORKERS_ENABLED=0`은 어디서든 끔.
- **리스** `lease(name)`: DB(`app_state worker_lease:<name>`)에 「지금 누가 돌리나」를 원자적으로 잡는다 —
  둘 이상의 서비스가 1이어도 같은 워커는 한 곳에서만. 만료(기본 120초)되면 다른 곳이 이어받는다.
  (장 단위 중복은 큐의 `FOR UPDATE SKIP LOCKED`가 이미 막는다 — 리스는 **서비스 단위** 중복을 막는다.)
- **기록** `record_run(name, n)`: 서비스별·워커별 마지막 실행·오늘 횟수(`app_state workers:runs`).
  진단 「워커 실행 서비스」 블록이 이걸 그대로 보인다.
- 크론 엔드포인트(/cron/*)는 게이트를 걸지 않는다 — 외부 크론이 부른 서비스에서 **안 돌면 아무도 안 돌기** 때문.
  대신 리스로 서비스 간 동시 실행만 막고 기록을 남긴다.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_RUNS_KEY = "workers:runs"
_LEASE_PREFIX = "worker_lease:"
_MEM: dict = {}
_LOCK = threading.Lock()

# 진단에 보일 워커 목록(이름 → 설명). 실제로 이 레포 서버에서 도는 것만.
WORKERS = {
    "optko-auto": "옵션·상품명 번역 큐(수집 직후 자동)",
    "imgko-auto": "이미지 번역 큐",
    "translate-pilot-tick": "번역 드레인 + 파일럿(/cron/translate-drain)",
    "reject-watch": "쿠팡 반려 감시(/cron/reject-watch)",
    "naver-order-poll": "네이버 주문 폴러(NAVER_ORDER_POLL=1일 때만)",
}


def service_name() -> str:
    return (os.getenv("RENDER_SERVICE_NAME") or "local").strip() or "local"


def _holder() -> str:
    return f"{service_name()}:{os.getpid()}"


def _deployed() -> bool:
    try:
        from src.db.pg import is_deployed
        return bool(is_deployed())
    except Exception:
        return False


def workers_enabled() -> bool:
    """이 서비스가 워커를 띄워도 되나. 배포에선 `WORKERS_ENABLED=1`만, 로컬·테스트는 미설정이면 예전처럼 켬."""
    raw = os.getenv("WORKERS_ENABLED")
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return not _deployed()


def gate_text() -> str:
    raw = os.getenv("WORKERS_ENABLED")
    if raw is not None and raw.strip() != "":
        return f"WORKERS_ENABLED={raw.strip()}"
    return "WORKERS_ENABLED 없음 — " + ("배포라 꺼짐(접수만)" if _deployed() else "로컬이라 켬")


def _pg_on() -> bool:
    try:
        from src.db import pg
        return bool(pg.pg_enabled())
    except Exception:
        return False


def lease(name: str, ttl: int = 120) -> bool:
    """`name` 워커를 지금 이 프로세스가 돌려도 되나 — 비었거나·만료됐거나·이미 내 것이면 잡고 True."""
    until = datetime.now(timezone.utc) + timedelta(seconds=int(ttl))
    me = _holder()
    val = {"holder": me, "service": service_name(), "until": until.isoformat()}
    if not _pg_on():
        with _LOCK:
            cur = _MEM.get(_LEASE_PREFIX + name)
            if cur and cur["holder"] != me and datetime.fromisoformat(cur["until"]) > datetime.now(timezone.utc):
                return False
            _MEM[_LEASE_PREFIX + name] = val
        return True
    try:
        from src.db import pg
        with pg.tx() as cur:
            cur.execute(
                "INSERT INTO app_state (key, value, updated_at) VALUES (%s, %s::jsonb, now()) "
                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now() "
                "WHERE app_state.value->>'holder' = %s OR (app_state.value->>'until')::timestamptz < now() "
                "RETURNING key", (_LEASE_PREFIX + name, json.dumps(val), me))
            return cur.fetchone() is not None
    except Exception as exc:
        logger.warning("[워커] 리스 확인 실패(%s) — 이번엔 돌리지 않음: %s", name, exc)
        return False


def release(name: str) -> None:
    """내가 잡은 리스만 놓는다(만료 시각을 지금으로)."""
    me = _holder()
    now = datetime.now(timezone.utc).isoformat()
    if not _pg_on():
        with _LOCK:
            cur = _MEM.get(_LEASE_PREFIX + name)
            if cur and cur["holder"] == me:
                cur["until"] = now
        return
    try:
        from src.db import pg
        with pg.tx() as cur:
            cur.execute("UPDATE app_state SET value = jsonb_set(value, '{until}', to_jsonb(%s::text)), updated_at=now() "
                        "WHERE key=%s AND value->>'holder' = %s", (now, _LEASE_PREFIX + name, me))
    except Exception as exc:
        logger.debug("[워커] 리스 반납 실패(%s): %s", name, exc)


def _state():
    from src.db import image_translate_queue_pg as st
    return st


def record_run(name: str, n: int = 0, note: str = "") -> None:
    """서비스별 실행 기록 — 마지막 시각·처리 수·오늘 횟수. 실패해도 워커는 계속."""
    try:
        st = _state()
        runs = st.state_get(_RUNS_KEY) or {}
        svc = runs.setdefault(service_name(), {})
        day = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
        w = svc.get(name) or {}
        if w.get("day") != day:
            w = {"day": day, "runs_today": 0, "items_today": 0}
        w.update(last_at=datetime.now(timezone.utc).isoformat(), last_n=int(n), note=note[:160],
                 runs_today=int(w.get("runs_today", 0)) + 1, items_today=int(w.get("items_today", 0)) + int(n))
        svc[name] = w
        st.state_set(_RUNS_KEY, runs)
    except Exception as exc:
        logger.debug("[워커] 실행 기록 실패(%s): %s", name, exc)


def snapshot() -> dict:
    """진단 블록 재료 — 이 서비스의 게이트, 워커별 리스 보유자, 서비스별 실행 기록."""
    out = {"service": service_name(), "enabled": workers_enabled(), "gate": gate_text(), "workers": [], "error": ""}
    try:
        runs = _state().state_get(_RUNS_KEY) or {}
    except Exception as exc:
        runs, out["error"] = {}, f"{type(exc).__name__}: {str(exc)[:160]}"
    leases = {}
    try:
        if _pg_on():
            from src.db import pg
            with pg.query() as cur:
                cur.execute("SELECT key, value FROM app_state WHERE key LIKE %s", (_LEASE_PREFIX + "%",))
                for k, v in cur.fetchall():
                    leases[k[len(_LEASE_PREFIX):]] = v if isinstance(v, dict) else json.loads(v or "{}")
        else:
            leases = {k[len(_LEASE_PREFIX):]: v for k, v in _MEM.items() if k.startswith(_LEASE_PREFIX)}
    except Exception as exc:
        out["error"] += f" 리스: {type(exc).__name__}: {str(exc)[:120]}"
    now = datetime.now(timezone.utc)
    for name, desc in WORKERS.items():
        ls = leases.get(name) or {}
        try:
            live = bool(ls) and datetime.fromisoformat(ls.get("until")) > now
        except Exception:
            live = False
        by_svc = {svc: rec[name] for svc, rec in runs.items() if isinstance(rec, dict) and name in rec}
        out["workers"].append({"name": name, "desc": desc, "lease_service": ls.get("service", "") if live else "",
                               "runs": by_svc})
    return out
