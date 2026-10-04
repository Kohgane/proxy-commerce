"""도움말 설정값 — 아이폰 단축어 설치 링크(M3-iOS 보충, 오너 2026-09-28).

오너가 아이폰에서 단축어를 만들고 「iCloud 링크 복사」한 값을 **관리자 화면에서 붙여넣는다**.
저장은 `app_state`(PG, 없으면 메모리) — D3-8·F53과 같은 자리. 환경변수 `IOS_SHORTCUT_URL`은 폴백.
비어 있으면 안내 화면은 버튼 대신 「준비 중」이라고 말한다(없는 링크를 지어내지 않는다).
"""
from __future__ import annotations

import os
import re

_KEY = "help:ios_shortcut_url"
# iCloud 단축어 공유 링크 모양만 받는다(다른 주소를 「단축어 설치」 버튼에 걸면 유저가 엉뚱한 곳으로 간다).
_ICLOUD_RE = re.compile(r"^https://www\.icloud\.com/shortcuts/[0-9A-Za-z]{8,64}/?$")


def _st():
    from src.db import image_translate_queue_pg as st
    return st


def ios_shortcut_url() -> str:
    try:
        v = str((_st().state_get(_KEY) or {}).get("url") or "").strip()
    except Exception:
        v = ""
    return v or os.getenv("IOS_SHORTCUT_URL", "").strip()


def ios_shortcut_link_version() -> int:
    """Z2(오너 2026-10-04): 지금 iCloud 링크에 든 단축어가 **URL에 싣는 v** — 오너가 링크와 함께 적는다. 모르면 0.
    서버는 링크 안의 단축어를 볼 수 없다 → 이 값이 없으면 「구버전 — 다시 설치」를 띄우지 않는다(같은 링크로 무한 루프)."""
    try:
        return int((_st().state_get(_KEY) or {}).get("version") or 0)
    except Exception:
        return 0


def save_ios_shortcut_url(url: str, version=None) -> str:
    """빈 문자열이면 지운다(「준비 중」으로 돌아간다). 모양이 틀리면 ValueError.
    `version` = 그 링크의 단축어가 싣는 v(비우면 「모름」 — 구버전 배너 안 띄움)."""
    u = str(url or "").strip()
    if u and not _ICLOUD_RE.match(u):
        raise ValueError("iCloud 단축어 링크(https://www.icloud.com/shortcuts/…)만 넣을 수 있어요.")
    try:
        ver = int(str(version).strip()) if version not in (None, "") else 0
    except ValueError:
        raise ValueError("단축어 버전은 숫자만(예: 2) — 모르면 비워 두세요.")
    _st().state_set(_KEY, {"url": u, "version": ver if u else 0})
    return u


# T5(오너 2026-09-30-H): 단축어 버전별 도착 수 — 중국 유저가 새 단축어(v=2)로 옮겨 갔는지 화면 C에서 본다.
_VKEY = "help:share_version_counts"
SHORTCUT_VERSION = 2


def bump_share_version(v: int) -> None:
    """`v`별 도착 수 +1(PG면 한 문장으로 올려 워커 둘이 동시에 와도 안 잃는다). 실패는 조용히 — 수집을 막지 않는다."""
    key = f"v{int(v) if int(v) > 0 else 0}"
    try:
        from src.db import pg
        if pg.pg_enabled():
            with pg.tx() as cur:
                # O(2026-10-01) 실측: 형 없는 자리표시자를 `jsonb_build_object`에 넣으면 PG가
                #   `IndeterminateDatatype`로 거부한다 — 그런데 아래 except가 삼켜서 **운영에 한 건도 안 쌓였다**.
                #   자리표시자마다 형을 박는다(`::text`).
                cur.execute(
                    "INSERT INTO app_state (key, value, updated_at) VALUES (%s::text, jsonb_build_object(%s::text, 1), now()) "
                    "ON CONFLICT (key) DO UPDATE SET value = jsonb_set(app_state.value, ARRAY[%s::text], "
                    "to_jsonb(COALESCE((app_state.value->>%s::text)::int, 0) + 1)), updated_at = now()",
                    (_VKEY, key, key, key))
            return
        cur_v = _st().state_get(_VKEY) or {}
        cur_v[key] = int(cur_v.get(key) or 0) + 1
        _st().state_set(_VKEY, cur_v)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("[share] 버전별 도착 수 기록 실패: %s: %s", type(exc).__name__, exc)


def share_version_counts() -> dict:
    try:
        return {k: int(v) for k, v in (_st().state_get(_VKEY) or {}).items()}
    except Exception:
        return {}


# O(오너 2026-10-01): 「공유 내용도 클립보드도 비어 있어요」를 서버가 **무엇을 받았는지**로 가른다.
#   같은 쿼리를 테스트·실 gunicorn에 넣으면 담기는데 실기기에선 비었다 — 운영에 흔적이 없었다(위 카운터 SQL
#   결함). 도착마다 **길이·키·도달 단계만** 남긴다(내용·tk는 안 남김). 최근 20건, 관리자 화면 C에서 본다.
_AKEY = "help:share_arrivals"
_ARRIVALS_MAX = 20


def record_share_arrival(entry: dict) -> None:
    try:
        cur = _st().state_get(_AKEY) or {}
        rows = list(cur.get("rows") or [])
        rows.insert(0, {k: entry.get(k) for k in ("at", "method", "v", "qlen", "text_len", "clip_len", "keys",
                                                  "route", "stage", "reason", "authed", "decodes", "ticket", "u_len")})
        _st().state_set(_AKEY, {"rows": rows[:_ARRIVALS_MAX]})
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("[share] 도착 기록 실패: %s: %s", type(exc).__name__, exc)


def share_arrivals() -> list:
    try:
        return list((_st().state_get(_AKEY) or {}).get("rows") or [])
    except Exception:
        return []
