"""src/db/settings_pg.py — 가격 정책 저장소 (v87-S3).

PG가 설정돼 있으면 settings/settings_history 테이블에, 아니면 **인메모리**(개발·테스트)로 동작한다.
다른 스토어(collect_history_store 등)와 같은 패턴 — 프로덕션 부팅 가드는 order_webhook이 이미 건다.

낙관잠금: 저장 요청은 `base_version`(불러올 때 받은 값)을 들고 온다. 그 사이 다른 탭·기기에서 저장돼
version이 올라갔으면 **덮어쓰지 않고 충돌로 돌려준다**(조용한 유실 금지 — 정책은 돈이 걸린 값이다).
"""
from __future__ import annotations

import copy
import json
from typing import Any

from src.db import pg

# 인메모리 폴백: {user_id: {"policy": {...}, "version": n}} / {user_id: [history…]}
_MEM: dict[str, dict] = {}
_MEM_HIST: dict[str, list] = {}

HISTORY_LIMIT = 5


class ConflictError(Exception):
    """다른 곳에서 먼저 저장돼 base_version이 낡았다."""

    def __init__(self, current_version: int):
        super().__init__("정책이 다른 곳에서 먼저 저장되었습니다.")
        self.current_version = current_version


def _enabled() -> bool:
    try:
        return bool(pg.pg_enabled())
    except Exception:
        return False


def get_policy(user_id: str) -> dict:
    """저장된 정책과 version. 없으면 {"policy": {}, "version": 0} — 디폴트 적용은 호출부(policy.merge_policy)."""
    uid = (user_id or "").strip()
    if not uid:
        return {"policy": {}, "version": 0}
    if _enabled():
        with pg.tx() as cur:
            cur.execute("SELECT policy, version FROM settings WHERE user_id = %s", (uid,))
            row = cur.fetchone()
        if not row:
            return {"policy": {}, "version": 0}
        pol = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        return {"policy": pol, "version": int(row[1] or 0)}
    got = _MEM.get(uid)
    if not got:
        return {"policy": {}, "version": 0}
    return {"policy": copy.deepcopy(got["policy"]), "version": int(got["version"])}


def _same_policy(a: dict, b: dict) -> bool:
    """두 정책이 같은 내용인가(키 순서 무관).

    v87-S3 후속: 같은 저장이 두 번 도착하면(더블 클릭·폼 재전송) 두 번째는 base_version이 낡아
    낙관잠금에 걸린다. 그런데 **저장된 값이 지금 보내는 값과 같다면 덮어쓸 남의 변경이 없다** —
    이건 충돌이 아니라 중복이다. 충돌 배너는 '남이 바꾼 걸 네가 밀어낼 뻔했다'일 때만 떠야 한다.
    (오너 실배포 캡처: 첫 저장에서 '현재 버전 1' 배너 + 이력엔 v1 정상 — 두 번째 도착이 만든 오탐.)
    """
    return json.dumps(a or {}, sort_keys=True, ensure_ascii=False) ==         json.dumps(b or {}, sort_keys=True, ensure_ascii=False)


def save_policy(user_id: str, policy: dict, base_version: int, summary: str = "") -> dict:
    """정책 저장(낙관잠금). 성공 시 새 version 반환, 충돌이면 ConflictError."""
    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("user_id가 필요합니다.")
    base = int(base_version or 0)
    pol = copy.deepcopy(policy or {})

    if _enabled():
        with pg.tx() as cur:
            cur.execute("SELECT version, policy FROM settings WHERE user_id = %s FOR UPDATE", (uid,))
            row = cur.fetchone()
            cur_ver = int(row[0]) if row else 0
            if cur_ver != base:
                stored = {}
                if row:
                    stored = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
                if _same_policy(stored, pol):
                    return {"ok": True, "version": cur_ver, "duplicate": True}
                raise ConflictError(cur_ver)
            new_ver = cur_ver + 1
            if row:
                cur.execute("UPDATE settings SET policy = %s, version = %s WHERE user_id = %s",
                            (json.dumps(pol), new_ver, uid))
            else:
                cur.execute("INSERT INTO settings (user_id, policy, version) VALUES (%s, %s, %s)",
                            (uid, json.dumps(pol), new_ver))
            cur.execute(
                "INSERT INTO settings_history (user_id, policy, version, summary) VALUES (%s, %s, %s, %s)",
                (uid, json.dumps(pol), new_ver, (summary or "")[:300]))
        return {"ok": True, "version": new_ver}

    got = _MEM.get(uid)
    cur_ver = int(got["version"]) if got else 0
    if cur_ver != base:
        if _same_policy((got or {}).get("policy") or {}, pol):
            return {"ok": True, "version": cur_ver, "duplicate": True}
        raise ConflictError(cur_ver)
    new_ver = cur_ver + 1
    _MEM[uid] = {"policy": pol, "version": new_ver}
    _MEM_HIST.setdefault(uid, []).insert(
        0, {"version": new_ver, "summary": (summary or "")[:300], "policy": copy.deepcopy(pol)})
    del _MEM_HIST[uid][HISTORY_LIMIT * 4:]   # 인메모리는 넉넉히만 보관(조회 시 5건으로 자름)
    return {"ok": True, "version": new_ver}


def list_history(user_id: str, limit: int = HISTORY_LIMIT) -> list[dict]:
    """변경 이력 최근 N건(기본 5)."""
    uid = (user_id or "").strip()
    n = max(1, int(limit or HISTORY_LIMIT))
    if not uid:
        return []
    if _enabled():
        with pg.tx() as cur:
            cur.execute(
                "SELECT version, summary, created_at FROM settings_history "
                "WHERE user_id = %s ORDER BY created_at DESC LIMIT %s", (uid, n))
            rows = cur.fetchall() or []
        return [{"version": int(r[0] or 0), "summary": r[1] or "",
                 "at": r[2].isoformat() if r[2] else ""} for r in rows]
    return [{"version": h["version"], "summary": h["summary"], "at": ""}
            for h in (_MEM_HIST.get(uid) or [])[:n]]


def diff_summary(before: dict, after: dict) -> str:
    """바뀐 항목을 사람이 읽는 한 줄로. 이력에서 '뭐가 바뀌었나'를 바로 알아보게."""
    changed: list[str] = []

    def walk(a: Any, b: Any, path: str = "") -> None:
        if isinstance(a, dict) or isinstance(b, dict):
            a = a if isinstance(a, dict) else {}
            b = b if isinstance(b, dict) else {}
            for k in sorted(set(a) | set(b)):
                walk(a.get(k), b.get(k), f"{path}.{k}" if path else str(k))
            return
        if a != b:
            changed.append(f"{path}: {a} → {b}")

    walk(before or {}, after or {})
    if not changed:
        return "변경 없음"
    head = ", ".join(changed[:3])
    return head if len(changed) <= 3 else f"{head} 외 {len(changed) - 3}건"


def _reset_for_tests() -> None:
    _MEM.clear()
    _MEM_HIST.clear()
