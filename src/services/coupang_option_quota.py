"""Y13-F F1(오너 2026-10-19 13:31 KST) — 쿠팡 「오늘 등록할 수 있는 구매옵션 개수(5000)」.

실측: 고가네(A01381223) 등록 두 건이 「[A01381223]가 오늘 등록할 수 있는 구매옵션 개수(5000)를 초과… 현재까지 요청: 5000,
현재요청: 10」으로 거부됐다. 이 한도는 **판매자(vendorId) 공용**이다 — 같은 계정을 쓰는 다른 도구(브릿지 밖)의 요청도 같이 센다.
예전엔 이 거부가 `api_error`(재시도 가능)로 분류돼 같은 날 다시 눌러도 같은 답이었다.

- `parse(text)` — 거부 원문 → `{vendor, limit, used, req}`(아니면 None).
- `count(vendor, n, kind)` — 브릿지가 쿠팡에 보낸 items 수(등록 POST · 수정 PUT · 상세 갱신 큐)를 **KST 날짜별**로 센다(원자적).
- `observe(vendor, parsed)` — 거부 원문이 알려 준 「현재까지 요청」(브릿지 밖 포함 전체)을 그날 기록으로 남긴다.
- `usage(vendor)` — `{bridge, observed, limit, left, kinds, day}` — 사전검증 한 줄과 집계 보고가 읽는다.
- 이월: `carry_add` · `carry_rows` · `carry_due` — KST 00:10 이후 같은 등록을 다시 시도한다(`oneshot_ops`가 틱에서 꺼낸다).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
LIMIT = 5000
CARRY_KEY = "coupang:option_carry"
#: 이월 재시도 시각 — KST 00:10 이후(쿠팡 「오늘」이 바뀐 뒤 · 자정 직후 몰림 피함)
CARRY_AFTER = (0, 10)
CODE = "coupang_option_quota"
_RE = re.compile(r"\[(?P<vendor>[A-Z0-9]+)\][^0-9]{0,40}?구매옵션\s*개수\((?P<limit>\d+)\)[^0-9]*?초과"
                 r"(?:.*?현재까지\s*요청\s*[:：]\s*(?P<used>\d+))?(?:.*?현재\s*요청\s*[:：]\s*(?P<req>\d+))?", re.S)


def _st():
    from src.db import image_translate_queue_pg as st
    return st


def today(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(KST).strftime("%Y-%m-%d")


def parse(text) -> Optional[Dict]:
    """「[A01381223]가 오늘 등록할 수 있는 구매옵션 개수(5000)를 초과… 현재까지 요청: 5000, 현재요청: 10」 → 숫자들."""
    m = _RE.search(str(text or ""))
    if not m:
        return None
    g = m.groupdict()
    return {"vendor": g["vendor"], "limit": int(g["limit"]),
            "used": int(g["used"]) if g.get("used") else None, "req": int(g["req"]) if g.get("req") else None}


def _day_key(vendor: str, day: str, part: str = "") -> str:
    return f"coupang_opts:{vendor}:{day}" + (f":{part}" if part else "")


def count(vendor: str, n: int, kind: str = "post") -> None:
    """브릿지가 보낸 items 수를 센다 — kind = post(등록) · put(수정) · refresh(상세 갱신 큐). 실패해도 전송은 막지 않는다."""
    vendor, n = str(vendor or "").strip(), int(n or 0)
    if not vendor or n <= 0:
        return
    try:
        from src.db import option_translate_queue_pg as oq
        day = today()
        oq.take_n(_day_key(vendor, day), 10 ** 9, n)
        oq.take_n(_day_key(vendor, day, kind), 10 ** 9, n)
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[쿠팡 옵션 수] 기록 실패(전송은 그대로) vendor=%s n=%s: %s", vendor, n, exc)


def observe(vendor: str, parsed: Dict) -> None:
    """거부 원문의 「현재까지 요청」(브릿지 밖 포함) — 그날 가장 큰 값을 남긴다."""
    if not parsed or not vendor:
        return
    try:
        key = _day_key(vendor, today(), "observed")
        st = _st()
        cur = st.state_get(key) or {}
        used = int(parsed.get("used") or 0)
        if used >= int(cur.get("used") or 0):
            st.state_set(key, {"used": used, "limit": int(parsed.get("limit") or LIMIT), "req": parsed.get("req"),
                               "at": datetime.now(timezone.utc).isoformat()})
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[쿠팡 옵션 수] 관측 기록 실패: %s", exc)


def usage(vendor: str, day: Optional[str] = None) -> Dict:
    vendor, day = str(vendor or "").strip(), day or today()
    out = {"vendor": vendor, "day": day, "bridge": 0, "kinds": {}, "observed": None, "limit": LIMIT, "left": LIMIT}
    if not vendor:
        return out
    try:
        from src.db import option_translate_queue_pg as oq
        out["bridge"] = oq.day_count(_day_key(vendor, day))
        out["kinds"] = {k: oq.day_count(_day_key(vendor, day, k)) for k in ("post", "put", "refresh")}
        obs = _st().state_get(_day_key(vendor, day, "observed")) or {}
        if obs:
            out["observed"] = int(obs.get("used") or 0)
            out["limit"] = int(obs.get("limit") or LIMIT)
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("[쿠팡 옵션 수] 읽기 실패: %s", exc)
    out["left"] = max(0, out["limit"] - max(out["bridge"], out["observed"] or 0))
    return out


def caution(vendor: str, items: int) -> str:
    """사전검증 한 줄 — 「오늘 쿠팡 옵션 사용(브릿지분) n/5000」 + 등록할 SKU 수가 남은 수를 넘으면 경고."""
    u = usage(vendor)
    line = f"오늘 쿠팡 옵션 사용(브릿지분) {u['bridge']:,}/{u['limit']:,}"
    if u["observed"] is not None:
        line += f" · 쿠팡이 알려 준 오늘 전체 {u['observed']:,}(브릿지 밖 포함)"
    if items and items > u["left"]:
        line += f" — 이번 등록 옵션 {items}개가 남은 {u['left']:,}개를 넘어요(쿠팡이 거부하면 내일 KST 00:10 이후 자동 재시도)"
    return line


def refresh_daily_items() -> int:
    import os
    try:
        return max(0, int(os.getenv("COUPANG_REFRESH_DAILY_ITEMS", "200")))
    except ValueError:
        return 200


def refresh_block(vendor: str) -> str:
    """상세 갱신 큐가 오늘 더 보내면 안 되는 사유(없으면 빈 문자열) — 한도 소진(쿠팡이 알려 준 수) 또는 갱신분 하루 상한."""
    if not vendor:
        return ""
    u = usage(vendor)
    if u["observed"] is not None and u["observed"] >= u["limit"]:
        return f"쿠팡 일일 옵션 한도 소진({u['observed']:,}/{u['limit']:,}) — 내일 KST 00:10 이후 다시 보내요"
    cap = refresh_daily_items()
    if int(u["kinds"].get("refresh") or 0) >= cap:
        return f"오늘 상세 갱신으로 보낸 옵션 {u['kinds'].get('refresh'):,}개 — 하루 상한 {cap:,}개라 내일 보내요"
    return ""


# ── 이월(내일 자동 재시도) ────────────────────────────────────────────────────────────────

def carry_rows() -> List[Dict]:
    return [r for r in (_st().state_get(CARRY_KEY) or {}).get("rows") or [] if isinstance(r, dict)]


def carry_add(item_id: str, market: str, uid: str, parsed: Optional[Dict] = None) -> bool:
    """같은 상품·마켓이 이미 줄에 있으면 날짜만 갱신(중복 0). 반환 = 새로 넣었나."""
    st = _st()
    cur = st.state_get(CARRY_KEY) or {}
    rows = [r for r in cur.get("rows") or [] if isinstance(r, dict)]
    now = datetime.now(timezone.utc)
    hit = next((r for r in rows if r.get("item_id") == item_id and r.get("market") == market), None)
    if hit:
        hit.update(day=today(now), at=now.isoformat(), quota=parsed or hit.get("quota"), state="queued")
    else:
        rows.append({"item_id": str(item_id), "market": str(market), "uid": str(uid or ""), "day": today(now),
                     "at": now.isoformat(), "tries": 0, "quota": parsed or {}, "state": "queued"})
    st.state_set(CARRY_KEY, dict(cur, rows=rows))
    return hit is None


def carry_due(now: Optional[datetime] = None) -> List[Dict]:
    """다시 보낼 때가 된 줄 — 넣은 날(KST)보다 뒤 날짜이고 KST 00:10이 지났을 때."""
    now = now or datetime.now(timezone.utc)
    k = now.astimezone(KST)
    if (k.hour, k.minute) < CARRY_AFTER:
        return []
    d = k.strftime("%Y-%m-%d")
    return [r for r in carry_rows() if r.get("state", "queued") == "queued" and str(r.get("day") or "") < d]


def carry_done(item_id: str, market: str, result: Dict) -> None:
    """성공만 제거한다. 한도는 다음 날로, 그 밖의 실패·응답 유실은 확인 대기로 보존한다.

    응답 유실 뒤 재전송하면 중복 상품이 생길 수 있다. 확인 대기는 자동으로 다시 보내지 않으며,
    원인 해결 후 명시적인 등록 요청이 다시 한도에 걸렸을 때 carry_add가 다시 줄에 세운다.
    """
    st = _st()
    cur = st.state_get(CARRY_KEY) or {}
    rows = [r for r in cur.get("rows") or [] if isinstance(r, dict)]
    keep = []
    for r in rows:
        if r.get("item_id") == item_id and r.get("market") == market:
            r = dict(r, tries=int(r.get("tries") or 0) + 1, last=result, last_at=datetime.now(timezone.utc).isoformat())
            if result.get("error_code") == CODE:
                r["day"] = today()
                r["state"] = "queued"
                keep.append(r)
            elif not result.get("success"):
                r["state"] = "needs_review"
                keep.append(r)
            continue
        keep.append(r)
    log = list(cur.get("log") or [])[-19:] + [{"item_id": item_id, "market": market, "at": datetime.now(timezone.utc).isoformat(),
                                               "ok": bool(result.get("success")), "code": result.get("error_code") or "",
                                               "message": str(result.get("message") or "")[:300]}]
    st.state_set(CARRY_KEY, dict(cur, rows=keep, log=log))
