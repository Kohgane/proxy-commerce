"""Y14-f(오너 10-20 순찰 6) — 쿠팡 카테고리를 바꾸려면 **새로 등록 → 새 상품 승인 → 옛 상품 판매중지** 순서로.

근거(실측 · 쿠팡 공식 문서는 이 환경에서 열리지 않음): 볼트 「쿠팡 API 지뢰」·「런북 승인완료 상품 수정」(2026-08-22~24) —
`displayCategoryCode`는 partial·전체 PUT 모두 미반영(승인완료·임시저장 두 상태, 토라스 아우터 54건 전건 그대로) ·
10-20 피샹리 2계정 PUT 두 번(10:40 · 19:40) SUCCESS인데 조회 원문 77903 그대로.

세 단계 — 일회성 줄 `coupang_relist` `{step, markets}`, 단계마다 오너가 부른다:
  plan      읽기만 — 옛 상품번호·지금 카테고리·바꿀 카테고리(`coupang_category_id`)·판매중지할 옵션 번호·옛 상품 판매 상태
  register  옛 번호를 먼저 `extra.coupang_relist[market]`에 적고, 화면 「마켓 등록」과 같은 입구로 **새로** 등록(중복 확인만 이 단계가 넘김)
  stop_old  새 상품이 **승인완료**이고 카테고리가 바꿀 값과 같을 때만 옛 상품 옵션마다 판매중지(`sales/stop`) → `onSale`로 다시 확인.
            새 상품이 아직이면 아무것도 안 하고 이유를 적는다(먼저 중지 금지). 지우지 않는다 — 되돌리기는 `sales/resume`.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

APPROVED = ("승인완료", "APPROVED", "APPROVE")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ex(item: Dict) -> Dict:
    try:
        return json.loads(item.get("extra_json") or "{}") or {}
    except Exception:                                            # noqa: BLE001
        return {}


def _uploader(account: str):
    from src.services.coupang_detail_refresh import _uploader as _u
    return _u(account)


def _vids(live: Dict) -> List[str]:
    return [str(it.get("vendorItemId")) for it in (live.get("items") or []) if str(it.get("vendorItemId") or "").isdigit()]


def _status(live: Dict) -> str:
    return str(live.get("statusName") or live.get("status") or "")


def _records(ex: Dict, market: str) -> List[Dict]:
    return [u for u in (ex.get("uploaded") or []) if isinstance(u, dict) and u.get("market") == market]


def plan(item: Dict, markets: List[str], make_up: Callable = None) -> Dict:
    """읽기만 — 마켓마다 `{old_sid, category_now, category_to, vids, old_status, ready, why}`."""
    make_up = make_up or _uploader
    ex = _ex(item)
    target = str(ex.get("coupang_category_id") or "").strip()
    rel = ex.get("coupang_relist") if isinstance(ex.get("coupang_relist"), dict) else {}
    out: Dict[str, Dict] = {}
    for m in markets:
        if not m.startswith("coupang"):
            out[m] = {"ready": False, "why": "쿠팡 마켓만"}
            continue
        recs = _records(ex, m)
        old_sid = str((rel.get(m) or {}).get("old_sid") or (recs[0].get("product_id") if recs else "") or "")
        row = {"old_sid": old_sid, "category_to": target, "ready": False, "why": ""}
        if not old_sid:
            row["why"] = "이 마켓 등록 기록이 없어요"
        elif not target.isdigit():
            row["why"] = "바꿀 쿠팡 카테고리(상품 기록 coupang_category_id)가 없어요"
        else:
            up = make_up(m.partition(":")[2])
            live = up.get_product(old_sid)
            if "error" in live:
                row["why"] = f"옛 상품 조회 실패 — {live['error']}"
            else:
                row.update(category_now=str(live.get("displayCategoryCode") or ""), old_status=_status(live), vids=_vids(live))
                if row["category_now"] == target:
                    row["why"] = "이미 바꿀 카테고리예요 — 다시 등록할 일 없음"
                else:
                    row["ready"] = True
        out[m] = row
    return {"ok": all(r.get("ready") for r in out.values()) and bool(out), "markets": out}


def register(item: Dict, markets: List[str], *, save: Callable, register_fn: Callable = None,
             make_up: Callable = None) -> Dict:
    """옛 번호를 먼저 적고 새로 등록한다. `register_fn(item_id, markets)` = 화면 「마켓 등록」 입구(중복 확인만 넘김)."""
    p = plan(item, markets, make_up=make_up)
    go = [m for m, r in p["markets"].items() if r.get("ready")]
    if not go:
        return {"ok": False, "why": "새로 등록할 마켓이 없어요", "plan": p}
    olds = {m: p["markets"][m]["old_sid"] for m in go}

    def _mark(fresh):
        rel = fresh.setdefault("coupang_relist", {})
        for m in go:
            rel[m] = {"old_sid": olds[m], "category_to": p["markets"][m]["category_to"],
                      "old_vids": p["markets"][m].get("vids") or [], "state": "registering", "at": _now()}
        return True
    save(_mark)                                                  # 등록 전에 옛 번호를 남긴다 — 새 기록이 쌓여도 옛 것을 안다
    res = (register_fn or _register_dup_ok)(str(item.get("id") or ""), go)
    rows = {str(r.get("market")): r for r in (res.get("rows") or []) if isinstance(r, dict)}

    def _after(fresh):
        rel = fresh.setdefault("coupang_relist", {})
        for m in go:
            r = rows.get(m) or {}
            new_sid = str(r.get("external_product_id") or "")
            ok = r.get("success") is True and new_sid and new_sid != olds[m]
            rel[m] = {**(rel.get(m) or {}), "new_sid": new_sid if ok else "",
                      "state": "wait_approval" if ok else "register_failed",
                      "why": "" if ok else str(r.get("message") or res.get("why") or "등록 응답 없음")[:300], "at": _now()}
        return True
    save(_after)
    return {"ok": bool(res.get("ok")), "rows": list(rows.values()), "why": str(res.get("why") or "")}


def _register_dup_ok(item_id: str, markets: List[str]) -> Dict:
    from src.services import oneshot_ops as O
    return O.register(item_id, markets, confirm_duplicate=True)


def stop_old(item: Dict, markets: List[str], *, save: Callable, make_up: Callable = None) -> Dict:
    """새 상품 승인완료 + 카테고리 확인 뒤에만 옛 상품 옵션 판매중지."""
    make_up = make_up or _uploader
    ex = _ex(item)
    rel = ex.get("coupang_relist") if isinstance(ex.get("coupang_relist"), dict) else {}
    out: Dict[str, Dict] = {}
    for m in markets:
        r = dict(rel.get(m) or {})
        if not r.get("new_sid"):
            out[m] = {"stopped": 0, "why": "새 상품이 아직 없어요(register 먼저)"}
            continue
        up = make_up(m.partition(":")[2])
        new = up.get_product(r["new_sid"])
        if "error" in new:
            out[m] = {"stopped": 0, "why": f"새 상품 조회 실패 — {new['error']}"}
            continue
        st, cat = _status(new), str(new.get("displayCategoryCode") or "")
        if st not in APPROVED:
            out[m] = {"stopped": 0, "new_status": st, "why": f"새 상품이 아직 「{st or '모름'}」 — 승인완료 뒤에 옛 상품을 내려요"}
            continue
        if cat != str(r.get("category_to") or ""):
            out[m] = {"stopped": 0, "new_status": st, "new_category": cat,
                      "why": f"새 상품 카테고리가 {cat} — 바꿀 값 {r.get('category_to')}과 달라 옛 상품을 내리지 않아요"}
            continue
        vids = r.get("old_vids") or _vids(up.get_product(r["old_sid"]))
        done, left = [], []
        for vid in vids:
            s = up.stop_sale(vid)
            if s.get("ok") and up.on_sale(vid) is False:
                done.append(vid)
            else:
                left.append({"vid": vid, "why": s.get("error") or "중지 뒤에도 판매중으로 읽힘"})
        out[m] = {"stopped": len(done), "of": len(vids), "left": left, "new_status": st, "new_category": cat}
        r.update(state="done" if not left else "stop_partial", stopped=done, at=_now())
        rel[m] = r
    if any(v.get("stopped") for v in out.values()):
        def _fn(fresh):
            fresh.setdefault("coupang_relist", {}).update({k: v for k, v in rel.items() if k in out})
            return True
        save(_fn)
    return {"ok": bool(out) and all(v.get("stopped") and not v.get("left") for v in out.values()), "markets": out}
