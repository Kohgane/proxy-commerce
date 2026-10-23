"""src/utils/instance.py — 이 프로세스가 어느 인스턴스인가(같은 빌드·같은 DB로 둘이 돌 때 누가 말하는지 보이게).

`id` = `RENDER_INSTANCE_ID`(있으면) 아니면 호스트 이름 · `started_at` = 이 모듈을 처음 읽은 시각(프로세스 기동 근사, UTC)."""
from __future__ import annotations

import os
import socket
from datetime import datetime, timezone

_STARTED = datetime.now(timezone.utc)


def instance_id() -> str:
    iid = (os.getenv("RENDER_INSTANCE_ID") or "").strip()
    if iid:
        return iid
    try:
        return socket.gethostname()
    except Exception:                                            # noqa: BLE001
        return ""


def instance_info() -> dict:
    return {"id": instance_id(), "id_source": "RENDER_INSTANCE_ID" if os.getenv("RENDER_INSTANCE_ID") else "hostname",
            "pid": os.getpid()}


def holder() -> str:
    """이 프로세스 한 개를 가리키는 이름 — `인스턴스:pid`(인스턴스가 둘이면 pid가 같아도 다르다). 잡 기록의 「누가 돌리나」."""
    return f"{instance_id()}:{os.getpid()}"
