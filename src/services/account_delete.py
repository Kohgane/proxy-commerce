"""오너 11-26 감독 3a — 앱 안 「계정 삭제」(앱스토어 심사 5.1.1(v)).

흐름: 유저가 더보기 › 계정 › 「계정 삭제」에서 두 번 확인하고 **요청**한다 → 이 줄(`app_state account_delete:requests`)에 서고
로그아웃된다 → **실제 삭제는 오너가 관리자 화면에서 누를 때만**(`execute`). 그 전에 유저가 다시 로그인하면 요청을 거둘 수 있다.

지우는 것(실행 시): 로그인 계정(비활성 + 삭제 표시) · 발급 토큰 전부 폐기 · 연결한 마켓 키 · 수집한 상품.
남기는 것: 주문·정산 기록(전자상거래법상 거래 기록 5년 보관 의무 — 화면에 그대로 적는다).
마켓에 올린 상품은 마켓 쪽에 남는다(우리가 판매중지·삭제하지 않는다 — 마켓 전송은 오너 확인 사항).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

KEY = "account_delete:requests"
MAX_ROWS = 500
CONFIRM_WORD = "삭제"

SCOPE_DELETE = ("로그인 계정(이메일·소셜 연결 — 애플로 가입했으면 애플 쪽 연결도 끊어요)", "수집한 상품과 편집 내용", "연결한 마켓 API 키", "발급한 수집기 토큰")
SCOPE_KEEP = ("주문·정산 기록 — 전자상거래법에 따라 5년 보관한 뒤 지워요",
              "이미 마켓에 올린 상품 — 각 마켓 판매자센터에서 직접 내려 주세요")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rows() -> List[dict]:
    from src.db import image_translate_queue_pg as st
    return list((st.state_get(KEY) or {}).get("rows") or [])


def _save(rs: List[dict]) -> None:
    from src.db import image_translate_queue_pg as st
    st.state_set(KEY, {"rows": rs[-MAX_ROWS:]})


def pending_for(user_id: str) -> Optional[dict]:
    uid = str(user_id or "")
    return next((r for r in rows() if r.get("user_id") == uid and r.get("state") == "requested"), None)


def request(user_id: str, email: str = "", reason: str = "") -> dict:
    """삭제 **요청**을 줄에 세운다(같은 사람의 대기 요청이 있으면 그대로 돌려준다). 계정은 아직 그대로다."""
    uid = str(user_id or "").strip()
    if not uid:
        raise ValueError("로그인이 필요합니다.")
    hit = pending_for(uid)
    if hit:
        return hit
    rec = {"id": uuid.uuid4().hex[:12], "user_id": uid, "email": str(email or "")[:200],
           "reason": str(reason or "").strip()[:300], "at": _now(), "state": "requested"}
    rs = rows()
    rs.append(rec)
    _save(rs)
    logger.warning("[계정 삭제] 요청 id=%s user=%s — 오너 확인 대기", rec["id"], uid)
    return rec


def cancel(user_id: str) -> bool:
    rs, done = rows(), False
    for r in rs:
        if r.get("user_id") == str(user_id or "") and r.get("state") == "requested":
            r.update(state="cancelled", cancelled_at=_now())
            done = True
    if done:
        _save(rs)
    return done


def execute(req_id: str, by: str) -> Dict:
    """오너가 누를 때만 — 요청 한 건을 실제로 지운다. 단계마다 결과를 그대로 적는다(실패를 성공으로 적지 않는다)."""
    rs = rows()
    rec = next((r for r in rs if r.get("id") == req_id), None)
    if not rec:
        return {"ok": False, "error": "그 요청이 없어요."}
    if rec.get("state") != "requested":
        return {"ok": False, "error": f"이미 처리된 요청이에요({rec.get('state')})."}
    uid, email = rec["user_id"], rec.get("email") or ""
    ids = {x for x in (uid, email) if x}
    steps: Dict[str, str] = {}

    try:
        from src.auth import personal_tokens as pt
        toks = [t for t in pt.list_tokens(uid, user_ids=ids) if not t.get("revoked")]
        n = sum(1 for t in toks if pt.revoke_token(t["token_hash"], uid, user_ids=ids))
        steps["tokens"] = f"폐기 {n}/{len(toks)}"
    except Exception as exc:                                    # noqa: BLE001
        steps["tokens"] = f"실패: {type(exc).__name__}: {str(exc)[:120]}"
    try:
        from src.seller_console import market_credentials as mc
        n = 0
        for sid in ids:
            for m in list((mc._load_all(sid) or {}).keys()):
                n += int(bool(mc.delete(sid, m)))
        steps["market_keys"] = f"삭제 {n}"
    except Exception as exc:                                    # noqa: BLE001
        steps["market_keys"] = f"실패: {type(exc).__name__}: {str(exc)[:120]}"
    try:
        from src.seller_console import collect_history_store as chs
        items = chs.list_items(seller_ids=ids, days=36500, lean=True)
        gone = chs.delete_ids([str(i.get("id")) for i in items], seller_ids=ids)
        steps["collected"] = f"삭제 {len(gone)}/{len(items)}"
    except Exception as exc:                                    # noqa: BLE001
        steps["collected"] = f"실패: {type(exc).__name__}: {str(exc)[:120]}"
    try:                                                           # 오너 11-26 오후 ④: 애플 로그인 계정이면 애플 쪽 토큰도 폐기
        from src.auth.apple_tokens import revoke as _apple_revoke
        steps["apple"] = _apple_revoke(uid)["step"]
    except Exception as exc:                                       # noqa: BLE001
        steps["apple"] = f"실패: {type(exc).__name__}: {str(exc)[:120]}"
    try:
        from src.auth.user_store import get_store
        store = get_store()
        user = store.find_by_id(uid)
        if user:
            user.active = False
            store.update(user)
            steps["account"] = "비활성(로그인 불가)"
        else:
            steps["account"] = "계정 없음(이미 지워짐)"
    except Exception as exc:                                    # noqa: BLE001
        steps["account"] = f"실패: {type(exc).__name__}: {str(exc)[:120]}"

    ok = not any(v.startswith("실패") for v in steps.values())
    rec.update(state="done" if ok else "partial", done_at=_now(), done_by=str(by or "")[:200], steps=steps)
    _save(rs)
    logger.warning("[계정 삭제] 실행 id=%s user=%s by=%s ok=%s %s", req_id, uid, by, ok, steps)
    return {"ok": ok, "steps": steps, "state": rec["state"]}
