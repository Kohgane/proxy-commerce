"""src/auth/account_label.py — 계정을 **사람이 읽는 이름**으로 바꾸는 한 곳.

## 왜 생겼나 (실측, 오너 2026-09-13 · PC curl)

`POST /api/v1/collect/one` 응답이 이랬다::

    account : "f275b60d-…"
    message : "… (f275b60d-… 계정에 담았어요)"

UUID는 **사람이 읽을 수 없다.** 이 문장의 목적은 「지금 담긴 곳이 내 계정이 맞나」를
사람이 판단하게 하는 것인데, 판단에 쓸 수 없는 값을 내밀면 문장이 있으나 마나다.
더 나쁜 건 *있는 척* 한다는 것 — 화면은 뭔가 말했고 사람은 아무것도 못 알아들었다.

## 근원 (C-F17-A1)

`user_store._get_worksheet()`가 없는 이름(`_get_credentials_dict`)을 import해 **항상 실패**했다.
그래서 `find_by_id`는 언제나 None이었고, 앞선 판(C-F15)이 심어 둔 폴백
「못 찾으면 user_id를 그대로 쓴다」가 **늘 발동**해 UUID가 그대로 나갔다.

폴백 자체가 틀렸다. 못 찾았으면 **아무 말도 안 하는 게 맞다** — 읽을 수 없는 값을
내미는 것은 정보가 아니라 소음이고, 사람은 그걸 자기 탓으로 돌린다.

> 규칙: **UUID는 절대 label이 되지 않는다.** 못 찾으면 빈 문자열을 돌려주고,
> 호출부는 그 자리를 **비운다**(문장을 통째로 빼지, UUID로 채우지 않는다).

## 왜 여기 한 곳인가

계정 이름을 말하는 자리가 넷이다 — `collect/one` 응답 · 수집 목록 머리줄 ·
이미지 처리 대기 머리줄 · API 토큰 화면. 넷이 제각각 폴백을 갖고 있으면
한 곳을 고쳐도 나머지 셋이 UUID를 계속 뱉는다(C-F15에서 실제로 그랬다 — 세 곳을
고치고 네 번째를 놓쳤다). 그래서 이름 짓기는 **여기서만** 한다.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 저장소 조회는 시트 전수 읽기다(무겁다) — 요청마다 하면 수집이 느려진다.
#   성공은 5분, 실패는 30초만 기억한다(일시적 장애가 스스로 풀리게).
_CACHE: dict[str, tuple[float, dict]] = {}
_TTL_OK_SEC = 300.0
_TTL_MISS_SEC = 30.0

_EMPTY = {"user_id": "", "email": "", "name": "", "label": ""}


def reset_cache() -> None:
    """캐시 비우기 — 계약·테스트가 저장소를 바꿔 끼울 때 쓴다."""
    _CACHE.clear()


def resolve_account(user_id) -> dict:
    """`{user_id, email, name, label}` — `label`은 **사람이 읽는 이름**, 못 찾으면 빈 문자열.

    순서:
      1. 값에 `@`가 있으면 그 자체가 사람이 읽는 이름이다(별칭으로 발급된 토큰) — 조회 없이 통과.
      2. 아니면 사용자 저장소를 한 번 찾는다(TTL 캐시). 이메일 > 이름 순으로 `label`.
      3. 못 찾으면 `label=""` — **user_id를 label로 승격하지 않는다.**
    """
    uid = str(user_id or "").strip()
    if not uid:
        return dict(_EMPTY)

    if "@" in uid:                       # 별칭(이메일)으로 발급된 토큰 — 이미 읽을 수 있다.
        return {"user_id": uid, "email": uid, "name": "", "label": uid}

    hit = _CACHE.get(uid)
    if hit and (time.monotonic() - hit[0]) < (_TTL_OK_SEC if hit[1].get("label") else _TTL_MISS_SEC):
        return dict(hit[1])

    out = {"user_id": uid, "email": "", "name": "", "label": ""}
    try:
        from src.auth.user_store import get_store
        u = get_store().find_by_id(uid)
        if u is not None:
            out["email"] = str(getattr(u, "email", "") or "").strip()
            out["name"] = str(getattr(u, "name", "") or "").strip()
            out["label"] = out["email"] or out["name"]
    except Exception as exc:
        # 조용히 삼키지 않는다 — 이 실패가 곧 「계정을 못 말하는」 이유다.
        logger.warning("계정 이름 조회 실패(user_id 로그 생략): %s", exc)

    if not out["label"]:
        logger.info("계정 이름을 찾지 못해 응답에서 계정 줄을 생략한다(UUID 노출 금지).")
    _CACHE[uid] = (time.monotonic(), dict(out))
    return dict(out)


def account_label(user_id) -> str:
    """사람이 읽는 계정 이름 한 줄. 못 찾으면 빈 문자열(호출부가 그 자리를 비운다)."""
    return resolve_account(user_id).get("label", "")


def same_account(a, b, *, identities: Optional[set] = None) -> bool:
    """두 식별자가 **같은 사람**인가.

    user_id(UUID)와 email은 서로 다른 문자열이지만 같은 사람일 수 있다 — 그래서
    문자열을 직접 비교하면 안 된다. C-F15가 토큰 화면에서 `tok.user_id != session_account`
    (UUID vs 이메일)로 비교해 **모든 토큰에 「다른 계정」 뱃지**를 달았다(가짜 신호).
    """
    ids = {str(i).strip() for i in (identities or set()) if str(i or "").strip()}
    sa, sb = str(a or "").strip(), str(b or "").strip()
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    if ids and sa in ids and sb in ids:
        return True
    ra, rb = resolve_account(sa), resolve_account(sb)
    for key in ("email", "name"):
        if ra.get(key) and ra.get(key) == rb.get(key):
            return True
    return bool(ra.get("label")) and ra.get("label") == rb.get("label")
