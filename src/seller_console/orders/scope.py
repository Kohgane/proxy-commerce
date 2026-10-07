"""src/seller_console/orders/scope.py — Z7(2026-10-07): 주문 행은 **누구의 것인가**.

`orders` 행은 대부분 오너 서버의 마켓 자격(전역 환경변수)으로 동기화된 **오너 마켓 주문**이고,
`user_id`가 비어 있다(= 오너 풀). L1(#837) 이후 누구나 가입하므로 이 풀을 아무에게나 보여 주면
오너의 주문·구매자(마스킹)·매출이 새고, 운송장·상태 변경이 **오너 마켓 계정으로** 나간다.

| 보는 사람 | 보이는 행 |
|---|---|
| 공유 사용자(관리자 · `FAMILY_EMAILS`) | 오너 풀(`user_id` 빈 행) + 자기 행 |
| 그 밖의 로그인 사용자 | 자기 `user_id`(또는 이메일)가 실린 행만 |
| 로그인 신원 없음(크론·부팅·인증 꺼진 개발) | 전부 — 오너 서버 자신이다(Z6 `env_fallback_allowed`와 같은 판정) |

다른 가입자의 행은 공유 사용자에게도 안 보인다 — 그 행은 그 셀러의 것이다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import FrozenSet, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrderViewer:
    shared: bool
    ids: FrozenSet[str] = field(default_factory=frozenset)

    def can_see(self, row_user_id) -> bool:
        uid = str(row_user_id or "").strip()
        if not uid:
            return self.shared
        return uid.casefold() in self.ids


def _session_shared(sess) -> bool:
    """공유 사용자 판정 — Z6의 `market_pick.session_is_shared`가 있으면 그것, 없으면 같은 규칙으로."""
    from src.seller_console import market_pick
    fn = getattr(market_pick, "session_is_shared", None)
    if fn is not None:
        return bool(fn())
    try:
        from src.auth.admin_resolver import is_admin_session
        admin = bool(is_admin_session(sess)[0])
    except Exception:
        admin = str(sess.get("user_role") or "").strip().lower() == "admin"
    # 로그인 코드가 넣는 키는 `user_email`(`email`은 옛 픽스처 호환) — Z6과 같은 순서.
    return market_pick.is_shared(str(sess.get("user_email") or sess.get("email") or ""), admin)


def current_viewer() -> Optional[OrderViewer]:
    """지금 요청의 주문 보기 범위. 요청 밖·로그인 신원 없음이면 None(= 스코프 없음, 서버 자신)."""
    try:
        from flask import has_request_context, session
        if not has_request_context():
            return None
        raw = [session.get("user_id"), session.get("user_email"), session.get("email")]
        ids = frozenset(str(v).strip().casefold() for v in raw if v and str(v).strip())
        if not ids:
            return None
        return OrderViewer(shared=_session_shared(session), ids=ids)
    except Exception as exc:
        # 판정이 깨졌으면 **닫는다** — 신원은 있는데 범위를 모르면 오너 풀을 내주지 않는다.
        logger.warning("주문 범위 판정 실패 — 본인 행으로 제한: %s", exc)
        try:
            from flask import session
            ids = frozenset(str(v).strip().casefold()
                            for v in (session.get("user_id"), session.get("user_email")) if v)
        except Exception:
            ids = frozenset()
        return OrderViewer(shared=False, ids=ids)
