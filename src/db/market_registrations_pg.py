"""src/db/market_registrations_pg.py — 등록 파이프 P4: 마켓 등록 대장.

등록 파이프가 관통(카나리 10차)한 뒤 실제 등록이 나간다. **무엇을 등록했는지 서버가 기억해야**
반려감시가 감시 대상을 스스로 안다(그 전엔 오너가 sid를 손으로 입력). stage1 관례(pg.tx 커밋=durable).

PG 미가동(개발/테스트)이면 **프로세스 인메모리 폴백** — 기능은 돌되 영속 아님을 `durable`로 정직 표기.
"""
from __future__ import annotations

from typing import Optional

from . import pg

# PG 미가동 시 폴백(개발/테스트 전용 — 재시작에 휘발. durable=False로 정직 표기).
_MEM: dict = {}

# 감시 큐에 남는 상태 = **아직 확정 안 된 것들**.
#   `saved`(임시저장)는 조치 대상이지 확정이 아니다 — 승인요청을 다시 걸면 결과가 또 나온다.
#   ★ 이게 없으면 `_next_status`가 `saved`를 써도 행이 그대로 큐를 떠난다(반쪽 수리).
#     판정 쪽만 고치고 저장 쪽을 빼먹는 게 이 프로젝트의 단골 결함이라 둘을 같이 본다.
#: Y12-A(오너 2026-10-17 e): **반려도 계속 재조회한다**(다른 상태와 같은 주기) — 반려 판정이 재조회를 끊으면
#:   반려가 풀렸는지·다시 반려됐는지를 영영 모른다(지뢰 「반려 판정이 재조회를 끊는다」, 실측 Stagg 49일).
#:   단, 사유가 「임시저장」인 반려 줄(09-05 수리 전 판정)은 **오너 승인 뒤에만** 다시 조회한다(`_HELD_SQL`).
_WATCH_STATUSES = ("submitted", "unknown", "saved", "rejected")
_HELD_RE = __import__("re").compile(r"임시\s*저장|\bSAVED\b", __import__("re").I)
_HELD_SQL = "NOT (status = 'rejected' AND COALESCE(reject_comment, '') ~* '임시\\s*저장|SAVED')"


def _held(r: dict) -> bool:
    """오너 승인 전 재조회 보류 — 사유가 임시저장인 반려 줄."""
    return str(r.get("status") or "") == "rejected" and bool(_HELD_RE.search(str(r.get("reject_comment") or "")))


def enabled() -> bool:
    return pg.pg_enabled()


def _key(marketplace: str, product_id: str) -> str:
    return f"{marketplace}|{product_id}"


def record(product_id: str, *, marketplace: str = "coupang", account: str = "",
           vendor_sku: str = "", title: str = "", source_url: str = "",
           market_url: str = "") -> dict:
    """등록 성공분 적재(재등록이면 갱신). 반환 {ok, product_id, durable}.

    durable=False = PG 미가동 폴백(인메모리) — 재시작하면 사라진다는 뜻(가짜 영속 주장 금지).
    """
    pid = str(product_id or "").strip()
    if not pid:
        return {"ok": False, "error": "product_id 없음", "durable": False}
    row = {"marketplace": marketplace, "account": account, "product_id": pid,
           "vendor_sku": vendor_sku, "title": title, "source_url": source_url,
           "market_url": market_url, "status": "submitted", "reject_kind": "",
           "reject_comment": "", "prescription": "", "checked_at": None}
    if not enabled():
        _MEM[_key(marketplace, pid)] = row
        return {"ok": True, "product_id": pid, "durable": False}
    with pg.tx() as cur:
        cur.execute(
            """INSERT INTO market_registrations
                 (marketplace, account, product_id, vendor_sku, title, source_url, market_url)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (marketplace, product_id) WHERE deleted_at IS NULL
               DO UPDATE SET account=EXCLUDED.account, vendor_sku=EXCLUDED.vendor_sku,
                             title=EXCLUDED.title, source_url=EXCLUDED.source_url,
                             market_url=EXCLUDED.market_url, status='submitted'
               RETURNING product_id""",
            (marketplace, account, pid, vendor_sku, title, source_url, market_url))
        cur.fetchone()
    return {"ok": True, "product_id": pid, "durable": True}


