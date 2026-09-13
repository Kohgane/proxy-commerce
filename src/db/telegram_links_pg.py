"""src/db/telegram_links_pg.py — 텔레그램 (봇, chat_id) ↔ 셀러 바인딩 저장소 (C-F17/F18).

PG가 켜져 있으면 `telegram_links` 테이블, 아니면 **인메모리**(개발·테스트, 비영속).
다른 스토어와 같은 패턴 — 프로덕션 부팅 가드는 `order_webhook`이 이미 건다.

**키는 (bot_slug, chat_id)다.** 한 사람이 봇 둘로 콘솔 로그인 둘을 따로 쓴다 —
같은 텔레그램 계정이라 chat_id는 같은데 담길 계정이 다르다. chat_id만으로 키를 잡으면
둘 중 하나가 다른 하나를 덮는다.

**토큰 원문은 여기 오지 않는다.** `/link`는 토큰을 검증하고 **해시만** 남긴다.
해시를 두는 이유는 콘솔에서 그 토큰을 폐기하면 **매핑도 따라 무효**가 되어야 하기 때문이다.
"""
from __future__ import annotations

from src.db import pg

# 인메모리 폴백: {(bot_slug, chat_id): {"user_id": …, "token_hash": …}}
_MEM: dict[tuple, dict] = {}


def _enabled() -> bool:
    try:
        return bool(pg.pg_enabled())
    except Exception:
        return False


def reset_for_tests() -> None:
    _MEM.clear()


def _key(bot_slug, chat_id) -> tuple:
    return (str(bot_slug or "").strip(), str(chat_id or "").strip())


def link(chat_id: str, user_id: str, *, bot_slug: str = "default", token_hash: str = "") -> bool:
    """이 봇의 이 chat을 계정에 묶는다(이미 있으면 갈아끼운다). 실제 커밋됐을 때만 True."""
    slug, cid = _key(bot_slug, chat_id)
    uid = str(user_id or "").strip()
    if not (slug and cid and uid):
        return False
    th = str(token_hash or "")
    if not _enabled():
        _MEM[(slug, cid)] = {"user_id": uid, "token_hash": th}
        return True
    with pg.tx() as cur:
        cur.execute(
            "INSERT INTO telegram_links (bot_slug, chat_id, user_id, token_hash) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (bot_slug, chat_id) WHERE deleted_at IS NULL "
            "DO UPDATE SET user_id = EXCLUDED.user_id, token_hash = EXCLUDED.token_hash, linked_at = now()",
            (slug, cid, uid, th))
    return True


def get(chat_id: str, *, bot_slug: str = "default") -> dict:
    """묶인 계정 `{user_id, token_hash}`. 없으면 빈 dict — 호출부가 **정직 거절**한다."""
    slug, cid = _key(bot_slug, chat_id)
    if not (slug and cid):
        return {}
    if not _enabled():
        return dict(_MEM.get((slug, cid), {}))
    with pg.query() as cur:
        cur.execute("SELECT user_id, token_hash FROM telegram_links "
                    "WHERE bot_slug = %s AND chat_id = %s AND deleted_at IS NULL", (slug, cid))
        row = cur.fetchone()
    return {"user_id": str(row[0]), "token_hash": str(row[1] or "")} if row else {}


def user_id_for(chat_id: str, *, bot_slug: str = "default") -> str:
    """묶인 계정 식별자만. 없으면 빈 문자열(아무 스코프에나 쓰지 않는다)."""
    return get(chat_id, bot_slug=bot_slug).get("user_id", "")


def unlink(chat_id: str, *, bot_slug: str = "default") -> bool:
    """바인딩 해제(소프트삭제). 실제로 지워졌을 때만 True."""
    slug, cid = _key(bot_slug, chat_id)
    if not (slug and cid):
        return False
    if not _enabled():
        return _MEM.pop((slug, cid), None) is not None
    with pg.tx() as cur:
        cur.execute("UPDATE telegram_links SET deleted_at = now() "
                    "WHERE bot_slug = %s AND chat_id = %s AND deleted_at IS NULL", (slug, cid))
        return bool(cur.rowcount)


def touch(chat_id: str, *, bot_slug: str = "default") -> None:
    """마지막 사용 시각 갱신 — 실패해도 수집을 막지 않는다(부가 기록)."""
    slug, cid = _key(bot_slug, chat_id)
    if not (slug and cid and _enabled()):
        return
    try:
        with pg.tx() as cur:
            cur.execute("UPDATE telegram_links SET last_used_at = now() "
                        "WHERE bot_slug = %s AND chat_id = %s AND deleted_at IS NULL", (slug, cid))
    except Exception:
        pass
