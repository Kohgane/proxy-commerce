"""Z5 후속(오너 2026-10-06) — 검수 카드(M5)·데스크톱 검수 화면의 마켓 체크 기본값.

결정 변경: 가족 유저도 연결된 모든 마켓에 등록할 수 있다 — 묶음 강제 없음, 체크박스는 전부 토글(disabled 0).

기본 체크 = ① 마지막 등록 때 고른 마켓(그 화면에 있는 것만) → ② 계정 설정 「기본 등록 마켓」(`/seller/settings`)
            → ③ 우주대행 묶음(쿠팡 우주대행 + 스마트스토어 고코스모스 — 키·승인이 있는 줄만).
설정을 저장하면 ①을 지운다(오너가 방금 정한 값이 다음 카드에 바로 보이게).

범위: **계정 단위** — 오너 서버의 공유 마켓(관리자 + `FAMILY_EMAILS`)은 한 벌(`shared`), 자기 키를 넣은 다른 셀러는
셀러별. Stage 6(사용자별) 전까지 가족 각자의 기억은 나누지 않는다.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Iterable, List, Optional

ENV_FAMILY = "FAMILY_EMAILS"
ENV_BUSINESS = "MARKET_DEFAULT_BUSINESS"          # Z5 그대로(gogane|woojoo) — 설정·기억이 없을 때의 묶음
BUNDLE = {"woojoo": ("coupang:woojoo", "smartstore:gocosmos"),
          "gogane": ("coupang:gogane", "smartstore:chezgoga")}
_DEFAULT = "market_pick:default:"
_LAST = "market_pick:last:"


def _store():
    from src.db import image_translate_queue_pg as st
    return st


def family_emails() -> List[str]:
    return [e.strip().lower() for e in os.getenv(ENV_FAMILY, "").split(",") if e.strip()]


def is_shared(session_email: str, admin: bool) -> bool:
    """오너 서버의 공유 마켓(쿠팡 두 계정·스마트스토어 두 스토어)을 쓰는 사람인가 — 관리자 또는 `FAMILY_EMAILS`."""
    return bool(admin) or (str(session_email or "").strip().lower() in family_emails() if session_email else False)


def session_email() -> str:
    """로그인 세션의 이메일. 로그인 코드가 넣는 키는 `user_email`이다(`email`은 옛 테스트 픽스처 호환).
    Z6: #839는 `email`만 읽어 운영의 가족 계정이 공유로 판정되지 않았다."""
    try:
        from flask import has_request_context, session
        if not has_request_context():
            return ""
        return str(session.get("user_email") or session.get("email") or "")
    except Exception:
        return ""


def session_identity() -> str:
    """로그인 세션의 정본 신원 — user_id, 없으면 로그인 이메일. 요청 밖·비로그인은 ""."""
    try:
        from flask import has_request_context, session
        if not has_request_context():
            return ""
        return str(session.get("user_id") or session.get("user_email") or session.get("email") or "").strip()
    except Exception:
        return ""


def owner_contact_hint() -> str:
    """순찰 57·95: 막힌 화면(403 · 사전검증 「키를 넣어 주세요」)에 한 줄 — 공유 판정은 **로그인 계정 번호** 기준이라, 가족·관리자가
    목록에 없는 로그인으로 들어왔을 때 무엇을 오너에게 주면 되는지. 계정 번호는 앞 8자리만(본인 화면에만) · 설정 이름·값은 안 보인다."""
    ident = session_identity()
    if not ident or "@" in ident:
        return ""
    return (f"이 화면은 로그인 계정 번호로 판정해요. 가족·관리자인데 이게 보이면 이 계정 번호(앞 8자리 {ident[:8]})를 "
            "오너에게 알려 주세요 — 공유 목록에 넣으면 바로 열려요.")


def session_is_shared(admin: Optional[bool] = None) -> bool:
    """지금 요청의 사람이 공유 마켓(= 오너 서버 자격) 사용자인가.

    순찰 57(오너 2026-10-23 「Z9 오너 풀 공유 판정 user_id 통일」): 마켓 키 격리(P0-2)와 **같은 정체성 규칙** —
    `market_credentials.seller_shared_reason(user_id)`(정본 오너 · `ADMIN_USER_IDS` · `FAMILY_EMAILS` 로그인 이메일).
    세션 role·`ADMIN_EMAILS`만으로는 공유가 아니다(예전엔 세었다 — 화면은 보이는데 마켓 키는 안 쓰이는 어긋남).
    `admin` 인자는 예전 호출 호환으로만 받고 판정에 쓰지 않는다. 비로그인·요청 밖은 아니오."""
    ident = session_identity()
    if not ident:
        return False
    try:
        from .market_credentials import seller_shared_reason
        return seller_shared_reason(ident) not in ("", "server")
    except Exception:
        return False                                             # 판정이 깨지면 닫는다


def scope(seller_id: str, shared: bool) -> str:
    return "shared" if shared else f"seller:{seller_id or 'default'}"


def _clean(codes: Iterable) -> List[str]:
    out = []
    for c in codes or []:
        c = str(c or "").strip()[:60]
        if c and c not in out:
            out.append(c)
    return out[:20]


def get_default(sc: str) -> List[str]:
    return _clean((_store().state_get(_DEFAULT + sc) or {}).get("codes"))