def watch_queue(*, marketplace: str = "coupang", account: str = "", limit: int = 50) -> list:
    """감시 대상(미확정 등록분) — 오래 안 본 것 먼저. 반환: [{sid, title, account, ...}].

    확정된 건(approved/deleted)은 큐에 안 넣는다 — 반복 조회 낭비 방지. 반려는 넣는다(Y12-A e).
    """
    if not enabled():
        rows = [r for r in _MEM.values()
                if r["marketplace"] == marketplace and r["status"] in _WATCH_STATUSES and not _held(r)
                and (not account or r["account"] == account)]
        return [{"sid": r["product_id"], "title": r["title"], "account": r["account"],
                 "market_url": r["market_url"], "status": r["status"]}
                for r in rows[:max(0, int(limit))]]
    # `status`도 같이 준다(6-h-3 N3): 화면이 **상태별로 링크를 갈라야** 하는데,
    #   상태가 안 오면 갈 수가 없어 승인 전 건에도 구매자 URL을 걸게 된다(그게 그 결함이었다).
    sql = ["""SELECT product_id, title, account, market_url, status FROM market_registrations
              WHERE deleted_at IS NULL AND marketplace=%s AND status = ANY(%s) AND """ + _HELD_SQL]
    args = [marketplace, list(_WATCH_STATUSES)]
    if account:
        sql.append("AND account=%s")
        args.append(account)
    sql.append("ORDER BY checked_at NULLS FIRST, created_at LIMIT %s")
    args.append(max(0, int(limit)))
    with pg.query() as cur:
        cur.execute(" ".join(sql), tuple(args))
        rows = cur.fetchall()
    return [{"sid": r[0], "title": r[1], "account": r[2], "market_url": r[3], "status": r[4]}
            for r in rows]


def mark_checked(product_id: str, *, marketplace: str = "coupang", status: str = "",
                 reject_kind: str = "", reject_comment: str = "",
                 prescription: str = "", notified: bool = False) -> bool:
    """감시 결과 반영(상태·분류·처방·조회시각). 알림 보냈으면 notified=True로 중복 알림 방지."""
    pid = str(product_id or "").strip()
    if not pid:
        return False
    if not enabled():
        row = _MEM.get(_key(marketplace, pid))
        if not row:
            return False
        if status:
            row["status"] = status
        row.update({"reject_kind": reject_kind or row["reject_kind"],
                    "reject_comment": reject_comment or row["reject_comment"],
                    "prescription": prescription or row["prescription"],
                    "checked_at": "now"})
        if notified:
            row["notified_at"] = "now"
        return True
    sets = ["checked_at=now()"]
    args = []
    if status:
        sets.append("status=%s")
        args.append(status)
    for col, val in (("reject_kind", reject_kind), ("reject_comment", reject_comment),
                     ("prescription", prescription)):
        if val:
            sets.append(f"{col}=%s")
            args.append(val)
    if notified:
        sets.append("notified_at=now()")
    args.extend([marketplace, pid])
    with pg.tx() as cur:
        cur.execute(f"""UPDATE market_registrations SET {', '.join(sets)}
                        WHERE marketplace=%s AND product_id=%s AND deleted_at IS NULL""",
                    tuple(args))
        return cur.rowcount > 0


def find_by_vendor_sku(vendor_sku: str, *, marketplace: str = "coupang",
                       account: str = "") -> Optional[dict]:
    """판매자 SKU(아마존 ASIN 등)로 **이미 등록된 건**을 찾는다. 없으면 None.

    등록 파이프의 중복 방지용 — 반려 수리는 **신규 등록이 아니라 기존 sid 재제출**이 정석이라,
    같은 상품을 또 POST하지 않게 여기서 먼저 확인한다.
    """
    sku = str(vendor_sku or "").strip()
    if not sku:
        return None
    if not enabled():
        for r in _MEM.values():
            if (r["marketplace"] == marketplace and r.get("vendor_sku") == sku
                    and (not account or r["account"] == account)):
                return dict(r)
        return None
    sql = ["""SELECT product_id, account, title, status, reject_kind, prescription
              FROM market_registrations
              WHERE deleted_at IS NULL AND marketplace=%s AND vendor_sku=%s"""]
    args = [marketplace, sku]
    if account:
        sql.append("AND account=%s")
        args.append(account)
    sql.append("ORDER BY created_at DESC LIMIT 1")
    with pg.query() as cur:
        cur.execute(" ".join(sql), tuple(args))
        rows = cur.fetchall()
    if not rows:
        return None
    r = rows[0]
    return {"product_id": r[0], "account": r[1], "title": r[2], "status": r[3],
            "reject_kind": r[4], "prescription": r[5], "vendor_sku": sku}


