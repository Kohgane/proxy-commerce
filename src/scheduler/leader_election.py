from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path


def _read_lock(lock_path: Path) -> dict:
    if not lock_path.exists():
        return {}
    try:
        return json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_lock(lock_path: Path, payload: dict) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = lock_path.with_suffix(f"{lock_path.suffix}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, lock_path)


def acquire_leadership(lock_path: Path, ttl_seconds: int = 90) -> bool:
    """파일 기반 leader-election."""
    now = int(time.time())
    current = _read_lock(lock_path)
    expires_at = int(current.get("expires_at", 0) or 0)
    same_owner = (
        str(current.get("pid")) == str(os.getpid())
        and str(current.get("hostname")) == socket.gethostname()
    )
    if current and expires_at > now and not same_owner:
        return False

    payload = {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "acquired_at": now,
        "heartbeat_at": now,
        "expires_at": now + max(1, int(ttl_seconds)),
    }
    _write_lock(lock_path, payload)
    return True


def renew_leadership(lock_path: Path, ttl_seconds: int = 90):
    """주기적 갱신 (heartbeat)."""
    if not is_leader(lock_path):
        return False
    now = int(time.time())
    payload = _read_lock(lock_path)
    payload["heartbeat_at"] = now
    payload["expires_at"] = now + max(1, int(ttl_seconds))
    _write_lock(lock_path, payload)
    return True


def is_leader(lock_path: Path) -> bool:
    payload = _read_lock(lock_path)
    if not payload:
        return False
    now = int(time.time())
    if int(payload.get("expires_at", 0) or 0) <= now:
        return False
    return (
        str(payload.get("pid")) == str(os.getpid())
        and str(payload.get("hostname")) == socket.gethostname()
    )


def get_leader_info(lock_path: Path) -> dict:
    return _read_lock(lock_path)
