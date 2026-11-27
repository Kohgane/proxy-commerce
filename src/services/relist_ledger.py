"""오너 11-27 11:51 — 판매 재개 목록이 원가·소싱처를 **볼트 장부에서도** 찾는다(읽기 전용 참조).

1,679줄이 전부 「원본 주소 없음」이었다 — 앱의 수집 기록에는 없고, 원가·원본은 볼트 장부(소싱맵 · 가격 가드 원가표
`radar/cost_pin.json` · 등록 체인 카탈로그 · 쿠팡 미러 장부)에만 있었다. 그 장부를 상품 단위 요약으로 받아 캐시한다.

받는 길: 볼트 오라클 작업이 요약을 조각(`MAX_ROWS_PER_PART`줄)으로 나눠 `ops:oneshot:queue`에
`{op: relist_ledger_load, store, part, parts, src, rows: [...]}`를 **덧붙인다**(오너가 허용한 운영 DB 쓰기 그대로) →
10분 틱이 `load_part`로 이 캐시(`relist:ledger:<store>`)에 합친다.

한 줄에 싣는 것 = 상품번호(스스 채널 번호 또는 쿠팡 `CP-` 번호) · 원가 · 통화 · 소싱처 주소 · 갱신일 · 출처 · 볼트 사유
(판매중지 때 그 작업이 남긴 사유) · 쿠팡 판매 건수. **그 밖의 칸은 버린다**(손님 정보·비밀값이 섞여 와도 저장 안 함).
오너가 화면에서 넣은 원가는 출처 「오너 입력」으로 같은 캐시에 들어가고, 장부를 다시 받아도 덮이지 않는다.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

KEY = "relist:ledger:{}"
MAX_ROWS_PER_PART = 400
OWNER_SRC = "오너 입력"
#: 출처 이름 — 볼트 장부 이름을 화면 말로(모르는 이름은 받은 그대로 40자)
SRC_KO = {"sourcing_map": "볼트 소싱맵", "sourcing_map_name": "볼트 소싱맵(이름으로 찾음)", "cost_pin": "원가표",
          "catalog": "등록 체인 카탈로그", "coupang_mirror": "쿠팡 미러 장부", "vault_log": "볼트 작업 기록", "owner": OWNER_SRC}
_CUR = re.compile(r"^[A-Z]{3}$")
_NO = re.compile(r"^\d{5,15}$")
_SKU = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{1,39}$")
#: 볼트 사유 중 「다시 켜면 안 되는 것」 — 반려·소명·상표·금지로 내린 상품
_HARD_VAULT = ("반려", "소명", "상표", "금지", "지재권", "침해", "판매불가", "KC", "오매칭")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _get(store: str) -> Dict:
    from src.db import image_translate_queue_pg as st
    return dict(st.state_get(KEY.format(store)) or {})


def _update(store: str, fn) -> Dict:
    from src.db import image_translate_queue_pg as st
    upd = getattr(st, "state_update", None)
    if callable(upd):
        out = {}

        def _wrap(cur):
            new = fn(dict(cur or {}))
            out.update(new)
            return new
        upd(KEY.format(store), _wrap)
        return out
    new = fn(_get(store))
    st.state_set(KEY.format(store), new)
    return new


def norm_code(s) -> str:
    """판매자 관리 코드 정규화 — 오라클 미러는 `CP-<sid>`(nv_winners) 또는 `CP<sid>`(nv_mirror, 하이픈 없음) · 등록 체인은 품번(SKU)."""
    t = str(s or "").strip()
    m = re.match(r"^CP-?(\d{5,15})$", t, re.I)
    if m:
        return "CP-" + m.group(1)
    if re.match(r"^CP-?\d", t, re.I):                                # 미러 꼴인데 번호가 짧다 — 미러로도 품번으로도 안 친다
        return ""
    return t if _SKU.match(t) else ""


def clean_row(raw) -> Optional[Dict]:
    """받은 한 줄 → 허용 칸만. 잇는 번호(채널 번호 · 원상품 번호 · 판매자 관리 코드) 하나도 없으면 None(버림)."""
    if not isinstance(raw, dict):
        return None
    out: Dict = {}
    for k in ("channel_no", "origin_no"):
        v = str(raw.get(k) or "").strip()
        if _NO.match(v):
            out[k] = v
    code = norm_code(raw.get("code") or raw.get("cp") or raw.get("seller_code") or "")
    if not code and _NO.match(str(raw.get("sid") or "").strip()):
        code = "CP-" + str(raw.get("sid")).strip()
    if code:
        out["code"] = code
    if not any(k in out for k in ("channel_no", "origin_no", "code")):
        return None
    try:
        c = Decimal(str(raw.get("cost") if raw.get("cost") is not None else "").replace(",", "").strip())
        cur = str(raw.get("currency") or "").strip().upper()
        if c > 0 and _CUR.match(cur):
            out["cost"], out["currency"] = float(c), cur
    except (InvalidOperation, ValueError):
        pass
    url = str(raw.get("url") or raw.get("source_url") or "").strip()
    if url.startswith("http") and len(url) <= 1000 and " " not in url:
        out["url"] = url
    for k, n in (("updated", 32), ("vault_reason", 80), ("vault_job", 60)):
        v = str(raw.get(k) or "").strip()
        if v:
            out[k] = v[:n]
    try:
        n = int(raw.get("cp_sold") or 0)
        if n > 0:
            out["cp_sold"] = min(n, 100000)
    except (TypeError, ValueError):
        pass
    if not any(k in out for k in ("cost", "url", "vault_reason", "cp_sold")):     # 번호만 있고 쓸 게 없는 줄
        return None
    return out


def _key(r: Dict) -> str:
    for k, pre in (("channel_no", "ch:"), ("origin_no", "or:"), ("code", "cd:")):
        if r.get(k):
            return pre + str(r[k])
    return ""


def load_part(store: str, part: int, parts: int, src: str, rows: List) -> Dict:
    """장부 조각 하나를 합친다 — 같은 출처의 이전 줄은 새로 받은 조각으로 바뀐다(조각 1이 오면 그 출처 줄을 먼저 비움).
    「오너 입력」 줄은 건드리지 않는다."""
    from src.seller_console import smartstore_routing as R
    if store not in R.STORES:
        return {"ok": False, "why": "그런 스토어가 없어요"}
    try:
        part, parts = int(part), int(parts)
    except (TypeError, ValueError):
        return {"ok": False, "why": "조각 번호 꼴이 아니에요"}
    src_ko = SRC_KO.get(str(src or ""), str(src or "볼트 장부")[:40])
    if src_ko == OWNER_SRC:
        return {"ok": False, "why": "「오너 입력」은 화면에서만 넣어요"}
    got = [x for x in (clean_row(r) for r in (rows or [])[:MAX_ROWS_PER_PART]) if x]
    for x in got:
        x["src"] = src_ko
    dropped = len(rows or []) - len(got)

    def _fn(cur):
        idx = {k: dict(v) for k, v in (cur.get("rows") or {}).items() if isinstance(v, dict)}
        if part <= 1:                                                  # 조각 1 = 그 출처를 새로 받는다(다른 출처·오너 입력은 그대로)
            for k in list(idx):
                idx[k].pop(src_ko, None)
                if not idx[k]:
                    del idx[k]
        for x in got:
            idx.setdefault(_key(x), {})[src_ko] = x
        srcs = dict(cur.get("sources") or {})
        srcs[src_ko] = {"at": _now(), "parts_seen": sorted(set((srcs.get(src_ko) or {}).get("parts_seen", []) + [part]))
                        if part > 1 else [part], "parts": parts}
        return {"store": store, "at": _now(), "rows": idx, "sources": srcs}
    _update(store, _fn)
    logger.info("[재개 장부] %s %s 조각 %d/%d — %d줄 받음 · %d줄 버림", store, src_ko, part, parts, len(got), dropped)
    return {"ok": True, "store": store, "src": src_ko, "part": part, "parts": parts, "kept": len(got), "dropped": dropped}


def set_owner_cost(store: str, channel_no: str, cost, currency: str, url: str = "") -> Dict:
    """오너가 화면에서 넣은 원가 — 출처 「오너 입력」 · 그 줄만."""
    row = clean_row({"channel_no": channel_no, "cost": cost, "currency": currency, "url": url, "updated": _now()[:10]})
    if not row or "cost" not in row or "channel_no" not in row:
        return {"ok": False, "error": "원가(0보다 큰 숫자)와 통화(KRW·USD·JPY·CNY 같은 세 글자)를 넣어 주세요."}
    row["src"] = OWNER_SRC

    def _fn(cur):
        idx = {k: dict(v) for k, v in (cur.get("rows") or {}).items() if isinstance(v, dict)}
        idx.setdefault(_key(row), {})[OWNER_SRC] = row
        return dict(cur, store=store, rows=idx, at=cur.get("at") or _now())
    _update(store, _fn)
    return {"ok": True, "row": row}


def index(store: str) -> Dict[str, Dict[str, Dict]]:
    """잇는 번호(`ch:`·`or:`·`cd:`) → {출처: 줄}."""
    return dict(_get(store).get("rows") or {})


def find(idx: Dict[str, Dict], row: Dict) -> Optional[Dict]:
    """판매중지 한 줄 → 장부 줄. 「오너 입력」이 먼저, 그다음 채널 번호 → 원상품 번호 → 판매자 관리 코드 순.
    여러 장부가 같은 상품을 말하면 원가 있는 줄을 먼저 쓴다."""
    if not idx:
        return None
    keys = ["ch:" + str(row.get("channel_no") or ""), "or:" + str(row.get("origin_no") or "")]
    code = norm_code(row.get("seller_code"))
    if code:
        keys.append("cd:" + code)
    hits = [r for k in keys for r in (idx.get(k) or {}).values() if isinstance(r, dict)]
    if not hits:
        return None
    hits.sort(key=lambda v: (v.get("src") != OWNER_SRC, not v.get("cost")))
    best = dict(hits[0])
    for h in hits[1:]:                                              # 원가 줄에 없는 칸(주소·볼트 사유·쿠팡 판매)은 다른 장부에서 채운다
        for k in ("url", "vault_reason", "vault_job", "cp_sold"):
            if not best.get(k) and h.get(k):
                best[k] = h[k]
    return best


def hard_vault_reason(entry: Optional[Dict]) -> str:
    v = str((entry or {}).get("vault_reason") or "")
    return v if any(w in v for w in _HARD_VAULT) else ""


def summary(store: str) -> Dict:
    cur = _get(store)
    rows = cur.get("rows") or {}
    by: Dict[str, int] = {}
    for per in rows.values():
        for src in (per or {}):
            by[src] = by.get(src, 0) + 1
    return {"at": cur.get("at"), "rows": len(rows),
            "with_cost": sum(1 for per in rows.values() if any((v or {}).get("cost") for v in (per or {}).values())),
            "by_src": by, "sources": cur.get("sources") or {}}
