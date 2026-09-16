"""src/db/image_ko_blobs_pg.py — 번역 이미지 바이트 저장소 (D2).

PG가 켜져 있으면 `image_ko_blobs`, 아니면 **인메모리**(개발·테스트).

**로컬 파일은 쓰지 않는다.** D1에서 `data/images_ko/<item>/<idx>.jpg`에 뒀는데,
Render는 배포마다 그 디스크를 버린다 — 볼트 [[Render tmp 휘발]]에 이미 적힌 지뢰를
「CDN 붙기 전 임시」라는 이유로 다시 밟았다. 장당 과금으로 만든 결과물이 배포에 사라지면
그 돈을 다시 쓴다.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MEM: dict = {}


def _enabled() -> bool:
    try:
        from src.db import pg
        return bool(pg.pg_enabled())
    except Exception:
        return False


def reset_for_tests() -> None:
    _MEM.clear()


def put(item_id: str, idx: int, raw: bytes, *, seller_id: str = "",
        kind: str = "gallery", content_type: str = "image/jpeg") -> bool:
    """바이트를 둔다. 같은 자리면 덮어쓴다(다시 번역하면 새것이 맞다)."""
    key = (str(item_id), str(kind), int(idx))
    if not raw:
        return False
    if not _enabled():
        prev = _MEM.get(key) or {}
        _MEM[key] = {"bytes": bytes(raw), "content_type": content_type,
                     "seller_id": str(seller_id or ""),
                     # 바이트가 바뀌면 올려 둔 주소는 더 이상 그 이미지가 아니다 — 비운다.
                     "cdn_url": prev.get("cdn_url", "") if prev.get("bytes") == raw else "",
                     "cdn_error": ""}
        return True
    try:
        from src.db import pg
        with pg.tx() as cur:
            cur.execute(
                "INSERT INTO image_ko_blobs (item_id, idx, seller_id, kind, content_type, bytes) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (item_id, kind, idx) DO UPDATE SET "
                "  bytes = EXCLUDED.bytes, content_type = EXCLUDED.content_type, "
                "  seller_id = EXCLUDED.seller_id, created_at = now(), "
                # 바이트가 바뀌면 올려 둔 주소는 더 이상 그 이미지가 아니다 — 비우고 다시 올린다.
                "  cdn_url = CASE WHEN image_ko_blobs.bytes = EXCLUDED.bytes "
                "                 THEN image_ko_blobs.cdn_url ELSE '' END, "
                "  cdn_error = ''",
                (str(item_id), int(idx), str(seller_id or ""), str(kind),
                 str(content_type), raw))
        return True
    except Exception as exc:
        logger.warning("[번역본 저장] 실패 item=%s idx=%s: %s", item_id, idx, exc)
        return False


def get(item_id: str, idx: int, *, kind: str = "gallery") -> tuple:
    """`(bytes, content_type)`. 없으면 `(b"", "")` — **가짜로 만들어 내지 않는다.**"""
    key = (str(item_id), str(kind), int(idx))
    if not _enabled():
        row = _MEM.get(key)
        return (row["bytes"], row["content_type"]) if row else (b"", "")
    try:
        from src.db import pg
        with pg.query() as cur:
            cur.execute("SELECT bytes, content_type FROM image_ko_blobs "
                        "WHERE item_id = %s AND kind = %s AND idx = %s",
                        (str(item_id), str(kind), int(idx)))
            row = cur.fetchone()
        return (bytes(row[0]), str(row[1])) if row else (b"", "")
    except Exception as exc:
        logger.warning("[번역본 조회] 실패 item=%s idx=%s: %s", item_id, idx, exc)
        return (b"", "")


def pending_cdn(limit: int = 200) -> list:
    """아직 외부 주소가 없는 번역본 — `[{item_id, idx, kind, seller_id}]`.

    등록에 나갈 수 없는 장들이다(우리 서버 주소는 마켓이 못 가져간다).
    """
    if not _enabled():
        return [{"item_id": k[0], "kind": k[1], "idx": k[2],
                 "seller_id": v.get("seller_id", "")}
                for k, v in _MEM.items() if not v.get("cdn_url")][:limit]
    try:
        from src.db import pg
        with pg.query() as cur:
            cur.execute("SELECT item_id, kind, idx, seller_id FROM image_ko_blobs "
                        "WHERE cdn_url = '' ORDER BY created_at LIMIT %s", (int(limit),))
            return [{"item_id": r[0], "kind": r[1], "idx": int(r[2]), "seller_id": r[3]}
                    for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("[번역본 CDN] 대기 조회 실패: %s", exc)
        return []


def set_cdn(item_id: str, idx: int, url: str, *, kind: str = "gallery",
            error: str = "") -> bool:
    """올린 결과를 적는다. 성공이면 `url`, 실패면 `error`(둘 중 하나만 의미가 있다)."""
    key = (str(item_id), str(kind), int(idx))
    if not _enabled():
        row = _MEM.get(key)
        if not row:
            return False
        row["cdn_url"] = str(url or "")
        row["cdn_error"] = str(error or "")
        return True
    try:
        from src.db import pg
        with pg.tx() as cur:
            cur.execute("UPDATE image_ko_blobs SET cdn_url = %s, cdn_error = %s, "
                        "  cdn_at = CASE WHEN %s <> '' THEN now() ELSE cdn_at END "
                        "WHERE item_id = %s AND kind = %s AND idx = %s",
                        (str(url or ""), str(error or "")[:300], str(url or ""),
                         str(item_id), str(kind), int(idx)))
            return bool(cur.rowcount)
    except Exception as exc:
        logger.warning("[번역본 CDN] 기록 실패 item=%s idx=%s: %s", item_id, idx, exc)
        return False


def get_cdn(item_id: str, idx: int, *, kind: str = "gallery") -> str:
    """이미 올려 둔 외부 주소. 없으면 빈 문자열 — **멱등 백필의 근거**다."""
    key = (str(item_id), str(kind), int(idx))
    if not _enabled():
        return str((_MEM.get(key) or {}).get("cdn_url") or "")
    try:
        from src.db import pg
        with pg.query() as cur:
            cur.execute("SELECT cdn_url FROM image_ko_blobs "
                        "WHERE item_id = %s AND kind = %s AND idx = %s",
                        (str(item_id), str(kind), int(idx)))
            row = cur.fetchone()
        return str(row[0] or "") if row else ""
    except Exception as exc:
        logger.warning("[번역본 CDN] 조회 실패: %s", exc)
        return ""


def delete_item(item_id: str) -> int:
    """그 상품의 번역본을 모두 지운다(상품이 지워질 때). 지운 수를 돌려준다."""
    if not _enabled():
        keys = [k for k in _MEM if k[0] == str(item_id)]
        for k in keys:
            _MEM.pop(k, None)
        return len(keys)
    try:
        from src.db import pg
        with pg.tx() as cur:
            cur.execute("DELETE FROM image_ko_blobs WHERE item_id = %s", (str(item_id),))
            return int(cur.rowcount or 0)
    except Exception as exc:
        logger.warning("[번역본 삭제] 실패 item=%s: %s", item_id, exc)
        return 0