def save_default(sc: str, codes: Iterable, by: str = "") -> List[str]:
    codes = _clean(codes)
    _store().state_set(_DEFAULT + sc, {"codes": codes, "by": str(by or "")[:120],
                                        "at": datetime.now(timezone.utc).isoformat()})
    _store().state_set(_LAST + sc, {})                 # 방금 정한 기본값이 다음 카드에 보이게
    return codes


def get_last(sc: str) -> List[str]:
    return _clean((_store().state_get(_LAST + sc) or {}).get("codes"))


def save_last(sc: str, codes: Iterable) -> List[str]:
    codes = _clean(codes)
    if codes:
        _store().state_set(_LAST + sc, {"codes": codes, "at": datetime.now(timezone.utc).isoformat()})
    return codes


def _bundle_codes() -> tuple:
    biz = (os.getenv(ENV_BUSINESS, "woojoo") or "woojoo").strip().lower()
    return BUNDLE.get(biz, BUNDLE["woojoo"])


ENV_FAMILY_BUNDLE = "FAMILY_MARKET_BUNDLE"
BUNDLE_LABEL = {"woojoo": "쿠팡 우주대행 · 스마트스토어 고코스모스", "gogane": "쿠팡 고가네 · 스마트스토어 셰고가"}


def family_bundle_label(codes: tuple) -> str:
    return next((BUNDLE_LABEL[b] for b, c in BUNDLE.items() if tuple(c) == tuple(codes)), " · ".join(codes))


def family_bundle(ident: Optional[str] = None) -> tuple:
    """순찰 95(오너 2026-10-25): `FAMILY_MARKET_BUNDLE`(gogane|woojoo)이 있으면 **가족**(`FAMILY_EMAILS` 판정) 사용자의 마켓을
    그 묶음으로 고정한다 — 화면엔 그 묶음 줄만, 서버는 묶음 밖 마켓 요청을 거부. 비어 있으면 () = 지금 그대로.
    오너·`ADMIN_USER_IDS`는 고정하지 않는다(가족만). 판정이 깨지면 () — 고정하지 않는 쪽(줄은 지금처럼 다 보인다)."""
    biz = (os.getenv(ENV_FAMILY_BUNDLE, "") or "").strip().lower()
    if biz not in BUNDLE:
        return ()
    ident = session_identity() if ident is None else str(ident or "").strip()
    if not ident:
        return ()
    try:
        from .market_credentials import seller_shared_reason
        return BUNDLE[biz] if seller_shared_reason(ident) == "FAMILY_EMAILS" else ()
    except Exception:                                            # noqa: BLE001
        return ()


def no_auto_codes() -> tuple:
    """Y7-O 5(오너 2026-10-12): 공유 마켓에서 **저절로 체크하지 않는** 마켓 — `MARKET_NO_AUTO_CHECK`(기본 `woocommerce`).
    코가네멀티샵(WC)은 Bluehost 쪽 ReadTimeout(5,386ms)으로 매번 「검증 못 함」이었다 — 줄은 그대로 두고(손으로 고를 수 있다)
    지난 등록·설정·묶음 어느 쪽에서도 기본 체크만 하지 않는다."""
    raw = os.getenv("MARKET_NO_AUTO_CHECK", "woocommerce")
    return tuple(c.strip() for c in raw.split(",") if c.strip())


def apply_checks(markets: list, sc: str, shared: bool = True) -> dict:
    """`markets`(화면 줄) 각 줄의 `checked`를 정하고 `{source, codes}`를 돌려준다. 줄은 지우지도 막지도 않는다.
    공유 마켓이 아닌 셀러(자기 키)의 묶음 기본은 예전 그대로 「쿠팡」 한 줄."""
    codes = [m.get("code") for m in markets]
    fb = family_bundle() if shared else ()
    if fb:                                                       # 순찰 95: 가족 고정 묶음 — 지난 등록·설정보다 앞선다
        hit = []
        for m in markets:
            m["checked"] = bool(m.get("code") in fb and m.get("connected") and not m.get("pending"))
            if m["checked"]:
                hit.append(m["code"])
        return {"source": "family_bundle", "codes": hit}
    skip = no_auto_codes() if shared else ()
    for source, pick in (("last", get_last(sc)), ("setting", get_default(sc))):
        hit = [c for c in pick if c in codes and c not in skip]
        if hit:
            for m in markets:
                m["checked"] = m.get("code") in hit
            return {"source": source, "codes": hit}
    bundle = _bundle_codes() if shared else ("coupang",)
    hit = []
    for m in markets:
        # 묶음 기본은 키가 있고(쿠팡) 승인된(스마트스토어) 줄만 — 안 되는 줄을 미리 켜 두지 않는다(손으로는 켤 수 있다)
        m["checked"] = bool(m.get("code") in bundle and m.get("code") not in skip
                            and (not shared or (m.get("connected") and not m.get("pending"))))
        if m["checked"]:
            hit.append(m["code"])
    return {"source": "bundle", "codes": hit}


def source_label(src: Optional[str]) -> str:
    return {"last": "지난번 등록에서 고른 마켓", "setting": "설정의 기본 등록 마켓",
            "bundle": "우주대행 묶음(설정 없음)",
            "family_bundle": "가족 계정 — 이 묶음으로만 등록해요"}.get(src or "", "")