def get(product_id: str, *, marketplace: str = "coupang") -> Optional[dict]:
    pid = str(product_id or "").strip()
    if not enabled():
        return _MEM.get(_key(marketplace, pid))
    with pg.query() as cur:
        cur.execute(
            """SELECT product_id, account, title, status, reject_kind, reject_comment, prescription
               FROM market_registrations
               WHERE marketplace=%s AND product_id=%s AND deleted_at IS NULL LIMIT 1""",
            (marketplace, pid))
        rows = cur.fetchall()
    if not rows:
        return None
    r = rows[0]
    return {"product_id": r[0], "account": r[1], "title": r[2], "status": r[3],
            "reject_kind": r[4], "reject_comment": r[5], "prescription": r[6]}


def recent_rejected(*, marketplace: str = "coupang", account: str = "", limit: int = 5) -> list:
    """반려 **확정** 건 최근 N개(화면 읽기용).

    F5(2026-09-04): 대시보드 02 카드가 `watch_queue`만 읽어서 `rejected`가 한 건도 안 보였다 — 읽는 함수를 따로 둔다.
    Y12-A(2026-10-17 e): 반려도 이제 `watch_queue`에 들어가 **재조회된다**(반려 판정이 재조회를 끊지 않는다).
    이 함수는 화면이 반려 줄만 골라 읽는 길로 남는다.
    """
    if not enabled():
        rows = [r for r in _MEM.values()
                if r["marketplace"] == marketplace and r["status"] == "rejected"
                and (not account or r["account"] == account)]
        return [{"sid": r["product_id"], "title": r["title"], "account": r["account"],
                 "market_url": r["market_url"], "reject_kind": r.get("reject_kind", ""),
                 "reject_comment": r.get("reject_comment", "")}
                for r in rows[:max(0, int(limit))]]
    sql = ["""SELECT product_id, title, account, market_url, reject_kind, reject_comment
              FROM market_registrations
              WHERE deleted_at IS NULL AND marketplace=%s AND status='rejected'"""]
    args = [marketplace]
    if account:
        sql.append("AND account=%s")
        args.append(account)
    sql.append("ORDER BY checked_at DESC NULLS LAST, created_at DESC LIMIT %s")
    args.append(max(0, int(limit)))
    with pg.query() as cur:
        cur.execute(" ".join(sql), tuple(args))
        rows = cur.fetchall()
    return [{"sid": r[0], "title": r[1], "account": r[2], "market_url": r[3],
             "reject_kind": r[4] or "", "reject_comment": r[5] or ""} for r in rows]


def account_counts(*, marketplace: str = "coupang") -> list:
    """Y12-C 대시보드 마켓별 현황 — `[{account, status, held, n, checked_at}]`. `held` = 사유가 임시저장인 반려 줄
    (09-05 수리 전 판정 — 반려로 세지 않는다, 진단 「임시저장 · 낡은 기록」 그대로)."""
    if not enabled():
        agg: dict = {}
        for r in _MEM.values():
            if r["marketplace"] != marketplace:
                continue
            k = (r["account"], r["status"], _held(r))
            a = agg.setdefault(k, {"account": k[0], "status": k[1], "held": k[2], "n": 0, "checked_at": None})
            a["n"] += 1
        return list(agg.values())
    with pg.query() as cur:
        cur.execute(f"""SELECT account, status, NOT ({_HELD_SQL}), count(*), max(checked_at) FROM market_registrations
                        WHERE deleted_at IS NULL AND marketplace=%s GROUP BY 1, 2, 3""", (marketplace,))
        rows = cur.fetchall()
    return [{"account": r[0] or "", "status": r[1] or "", "held": bool(r[2]), "n": int(r[3] or 0),
             "checked_at": r[4].isoformat() if hasattr(r[4], "isoformat") else (r[4] or None)} for r in rows]


def counts(*, marketplace: str = "coupang") -> dict:
    """상태별 건수(대시보드·정직 표기용). 조회 실패는 예외로 올린다(가짜 0 금지)."""
    if not enabled():
        out = {}
        for r in _MEM.values():
            if r["marketplace"] == marketplace:
                out[r["status"]] = out.get(r["status"], 0) + 1
        return out
    with pg.query() as cur:
        cur.execute("""SELECT status, count(*) FROM market_registrations
                       WHERE deleted_at IS NULL AND marketplace=%s GROUP BY status""",
                    (marketplace,))
        rows = cur.fetchall()
    return {r[0]: int(r[1]) for r in rows}


def reset_memory():
    """테스트 격리용 — 인메모리 폴백 비움."""
    _MEM.clear()
