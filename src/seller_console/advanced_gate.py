"""순찰 122b(오너 2026-10-26 18:29) — 「고급 기능」 메뉴 게이트.

오너: "데스크탑에서도 고급기능 그거 너무 난잡하고 비개발자들 입장에선 뭔소린지 싶어 그러니 그건 한정된 기능으로
숨겨라. 원하는? 혹은 결제한 사람들한테만 개방하는걸로 하고 관리자는 그냥 보이게하고."

보이는 조건(OR) — 한 곳에서만 판정한다:
  ① 관리자(`is_admin`)  ② 유료 플랜(plus·pro)  ③ 본인이 설정에서 「고급 기능 켜기」를 켰다(서버 저장, 되돌릴 수 있음).
숨겨도 라우트는 살아 있다 — 북마크로 들어오면 화면 위에 안내 한 줄만(차단 아님).
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

PAID_PLANS = ("plus", "pro")
PREF_KEY = "user_prefs:{sid}"

#: 설정 카드에 보여 줄 「고급 기능에 뭐가 있나」 — 사람 말 5줄(개발 표기 0)
ADVANCED_SUMMARY = (
    "상품명 금지어 자동 치환·단어 바꾸기",
    "가격 자동 규칙·환율 반영",
    "소싱처 가격·품절 변동 알림",
    "통관고유부호(PCCC) 조회·장부·정산",
    "AI 상품등록·키워드 트렌드·관심목록",
)


def _state_key(sid: str) -> str:
    return PREF_KEY.format(sid=str(sid or "").strip() or "-")


def pref_on(sid: str) -> bool:
    """본인이 「고급 기능 켜기」를 켰나(서버 저장 — PG 없으면 인메모리)."""
    if not sid:
        return False
    try:
        from src.db import image_translate_queue_pg as st
        return bool((st.state_get(_state_key(sid)) or {}).get("advanced_on"))
    except Exception as exc:                                       # noqa: BLE001 — 설정을 못 읽으면 기본(숨김)
        logger.warning("[고급 기능] 설정 읽기 실패 sid=%s: %s", str(sid)[:8], exc)
        return False


def set_pref(sid: str, on: bool) -> bool:
    if not sid:
        return False
    try:
        from src.db import image_translate_queue_pg as st
        cur = dict(st.state_get(_state_key(sid)) or {})
        cur["advanced_on"] = bool(on)
        st.state_set(_state_key(sid), cur)
        return True
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("[고급 기능] 설정 저장 실패 sid=%s: %s", str(sid)[:8], exc)
        return False


def is_paid(plan: Optional[str]) -> bool:
    return str(plan or "").strip().lower() in PAID_PLANS


def advanced_visible(*, is_admin: bool, plan: Optional[str], sid: str = "", pref: Optional[bool] = None) -> bool:
    """고급 메뉴를 그릴까. `pref`를 주면 저장소를 읽지 않는다(테스트·템플릿 재사용)."""
    if is_admin:
        return True
    if is_paid(plan):
        return True
    if pref is None:
        pref = pref_on(sid)
    return bool(pref)


def visibility_reason(*, is_admin: bool, plan: Optional[str], pref: bool) -> str:
    """설정 카드에 쓰는 한 줄 — 왜 보이는지/안 보이는지."""
    if is_admin:
        return "관리자 계정이라 항상 보여요"
    if is_paid(plan):
        return "Plus·Pro 플랜은 고급 기능이 모두 열려 있어요"
    if pref:
        return "직접 켜 두셨어요 — 언제든 끌 수 있어요"
    return "지금은 숨겨져 있어요 — 켜면 왼쪽 메뉴에 「고급 기능」이 나타나요"


#: 사이드바 「고급 기능」 접이식에 들어 있는 길(_base.html과 같은 목록) — 숨겨진 사람이 북마크로 들어오면 안내 한 줄.
#: 누구나 쓰는 네 길(연동·요금제·설정·알림)·소개·핵심 메뉴(AI 소싱 허브 /seller/sourcing 자체)는 **고급이 아니다**.
ADVANCED_PREFIXES = (
    "/seller/ads/", "/seller/analytics", "/seller/api/", "/seller/catalog", "/seller/collect/link-diag",
    "/seller/cs/", "/seller/customs/", "/seller/discovery", "/seller/guide/sources", "/seller/inventory/",
    "/seller/keywords", "/seller/listing/", "/seller/margin", "/seller/marketing/", "/seller/markets/guide",
    "/seller/me/subscriptions", "/seller/media/", "/seller/orders/auto", "/seller/pricing/", "/seller/settlement",
    "/seller/sourcing/", "/seller/subscriptions", "/seller/wholesale/",
)
BASIC_PATHS = ("/seller/markets/connect", "/seller/billing", "/seller/me", "/seller/me/notifications",
               "/seller/notifications", "/seller/about", "/seller/bookmarklet")


def is_advanced_path(path: str) -> bool:
    p = str(path or "")
    if p in BASIC_PATHS:
        return False
    return any(p.startswith(x) if x.endswith("/") else (p == x or p.startswith(x + "/") or p.startswith(x + "?")) for x in ADVANCED_PREFIXES)
