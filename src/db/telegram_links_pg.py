"""src/db/telegram_links_pg.py — 텔레그램 chat_id ↔ 셀러 바인딩 저장소 (C-F17-B).

PG가 켜져 있으면 `telegram_links` 테이블, 아니면 **인메모리**(개발·테스트, 비영속).
다른 스토어와 같은 패턴 — 프로덕션 부팅 가드는 `order_webhook`이 이미 건다.

**토큰 원문은 여기 오지 않는다.** `/link`는 토큰을 검증만 하고 버리며,
남는 것은 "이 chat은 이 계정"이라는 사실뿐이다.
"""
from __future__ import annotations

from src.db import pg

# 인메모리 폴백: {chat_id: user_id}
_MEM: dict[str, str] = {}


def _enabled() -> bool:
    try:
        return bool(pg.pg_enabled())
    except Exception:
        return False


def reset_for_tests() -> None:
    _MEM.clear()


def link(chat_id: str, user_id: str) -> bool:
    """chat을 계정에 묶는다(이미 있으면 갈아끼운다). 실제 커밋됐을 때만 True."""
    cid, uid = str(chat_id or "").strip(), str(user_id or "").strip()
    if not cid or not uid:
        return False
    if not _enabled():
        _MEM[cid] = uid
        return True
    with pg.tx() as cur:
        cur.execute(
            "INSERT INTO telegram_links (chat_id, user_id) VALUES (%s, %s) "
            "ON CONFLICT (chat_id) WHERE deleted_at IS NULL "
            "DO UPDATE SET user_id = EXCLUDED.user_id, linked_at = now()",
            (cid, uid))
    return True


def user_id_for(chat_id: str) -> str:
    """묶인 계정. 없으면 빈 문자열 — 호출부가 **정직 거절**한다(아무 스코프에나 쓰지 않는다)."""
    cid = str(chat_id or "").strip()
    if not cid:
        return ""
    if not _enabled():
        return _MEM.get(cid, "")
    with pg.query() as cur:
        cur.execute("SELECT user_id FROM telegram_links WHERE chat_id = %s AND deleted_at IS NULL", (cid,))
        row = cur.fetchone()
    return str(row[0]) if row and row[0] else ""


def unlink(chat_id: str) -> bool:
    """바인딩 해제(소프트삭제). 실제로 지워졌을 때만 True."""
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    if not _enabled():
        return _MEM.pop(cid, None) is not None
    with pg.tx() as cur:
        cur.execute("UPDATE telegram_links SET deleted_at = now() WHERE chat_id = %s AND deleted_at IS NULL", (cid,))
        return bool(cur.rowcount)


def touch(chat_id: str) -> None:
    """마지막 사용 시각 갱신 — 실패해도 수집을 막지 않는다(부가 기록)."""
    cid = str(chat_id or "").strip()
    if not cid or not _enabled():
        return
    try:
        with pg.tx() as cur:
            cur.execute("UPDATE telegram_links SET last_used_at = now() WHERE chat_id = %s AND deleted_at IS NULL", (cid,))
    except Exception:
        pass
