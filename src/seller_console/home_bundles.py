"""Y12-A(오너 2026-10-17) — 대시보드(첫화면) 세 묶음. 묶음마다 숫자 하나 + 눌러서 펼침.

1. 손댈 것 — 반려(마켓별) · 보내기 실패 · 오너 확인 대기(지우기 제안 사진 · 등록 보류 · 「확인 필요」 원문 줄). 0이면 「없음」.
   옆에 「마켓 상태 마지막 조회 HH:MM」(0이 낡은 0인지 보이게).
2. 돌아가는 것 — 보내는 중(쿠팡·네이버 갱신 줄) · 다듬는 중 · 번역 대기. 0이면 묶음째 숨김.
3. 오늘 쓴 것 — 「이미지 번역 n/상한」 한 줄(상한 = 운영 env 값 그대로).

숫자는 이미 있는 값만 센다(새로 지어내지 않는다). 못 읽으면 그 묶음에 「확인 못 함」.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

STATUS_KEY = "market_status:last_check"
ATTN_SCAN_LIMIT = 300


def mark_status_checked(at: Optional[str] = None) -> None:
    """마켓 상태를 마켓에 물어 기록한 시각(마지막 성공 조회) — 대시보드 「마지막 조회 HH:MM」."""
    try:
        from src.db import image_translate_queue_pg as st
        st.state_set(STATUS_KEY, {"at": at or datetime.now(timezone.utc).isoformat()})
    except Exception as exc:                                     # noqa: BLE001
        logger.debug("[대시보드] 마지막 조회 기록 실패: %s", exc)


def _attention(seller_ids) -> Dict:
    from . import collect_history_store as store
    from .attention import items as attn_items
    import json
    rows = store.list_items(days=3650, seller_ids=seller_ids, lean=True, order="action", attn_only=True, limit=ATTN_SCAN_LIMIT)
    groups: Dict[str, Dict] = {}
    products = []
    for r in rows:
        try:
            ex = json.loads(r.get("extra_json") or "{}") or {}
        except Exception:                                        # noqa: BLE001
            ex = {}
        its = attn_items(ex, r.get("title") or "")
        if not its:
            continue
        products.append({"id": r.get("id"), "title": str(ex.get("title_ko") or r.get("title") or "")[:60],
                         "lines": [i["text"] + (f" · {i['note']}" if i.get("note") else "") for i in its]})
        for i in its:
            if i["kind"] == "rejected":
                key, label = f"rejected:{i['market']}", i["text"]
            elif i["kind"] == "send_fail":
                key, label = f"send_fail:{i['market']}", i["text"]
            else:
                key, label = "owner", "오너 확인 대기"
            g = groups.setdefault(key, {"label": label, "n": 0, "kind": i["kind"]})
            g["n"] += 1
    # Y12-A(오너 23:31): 등록 대장(복제 등록분 — 수집 목록 밖)의 **살아 있는** 반려도 같은 묶음에. 낡은 기록(임시저장 사유)은 안 올린다.
    for r in _ledger_rejections():
        label = f"쿠팡 — {_ACCOUNT_KO.get(str(r.get('account') or ''), str(r.get('account') or ''))} 승인반려"
        from .attention import check_note
        products.append({"id": "", "title": str(r.get("title") or r.get("product_id") or "")[:60],
                         "lines": [label + (f" · {r['kind_word']}" if r.get("kind_word") else "")
                                   + f" · {check_note(r.get('checked_at'))}"]})
        g = groups.setdefault(f"rejected:ledger:{r.get('account')}", {"label": label, "n": 0, "kind": "rejected"})
        g["n"] += 1
    order = {"rejected": 0, "send_fail": 1, "owner": 2}
    return {"n": len(products), "groups": sorted(groups.values(), key=lambda g: (order.get(g["kind"], 9), g["label"])),
            "products": products[:30], "capped": len(rows) >= ATTN_SCAN_LIMIT}


_ACCOUNT_KO = {"gogane": "고가네", "woojoo": "우주대행"}


def _ledger_rejections(limit: int = 50) -> List[Dict]:
    """등록 대장의 반려 줄 **전부**(오너 e — 조회가 오래됐다고 숨기지 않는다, 「조회 낡음」 표시).
    사유가 「임시저장」인 줄은 반려가 아니라 임시저장이다(낱말은 `ops_snapshot._reject_words` 한 곳) — 손댈 것 · 반려에서 뺀다."""
    try:
        from src.db import market_registrations_pg as ledger
        if not ledger.enabled():
            return []
        from src.pipeline.ops_snapshot import _reject_words
        out = []
        for r in ledger.recent_rejected(marketplace="coupang", limit=limit) or []:
            w = _reject_words(r)
            if w["phase"] == "rejected":
                out.append(dict(r, **w))
        return out
    except Exception as exc:                                     # noqa: BLE001 — 대장 실패가 묶음을 막지 않는다
        logger.debug("[대시보드] 등록 대장 반려 조회 실패: %s", exc)
        return []


def _running() -> Dict:
    from src.services import coupang_detail_refresh as cdr
    from src.services import naver_detail_refresh as ndr
    sending = len(cdr.queue_rows()) + len(ndr.queue_rows())
    polishing = 0
    try:
        from src.db import pg
        if pg.pg_enabled():
            with pg.query() as cur:
                cur.execute("SELECT count(*) FROM app_state WHERE key LIKE 'imgpolish:item:%%' AND value->>'running' = 'true'")
                polishing = int((cur.fetchone() or (0,))[0] or 0)
    except Exception as exc:                                     # noqa: BLE001
        logger.debug("[대시보드] 다듬는 중 집계 실패: %s", exc)
    from src.db import image_translate_queue_pg as q
    c = q.counts() or {}
    waiting = int(c.get("queued") or 0) + int(c.get("running") or 0)
    lines = [x for x in ((f"보내는 중 {sending}건", sending), (f"다듬는 중 {polishing}건", polishing),
                         (f"번역 대기 {waiting}장", waiting)) if x[1]]
    return {"n": sending + polishing + waiting, "lines": [x[0] for x in lines]}


def _today() -> Dict:
    from src.services import image_translate_auto as A
    from src.db import image_translate_queue_pg as q
    return {"used": int(q.day_count(A._day_key()) or 0), "cap": A.daily_cap()}


def build(seller_ids) -> Dict:
    """`{attention:{n, groups, products, error}, running:{n, lines}, today:{used, cap}, last_check}`."""
    out: Dict = {}
    for key, fn in (("attention", lambda: _attention(seller_ids)), ("running", _running), ("today", _today)):
        try:
            out[key] = fn()
        except Exception as exc:                                 # noqa: BLE001 — 한 묶음 실패가 다른 묶음을 막지 않는다
            logger.warning("[대시보드] %s 묶음 실패: %s", key, exc)
            out[key] = {"error": "확인 못 함"}
    try:
        from src.db import image_translate_queue_pg as st
        from .attention import kst
        out["last_check"] = kst((st.state_get(STATUS_KEY) or {}).get("at"))
    except Exception:                                            # noqa: BLE001
        out["last_check"] = ""
    return out
