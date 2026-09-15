"""src/services/rate_slot.py — **서버 전역** 호출 차례표 (F25b).

## 프로세스 전역은 서버 전역이 아니다

F25에서 공급사 한도(계정 단위 초당 1회)를 지키려고 직렬 게이트를 걸었다.
그 잠금은 **프로세스 전역**이었다. 그런데 실측:

    scripts/start_render.sh:30   --workers "${GUNICORN_WORKERS:-2}"
    gunicorn.conf.py:5-7         workers 2 · gthread · threads 4

**워커가 둘이다.** 잠금도 둘이고, 각자 「나는 하나씩 보낸다」고 믿으면서 **합쳐서 둘**이 나간다.
한도는 계정 단위라 합쳐서 세므로, 워커가 늘수록 정확히 그만큼 넘긴다.

## 잠금이 아니라 차례표다

행 하나에 「다음으로 비는 시각」만 둔다. 호출자는 **원자적 UPDATE 한 번**으로 자기 차례를
예약받고, **연결을 놓은 뒤** 그 시각까지 기다린다.

잠금을 쥔 채 공급사를 부르지 않는다. 한 장이 최대 30초(내려받기 10 + 호출 20)이고
12장이면 그만큼 DB 연결과 트랜잭션을 붙잡는다 — 트랜잭션 풀러(6543) 뒤에서 그건
idle-in-transaction이고, 이 레포는 이미 그 문제를 아는 코드다(`pg.get_conn`의 rollback 정리).
차례표는 잠금을 **밀리초**만 잡는다.

## 시각은 서버 것을 쓴다

기다릴 시간을 서버가 계산해 돌려준다(`next_at - now()`). 워커마다 시계가 다를 수 있어
클라이언트 시계로 빼면 차례가 겹치거나 쓸데없이 길어진다.

## PG가 없으면

개발·테스트에서는 프로세스 전역 게이트로 폴백한다. 그때는 워커가 하나뿐이라 그걸로 족하다 —
**그리고 그 사실을 `backend`로 말한다.** 「지키고 있다」와 「이 환경에선 그걸로 족하다」는 다른 말이다.
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

# 프로세스 폴백용 — PG가 없을 때만 쓴다.
_LOCAL = threading.Lock()
_LOCAL_NEXT: dict = {}

MAX_WAIT_SEC = float(60)        # 차례가 이보다 멀면 기다리지 않고 알린다(줄이 비정상적으로 길다).


def _pg_ready() -> bool:
    try:
        from src.db import pg
        return bool(pg.pg_enabled())
    except Exception:
        return False


def reset_for_tests() -> None:
    with _LOCAL:
        _LOCAL_NEXT.clear()


def reserve(key: str, interval_sec: float) -> dict:
    """내 차례를 예약하고 `{wait, backend}`를 돌려준다. **기다리지는 않는다.**

    `wait` = 지금부터 몇 초 뒤에 보내면 되는지(0이면 바로).
    `backend` = `"server"`(PG 차례표) 또는 `"process"`(폴백) — 어느 범위로 지켰는지 정직하게.
    """
    k = str(key or "").strip() or "default"
    iv = max(0.0, float(interval_sec))

    if _pg_ready():
        try:
            from src.db import pg
            with pg.tx() as cur:
                # 원자적이다 — 한 행에 대한 UPSERT는 행 잠금 안에서 일어난다.
                #   내 차례 = 갱신 **전**의 next_at(또는 지금, 둘 중 늦은 쪽).
                cur.execute(
                    "INSERT INTO api_rate_slots (key, next_at) "
                    "VALUES (%s, now() + make_interval(secs => %s)) "
                    "ON CONFLICT (key) DO UPDATE SET "
                    "  next_at = GREATEST(api_rate_slots.next_at, now()) "
                    "            + make_interval(secs => %s), "
                    "  updated_at = now() "
                    "RETURNING EXTRACT(EPOCH FROM "
                    "  (next_at - make_interval(secs => %s) - now()))",
                    (k, iv, iv, iv))
                row = cur.fetchone()
            wait = max(0.0, float(row[0])) if row else 0.0
            return {"wait": wait, "backend": "server"}
        except Exception as exc:
            # 차례표가 죽었다고 번역을 막지는 않는다 — 다만 **어느 범위로 지키는지**는 바뀐다.
            logger.warning("[차례표] 서버 예약 실패 — 프로세스 범위로 폴백: %s", exc)

    with _LOCAL:
        now = time.monotonic()
        slot = max(_LOCAL_NEXT.get(k, 0.0), now)
        _LOCAL_NEXT[k] = slot + iv
    return {"wait": max(0.0, slot - now), "backend": "process"}


def wait_turn(key: str, interval_sec: float) -> dict:
    """차례를 예약하고 **그 시각까지 기다린다**. 반환은 `reserve`와 같은 모양 + `waited`.

    줄이 비정상적으로 길면(`MAX_WAIT_SEC` 초과) 기다리지 않고 그대로 돌려준다 —
    한 요청이 1분 넘게 잠들어 있는 것보다, 호출자가 「지금은 줄이 길다」를 아는 편이 낫다.
    """
    out = reserve(key, interval_sec)
    w = float(out.get("wait") or 0.0)
    if w > MAX_WAIT_SEC:
        out["waited"] = 0.0
        out["too_long"] = True
        return out
    if w > 0:
        time.sleep(w)
    out["waited"] = w
    return out
