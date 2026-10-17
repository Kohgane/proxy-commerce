"""Y12-A(오너 2026-10-17) · Y12-C(2026-10-18) — 대시보드(첫화면). Wing·퍼센티 식 밀도 — 390px 기준 2열 타일.

A. 오늘 할 일 — 손댈 것을 숫자가 아니라 **줄로**: 「VRSUK · 지우기 제안 8장 · [보기]」. 0이면 「없음」 한 줄.
   기준(Y12-B) = 오너가 눌러야 풀리는 것만 — 반려(마켓별) · 보내기 실패 · 수집 실패(재수집 소진) · 오너 확인 대기.
B. 마켓별 현황 표 4행(고가네 쿠팡 · 우주대행 쿠팡 · 셰고가 · 고코스모스): 판매중 · 승인대기 · 반려 · 연결 · 마지막 조회.
   등록 기록(`uploaded[].review`)과 등록 대장(쿠팡 복제 등록분)에서 센다 — 마켓에 묻지 않는다.
C. 상품 현황 타일 4: 수집 · 등록 완료 · 미등록 · 손댈 것 — 누르면 목록이 그 필터로 열린다.
D. 최근 동작 10줄(KST) — 기존 기록에서만(수집 · 등록 · 보냄 · 다듬기 · 상태 조회 결과).
E. 오늘 쓴 것 — 이미지 번역 n/상한 · 다듬기 n/상한(상한 = 운영 env 값 그대로).
돌아가는 것 — 보내는 중 · 다듬는 중 · 번역 대기 · 재수집 대기. 0이면 묶음째 숨김.
주문·매출 타일은 없다 — 운영 DB 주문은 QA 시험 1건뿐(10-18 실측). 빈 약속 타일 금지(오너).

전부 상품 **한 쿼리**(`collect_history_store.dashboard_rows` — 작은 칸만)에서 센다. 못 읽으면 그 묶음에 「확인 못 함」.
Y12-C 버그 1: 「마켓 상태 마지막 조회 기록 없음」은 거짓이었다 — 따로 적는 칸(`market_status:last_check`)을 아무도 안 썼다.
  이제 등록 기록의 조회 시각(`review.checked_at`) 중 가장 늦은 것을 그대로 읽는다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

RECENT_N = 10
TODO_N = 30
#: B 표 4행 — (자리, 이름, 마켓)
MARKET_ROWS = (("coupang:gogane", "고가네", "쿠팡"), ("coupang:woojoo", "우주대행", "쿠팡"),
               ("smartstore:chezgoga", "셰고가", "스마트스토어"), ("smartstore:gocosmos", "고코스모스", "스마트스토어"))
_ACCOUNT_KO = {"gogane": "고가네", "woojoo": "우주대행"}


def _bucket(state: str) -> Optional[str]:
    """등록 상태 → B 표 칸. 판매중 = 승인완료·판매중(품절 포함) · 반려 = 승인반려·판매금지 · 삭제·판매종료는 안 센다 · 나머지 승인대기."""
    st = str(state or "")
    if st == "approved":
        return "sale"
    if st == "rejected":
        return "rejected"
    if st == "deleted":
        return None
    return "wait"


def _rows(seller_ids) -> List[Dict]:
    from . import collect_history_store as store
    return store.dashboard_rows(seller_ids=seller_ids)


def _title(r: Dict) -> str:
    from src.collectors.ko_polish import unbrace_title
    t = str((r.get("extra") or {}).get("title_ko") or r.get("title") or "").strip()
    return (unbrace_title(t).strip() or t)[:60]


def _ts(v) -> Optional[datetime]:
    from .attention import _ts as ts
    return ts(v)


def _when(d: Optional[datetime], now: Optional[datetime] = None) -> str:
    """오늘이면 「HH:MM」, 아니면 「MM-DD HH:MM」(KST) — 낡은 시각이 오늘처럼 읽히지 않게."""
    from .attention import KST
    if not d:
        return ""
    k = d.astimezone(KST)
    today = (now or datetime.now(timezone.utc)).astimezone(KST).date()
    return k.strftime("%H:%M") if k.date() == today else k.strftime("%m-%d %H:%M")


# ── A. 오늘 할 일 ────────────────────────────────────────────────────────────────────────────────────
def _attention(seller_ids, rows: Optional[List[Dict]] = None) -> Dict:
    from .attention import check_note, items as attn_items
    rows = _rows(seller_ids) if rows is None else rows
    groups: Dict[str, Dict] = {}
    products, todo = [], []
    hot = sorted((r for r in rows if r.get("attn_n")),
                 key=lambda r: str(r.get("last_action_at") or r.get("collected_at") or ""), reverse=True)
    for r in hot:
        its = attn_items(r.get("extra") or {}, r.get("title") or "")
        if not its:
            continue
        title = _title(r)
        lines = [i["text"] + (f" · {i['note']}" if i.get("note") else "") for i in its]
        products.append({"id": r.get("id"), "title": title, "lines": lines})
        for ln in lines:
            todo.append({"id": r.get("id"), "title": title, "text": ln, "url": f"/seller/collect/history?open={r.get('id')}"})
        for i in its:
            if i["kind"] == "rejected":
                key, label = f"rejected:{i['market']}", i["text"]
            elif i["kind"] == "send_fail":
                key, label = f"send_fail:{i['market']}", i["text"]
            elif i["kind"] == "collect_fail":
                key, label = "collect_fail", "수집 실패"
            else:
                key, label = "owner", "오너 확인 대기"
            g = groups.setdefault(key, {"label": label, "n": 0, "kind": i["kind"]})
            g["n"] += 1
    # Y12-A: 등록 대장(복제 등록분 — 수집 목록 밖)의 반려도 같은 묶음에. 사유가 임시저장인 줄은 반려가 아니다.
    for r in _ledger_rejections():
        label = f"쿠팡 — {_ACCOUNT_KO.get(str(r.get('account') or ''), str(r.get('account') or ''))} 승인반려"
        line = label + (f" · {r['kind_word']}" if r.get("kind_word") else "") + f" · {check_note(r.get('checked_at'))}"
        title = str(r.get("title") or r.get("product_id") or "")[:60]
        products.append({"id": "", "title": title, "lines": [line]})
        todo.append({"id": "", "title": title, "text": line, "url": "/seller/diagnostics"})
        g = groups.setdefault(f"rejected:ledger:{r.get('account')}", {"label": label, "n": 0, "kind": "rejected"})
        g["n"] += 1
    order = {"rejected": 0, "send_fail": 1, "collect_fail": 2, "owner": 3}
    return {"n": len(products), "groups": sorted(groups.values(), key=lambda g: (order.get(g["kind"], 9), g["label"])),
            "products": products[:TODO_N], "todo": todo[:TODO_N], "more": max(0, len(todo) - TODO_N), "capped": False}


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


# ── B. 마켓별 현황 ──────────────────────────────────────────────────────────────────────────────────
def _markets(rows: List[Dict]) -> Dict:
    from .listing_status import records, slot_of
    acc = {slot: {"sale": 0, "wait": 0, "rejected": 0, "checked": None} for slot, _n, _m in MARKET_ROWS}

    def _add(a, state, n=1, checked=None):
        b = _bucket(state)
        if b:
            a[b] += n
        d = _ts(checked)
        if d and (a["checked"] is None or d > a["checked"]):
            a["checked"] = d

    for r in rows:
        for rec in records(r.get("extra") or {}):
            a = acc.get(slot_of(rec["market"]))
            if a is not None:
                rv = rec.get("review") or {}
                _add(a, rv.get("state"), checked=rv.get("checked_at"))
    try:                                                         # 등록 대장(쿠팡 복제 등록분 — 수집 목록 밖)
        from src.db import market_registrations_pg as ledger
        if ledger.enabled():
            for c in ledger.account_counts(marketplace="coupang") or []:
                a = acc.get(f"coupang:{c['account']}")
                if a is not None and not c.get("held"):          # 사유 임시저장 반려 줄은 세지 않는다(진단 「임시저장 · 낡은 기록」)
                    _add(a, "approved" if c["status"] == "approved" else c["status"], n=int(c["n"]), checked=c.get("checked_at"))
    except Exception as exc:                                     # noqa: BLE001
        logger.debug("[대시보드] 등록 대장 집계 실패: %s", exc)
    connected = {}
    try:
        from src.pipeline.ops_snapshot import account_tiles
        connected = {f"{t['market']}:{t['account']}": bool(t.get("connected")) for t in account_tiles()}
    except Exception as exc:                                     # noqa: BLE001
        logger.debug("[대시보드] 계정 연결 확인 실패: %s", exc)
    out, latest = [], None
    for slot, name, market_ko in MARKET_ROWS:
        a = acc[slot]
        if a["checked"] and (latest is None or a["checked"] > latest):
            latest = a["checked"]
        out.append({"slot": slot, "name": name, "market_ko": market_ko, "sale": a["sale"], "wait": a["wait"],
                    "rejected": a["rejected"], "connected": connected.get(slot), "last_check": _when(a["checked"])})
    return {"rows": out, "last_check": _when(latest)}


# ── C. 상품 현황 ────────────────────────────────────────────────────────────────────────────────────
def _products(rows: List[Dict]) -> Dict:
    from .listing_status import records
    reg = sum(1 for r in rows if records(r.get("extra") or {}))
    return {"collected": len(rows), "registered": reg, "unregistered": len(rows) - reg,
            "attn": sum(1 for r in rows if r.get("attn_n"))}


# ── D. 최근 동작 ────────────────────────────────────────────────────────────────────────────────────
def _recent(rows: List[Dict], n: int = RECENT_N) -> List[Dict]:
    from .attention import KST, recent_events
    ev = []
    for r in rows:
        for e in recent_events(r.get("extra") or {}, r.get("collected_at") or ""):
            ev.append((e["at"], e["text"], r))
    ev.sort(key=lambda x: x[0], reverse=True)
    out, seen = [], set()
    for d, t, r in ev:                                           # 같은 분·같은 상품·같은 줄(쿠팡 두 계정에 같이 보냄)은 한 줄
        at = d.astimezone(KST).strftime("%m-%d %H:%M")
        if (at, t, r.get("id")) in seen:
            continue
        seen.add((at, t, r.get("id")))
        out.append({"at": at, "text": t, "title": _title(r), "id": r.get("id")})
        if len(out) >= n:
            break
    return out


# ── 돌아가는 것 · 오늘 쓴 것 ─────────────────────────────────────────────────────────────────────────
def _running(seller_ids=None, rows: Optional[List[Dict]] = None) -> Dict:
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
    # Y12-B: 자동 재수집이 예정된 수집 실패 — 손댈 것이 아니라 여기(오너가 누를 일이 없다)
    rows = _rows(seller_ids) if rows is None else rows
    refetch = sum(1 for r in rows if isinstance((r.get("extra") or {}).get("attn"), dict) and r["extra"]["attn"].get("refetch"))
    lines = [x for x in ((f"보내는 중 {sending}건", sending), (f"다듬는 중 {polishing}건", polishing),
                         (f"번역 대기 {waiting}장", waiting), (f"재수집 대기 {refetch}건", refetch)) if x[1]]
    return {"n": sending + polishing + waiting + refetch, "lines": [x[0] for x in lines]}


def _today() -> Dict:
    from src.services import image_translate_auto as A
    from src.services import image_polish as IP
    from src.db import image_translate_queue_pg as q
    return {"used": int(q.day_count(A._day_key()) or 0), "cap": A.daily_cap(),
            "polish_used": int(IP.today_count() or 0), "polish_cap": IP.daily_cap()}


def build(seller_ids) -> Dict:
    """`{attention, running, today, markets, products, recent, last_check}` — 묶음마다 실패해도 다른 묶음은 그린다."""
    out: Dict = {}
    try:
        rows = _rows(seller_ids)
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[대시보드] 상품 읽기 실패: %s", exc)
        rows = None
    for key, fn in (("attention", lambda: _attention(seller_ids, rows)), ("running", lambda: _running(seller_ids, rows)),
                    ("today", _today), ("markets", lambda: _markets(rows)), ("products", lambda: _products(rows)),
                    ("recent", lambda: _recent(rows))):
        try:
            if rows is None and key != "today":
                raise RuntimeError("상품을 읽지 못함")
            out[key] = fn()
        except Exception as exc:                                 # noqa: BLE001 — 한 묶음 실패가 다른 묶음을 막지 않는다
            logger.warning("[대시보드] %s 묶음 실패: %s", key, exc)
            out[key] = {"error": "확인 못 함"}
    mk = out.get("markets")
    out["last_check"] = mk.get("last_check", "") if isinstance(mk, dict) else ""
    return out
