"""src/db/image_ko_blobs_pg.py — 번역 이미지 바이트 저장소 (D2).

PG가 켜져 있으면 `image_ko_blobs`, 아니면 **인메모리**(개발·테스트).

**로컬 파일은 쓰지 않는다.** D1에서 `data/images_ko/<item>/<idx>.jpg`에 뒀는데,
Render는 배포마다 그 디스크를 버린다 — 볼트 [[Render tmp 휘발]]에 이미 적힌 지뢰를
「CDN 붙기 전 임시」라는 이유로 다시 밟았다. 장당 과금으로 만든 결과물이 배포에 사라지면
그 돈을 다시 쓴다.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_MEM: dict = {}

# F30: **마지막 쓰기 오류를 기억한다.** 실측(2026-09-16)에서 번역은 「완료 5」인데 장마다
#   「저장된 번역본이 없습니다」였고, 왜 그런지는 **아무 데도 없었다**(로그조차 워커 안에서 끝났다).
#   값은 담지 않는다 — 언제·무슨 작업·무슨 오류인지만.
_LAST_ERROR: dict = {}


def _enabled() -> bool:
    try:
        from src.db import pg
        return bool(pg.pg_enabled())
    except Exception:
        return False


def _configured() -> bool:
    """`DATABASE_URL`이 **적혀 있는가.** 「붙었는가」와 다른 질문이다.

    F30 지뢰의 핵심: `pg_enabled()`는 **첫 접속 실패를 워커 수명 내내 캐시**한다.
    한 번 못 붙으면 그 워커의 모든 쓰기가 조용히 메모리로 가고, **다른 워커가 읽으면 없다.**
    그래서 「설정은 되어 있는데 못 붙었다」를 **개발 모드로 착각하지 않는다.**
    """
    try:
        from src.db import pg
        return bool(pg.db_url())
    except Exception:
        return False


def _scrub(text: str) -> str:
    """오류 문장에서 **인프라 흔적**(주소·아이피·포트)을 지운다 — 사유만 남긴다.

    진단 화면은 오너가 보지만, 그 화면도 접속 지도가 되어선 안 된다.
    """
    out = str(text or "")
    out = re.sub(r"\b[a-z][a-z0-9+.-]*://\S+", "[주소]", out)
    out = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "[아이피]", out)
    out = re.sub(r'"[A-Za-z0-9.-]+\.[A-Za-z]{2,}"', '"[호스트]"', out)
    out = re.sub(r"\bport\s+\d+\b", "port [포트]", out, flags=re.I)
    return out


def _note_error(op: str, detail: str) -> None:
    _LAST_ERROR.clear()
    _LAST_ERROR.update({"op": str(op), "detail": _scrub(detail)[:400],
                        "at": __import__("datetime").datetime.now(
                            __import__("datetime").timezone.utc).isoformat(timespec="seconds")})


def last_error() -> dict:
    """마지막 쓰기 오류 — 진단 화면이 **원문 그대로** 보여 준다(오너가 로그를 뒤지지 않게)."""
    return dict(_LAST_ERROR)


def reset_for_tests() -> None:
    _MEM.clear()
    _LAST_ERROR.clear()


def put(item_id: str, idx: int, raw: bytes, *, seller_id: str = "",
        kind: str = "gallery", content_type: str = "image/jpeg") -> bool:
    """바이트를 둔다. 같은 자리면 덮어쓴다(다시 번역하면 새것이 맞다)."""
    key = (str(item_id), str(kind), int(idx))
    if not raw:
        return False
    if not _enabled():
        if _configured():
            # **설정은 되어 있는데 못 붙었다 = 실패다.** 메모리에 두고 「저장했다」고 하면
            #   같은 워커에선 보이고 다른 워커에선 404다 — 번역은 「완료」인데 이미지는 없다.
            #   장당 과금으로 만든 것을 그렇게 잃었다(오너 실측 5장).
            _note_error("put", "DB에 연결하지 못했습니다(DATABASE_URL은 설정됨)")
            logger.error("[번역본 저장] DB 미연결 — 메모리 폴백 금지(item=%s idx=%s)", item_id, idx)
            return False
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
        # 사유를 **원문 그대로** 남긴다 — 「저장 실패」만으로는 크기인지 권한인지 타임아웃인지
        #   테이블이 없는 것인지 가릴 수 없다(그걸 가리려고 오너가 로그를 회수해 왔다).
        _note_error("put", f"{type(exc).__name__}: {exc}")
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


def status_for_item(item_id: str):
    """그 상품의 번역본 현황 — `{(kind, idx): {bytes, cdn_url, cdn_error, cdn_at}}`.

    **못 읽었으면 `None`.** 「행이 하나도 없다」와 「물어보지 못했다」는 다른 말이다 —
    같은 값(`{}`)으로 돌려주면 호출부가 「번역본이 사라졌다」와 「DB가 대답을 안 한다」를
    구분할 수 없고, 멀쩡한 번역본을 사라진 것으로 지운다.

    **한 번에 읽는다.** 장마다 묻는 것은 서랍 한 번 여는 데 쿼리 N개다(N+1).
    `bytes`는 **길이만** 낸다 — 화면은 「있나 없나」만 알면 되고, 바이트를 끌고 오면 행이 붓는다.
    """
    if not _enabled():
        return {(k[1], k[2]): {"bytes": len(v.get("bytes") or b""),
                               "cdn_url": v.get("cdn_url", ""),
                               "cdn_error": v.get("cdn_error", ""), "cdn_at": ""}
                for k, v in _MEM.items() if k[0] == str(item_id)}
    try:
        from src.db import pg
        with pg.query() as cur:
            cur.execute("SELECT kind, idx, length(bytes), cdn_url, cdn_error, cdn_at "
                        "FROM image_ko_blobs WHERE item_id = %s", (str(item_id),))
            return {(str(r[0]), int(r[1])): {
                "bytes": int(r[2] or 0), "cdn_url": str(r[3] or ""),
                "cdn_error": str(r[4] or ""),
                "cdn_at": r[5].isoformat() if r[5] else ""} for r in cur.fetchall()}
    except Exception as exc:
        logger.warning("[번역본 현황] 조회 실패 item=%s: %s", item_id, exc)
        return None            # 모름 — 호출부가 「없음」으로 읽지 않게


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


def probe() -> dict:
    """저장소가 **지금** 어떤 상태인지 — 진단 화면이 그대로 보여 준다 (F30-2).

    실측(2026-09-16): 번역은 「완료 5」인데 장마다 「저장된 번역본이 없습니다」였고,
    이유는 워커 안에서 끝났다. 「오너 캡처 1장이 답」이 되려면 **화면이 이만큼은 말해야** 한다.

    돌려주는 것(값은 없다 — 상태만):
      `configured`  DATABASE_URL이 적혀 있나
      `connected`   지금 붙는가(캐시된 판정이 아니라 **새로 물어본다**)
      `table`       `image_ko_blobs`가 실제로 있나(stage12 적용 여부)
      `rows`        그 표의 행 수(못 세면 -1)
      `last_error`  마지막 쓰기 오류 원문
    """
    out = {"configured": _configured(), "connected": False, "table": False,
           "rows": -1, "last_error": last_error(), "reason": ""}
    if not out["configured"]:
        out["reason"] = "DATABASE_URL이 설정되지 않았습니다(개발 모드 — 메모리에 둡니다)"
        return out
    try:
        from src.db import pg
        with pg.query() as cur:
            cur.execute("SELECT 1")
            out["connected"] = True
            # 표가 없으면(stage12 미적용) 쓰기는 매번 실패한다 — 그걸 「저장 실패」로만
            #   말하면 무엇을 해야 하는지 알 수 없다.
            cur.execute("SELECT to_regclass('public.image_ko_blobs') IS NOT NULL")
            out["table"] = bool((cur.fetchone() or [False])[0])
            if out["table"]:
                cur.execute("SELECT count(*) FROM image_ko_blobs")
                out["rows"] = int((cur.fetchone() or [0])[0])
    except Exception as exc:
        out["reason"] = _scrub(f"{type(exc).__name__}: {exc}")[:400]
    if out["connected"] and not out["table"]:
        out["reason"] = "image_ko_blobs 표가 없습니다 — 스키마(stage12)가 적용되지 않았습니다"
    return out
