"""src/seller_console/usage_meter.py — Y15(오너 2026-10-22) 요금제 한도 집행.

한도 숫자의 정본은 `billing_store.PLANS[plan]["limits"]`(None = 무제한). 여기는 **재고 · 막고 · 말하는** 곳이다.

| 종류 | 세는 법 | 풀리는 때 |
|---|---|---|
| collect(수집) | 이번 달(KST) 새로 만든 수집 행 — 지운 행도 센다(PG) | 다음 달 1일 0시(KST) |
| precheck(사전검증) | 누를 때 1회 — `app_state`의 달 카운터(원자적 상한 증가, 워커가 둘이어도 넘지 않음) | 다음 달 1일 0시(KST) |
| translate(번역) | 지금 그대로 `translation_usage`의 누적 무료 횟수(20) — 여기선 면제만 얹는다 | 풀리지 않음(유료면 무제한) |

**재지 않는 사람:** 공유 사용자(관리자 · `FAMILY_EMAILS` — 오너 서버 자격으로 운영하는 사람)와 서버 자신(신원 없음·크론·`default`).
지금 운영 흐름에 영향 0 — 테스트 `test_y15_billing_limits`가 핀으로 잡는다.

가짜 차단·가짜 활성 금지: 판정이 깨지면(시트·DB 실패) **막지 않는다**(로그만) — 한도는 장사를 막는 이유가 될 수 없다.
`USAGE_LIMITS=0`이면 전부 끈다(테스트 스위트 기본 — 다른 테스트가 한 셀러로 30개 넘게 만든다).
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
BILLING_URL = "/seller/billing"
KINDS = ("collect", "translate", "precheck")
_LABEL = {"collect": ("수집", "개"), "translate": ("번역", "회"), "precheck": ("사전검증", "회")}
_PRECHECK_KEY = "usage:precheck:"
_PLAN_TTL = 60.0
_plan_cache: dict = {}                 # sid → (ts, plan) — 수집 한 건마다 시트를 읽지 않게(벌크 1000건)
_PLAN_CACHE_MAX = 500


class UsageLimitReached(Exception):
    """이번 달 한도를 다 썼다 — `message`를 그대로 화면에 보인다."""

    def __init__(self, kind: str, used: int, limit: int, plan: str):
        self.kind, self.used, self.limit, self.plan = kind, int(used), int(limit), plan
        self.message = message(kind, plan, limit)
        super().__init__(self.message)

    def payload(self) -> dict:
        return {"ok": False, "error": self.message, "limit_reached": True, "kind": self.kind,
                "used": self.used, "limit": self.limit, "plan": self.plan, "billing_url": BILLING_URL}


def enabled() -> bool:
    return os.getenv("USAGE_LIMITS", "1").strip().lower() not in ("0", "false", "no", "off")


def month_start_utc(now: Optional[datetime] = None) -> datetime:
    """이번 달 1일 0시(KST)를 UTC로."""
    k = (now or datetime.now(timezone.utc)).astimezone(KST)
    return k.replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def month_key(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(KST).strftime("%Y-%m")


def message(kind: str, plan: str, limit: int) -> str:
    from .billing_store import PLANS
    name, unit = _LABEL.get(kind, (kind, "회"))
    label = PLANS.get(plan, {}).get("label", plan)
    up = "Pro로 올리거나" if plan == "plus" else "Plus로 올리거나"
    if kind == "translate":
        return f"{label} 무료 번역({limit}{unit})을 다 썼어요 — {up.replace('거나', '면')} 무제한이에요"
    return f"이번 달 {label} 한도({name} {limit}{unit})를 다 썼어요 — {up} 다음 달 1일에 풀려요"


def _session_matches(sid: str, email: str):
    """요청 세션이 이 사람이면 세션 판정(관리자 role 포함) 결과, 아니면 None."""
    try:
        from flask import has_request_context, session
        if not has_request_context():
            return None
        mine = {str(session.get(k) or "").strip().lower() for k in ("user_id", "user_email", "email")} - {""}
        if not mine or not ({sid.lower(), str(email or "").strip().lower()} & mine):
            return None
        from .market_pick import session_is_shared
        return bool(session_is_shared())
    except Exception:                                            # noqa: BLE001
        return None


def is_exempt(seller_id, email: str = "") -> bool:
    """한도를 재지 않는 사람인가 — 공유 사용자(관리자·FAMILY_EMAILS) 또는 서버 자신(신원 없음).

    세션 없는 경로(확장 토큰·텔레그램·벌크 잡)도 같은 답이 나와야 한다 — 세션이 이 사람이면 세션 판정,
    아니면 신원(정본 user_id · ADMIN_USER_IDS · 이 사람의 로그인 이메일 전부 vs ADMIN_EMAILS·FAMILY_EMAILS)으로."""
    sid = str(seller_id or "").strip()
    if not sid or sid == "default":
        return True
    by_session = _session_matches(sid, email)
    if by_session is not None:
        return by_session
    try:
        from src.auth.identity import OWNER_USER_ID
        from src.auth.admin_resolver import _env_list, admin_user_ids
        from .market_pick import family_emails
        if sid == OWNER_USER_ID or sid.lower() in admin_user_ids():
            return True
        mails = {str(email or "").strip().lower()} | ({sid.lower()} if "@" in sid else set())
        try:
            from src.db import user_identities_pg
            mails |= {str(m).strip().lower() for m in user_identities_pg.emails_for(sid)}
        except Exception as exc:                                 # noqa: BLE001
            logger.debug("[한도] 이메일 조회 실패(아는 것만으로): %s", exc)
        mails.discard("")
        return bool(mails & (set(_env_list("ADMIN_EMAILS")) | set(family_emails())))
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[한도] 공유 판정 실패 — 재지 않음(막지 않는다): %s", exc)
        return True


def plan_of(seller_id) -> str:
    sid = str(seller_id or "")
    hit = _plan_cache.get(sid)
    if hit and time.time() - hit[0] < _PLAN_TTL:
        return hit[1]
    from . import billing_store
    plan = str((billing_store.get_account(sid) or {}).get("plan") or "free")
    if plan not in billing_store.PLANS:
        plan = "free"
    if len(_plan_cache) >= _PLAN_CACHE_MAX:
        _plan_cache.clear()
    _plan_cache[sid] = (time.time(), plan)
    return plan


def forget_plan(seller_id) -> None:
    """플랜이 바뀌면(결제 승인·무료 전환) 캐시를 버린다 — 올린 직후 바로 풀려야 한다."""
    _plan_cache.pop(str(seller_id or ""), None)


def limit_for(seller_id, kind: str, email: str = "") -> Optional[int]:
    """이 사람의 이 종류 한도. None = 재지 않음(무제한·면제·꺼짐)."""
    if not enabled() or is_exempt(seller_id, email):
        return None
    from .billing_store import PLANS
    v = (PLANS.get(plan_of(seller_id), {}).get("limits") or {}).get(kind)
    return None if v is None else int(v)


def used(seller_id, kind: str, now: Optional[datetime] = None) -> int:
    sid = str(seller_id or "")
    if kind == "collect":
        from . import collect_history_store
        return int(collect_history_store.count_created_since(month_start_utc(now), {sid}))
    if kind == "precheck":
        from src.db import image_translate_queue_pg as st
        return int(st.day_count(_PRECHECK_KEY + f"{sid}:{month_key(now)}"))
    if kind == "translate":
        from . import translation_usage
        return int(translation_usage.get_used(sid))
    return 0


def ensure(kind: str, seller_id, email: str = "") -> None:
    """넘었으면 `UsageLimitReached`. 판정 실패는 막지 않는다."""
    try:
        lim = limit_for(seller_id, kind, email)
        if lim is None:
            return
        n = used(seller_id, kind)
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[한도] %s 사용량 확인 실패 — 막지 않음: %s", kind, exc)
        return
    if n >= lim:
        logger.info("[한도] %s %s %d/%d — 막음", str(seller_id)[:12], kind, n, lim)
        raise UsageLimitReached(kind, n, lim, plan_of(seller_id))


def take_precheck(seller_id, email: str = "") -> None:
    """사전검증 1회를 센다(상한 아래일 때만 올린다 — 원자적). 넘었으면 `UsageLimitReached`."""
    try:
        lim = limit_for(seller_id, "precheck", email)
        if lim is None:
            return
        from src.db import image_translate_queue_pg as st
        took, n = st.take_start(_PRECHECK_KEY + f"{seller_id}:{month_key()}", lim)
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[한도] 사전검증 횟수 확인 실패 — 막지 않음: %s", exc)
        return
    if not took:
        raise UsageLimitReached("precheck", n, lim, plan_of(seller_id))


def translate_unlimited(seller_id, email: str = "") -> bool:
    """번역 무료 횟수를 재지 않는가 — 유료 플랜(지금 규칙) 또는 면제(공유 사용자·서버 자신)."""
    try:
        from . import billing_store
        if billing_store.is_unlimited(seller_id):
            return True
    except Exception:                                            # noqa: BLE001
        pass
    if not enabled():
        return False
    try:
        return is_exempt(seller_id, email)
    except Exception:                                            # noqa: BLE001
        return False


def summary(seller_id, email: str = "") -> dict:
    """요금제 화면용 — `{plan, exempt, rows:[{kind, label, used, limit, unit, monthly}]}`."""
    plan = plan_of(seller_id)
    exempt = is_exempt(seller_id, email)
    from .billing_store import PLANS
    lims = PLANS.get(plan, {}).get("limits") or {}
    rows = []
    for k in KINDS:
        name, unit = _LABEL[k]
        try:
            u = used(seller_id, k)
        except Exception as exc:                                 # noqa: BLE001
            logger.debug("[한도] %s 사용량 못 셈: %s", k, exc)
            u = None
        rows.append({"kind": k, "label": "무료 번역" if k == "translate" else name, "unit": unit, "used": u,
                     "limit": None if exempt else lims.get(k), "monthly": k != "translate"})
    return {"plan": plan, "exempt": exempt, "rows": rows}
