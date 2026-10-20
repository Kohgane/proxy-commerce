"""Y13-G 3(오너 2026-10-20 「가라」) — 이미 올라간 상품의 **상품명·카테고리**를 마켓마다 한 번에 고친다(재심사 1회).

피샹리(회전 라운지 1인 소파)가 「소파>빈백」·「피샹리 가정 소파 의자…」로 나갔다(懒人沙发→빈백 치환 · 가게명). 고치는 길:
- 쿠팡: `GET seller-products/{sid}` → `live_fix_plan(name=…)`(상품명 3칸) + `displayCategoryCode` → `PUT`(승인필요 = 재심사).
- 네이버: `GET origin-products/{no}` → `leafCategoryId`·`name` + 채널 상품명 → `PUT`(조회한 몸통 위에 바꿀 칸만 — `_modify_origin`).
  새 카테고리가 KC 대상이면 KC 특례(해외구매대행)를 같이 싣는다(`naver_kc` — 등록과 같은 함수).
가격·재고·옵션·사진은 손대지 않는다. 결과(전·후·응답 원문)는 등록 기록 `uploaded[].relist_fix`에 남긴다.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)

NAVER_PREFIX = "[해외직구] "


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def coupang(rec: Dict, name: str, category: str, make_up=None) -> Dict:
    from src.services.coupang_detail_refresh import _uploader
    up = (make_up or _uploader)(rec.get("account") or "")
    live = up.get_product(rec["product_id"])
    if not isinstance(live, dict) or "error" in live:
        return {"ok": False, "error": f"쿠팡 상품 조회 실패 — {(live or {}).get('error') if isinstance(live, dict) else live}"}
    plan = up.live_fix_plan(live, name=name)
    body = plan["body"]
    before_cat = str(body.get("displayCategoryCode") or "")
    if category and before_cat != str(category):
        body["displayCategoryCode"] = int(category)
        plan["changes"].append({"field": "카테고리", "before": before_cat, "after": str(category)})
    if not plan["changes"]:
        return {"ok": True, "unchanged": True}
    body["requested"] = True
    res = up.modify_product(body)
    return {"ok": bool(res.get("success")), "changes": plan["changes"], "error": str(res.get("error") or "")[:600],
            "market_status": res.get("market_status"), "body": str(res.get("body") or "")[:2000]}


def naver(rec: Dict, name: str, category: str, make_up=None) -> Dict:
    from src.uploaders import naver_kc as _kc
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    up = (make_up or (lambda a: NaverSmartStoreUploader(account=a or None)))(rec.get("account") or "")
    full = (NAVER_PREFIX + name)[:100] if name else ""
    box: Dict = {}

    def _mut(op):
        change = {}
        if full and full != op.get("name"):
            change["name"] = full
        if category and str(op.get("leafCategoryId") or "") != str(category):
            change["leafCategoryId"] = str(category)
            if _kc.kc_required(str(category), up):
                da = dict(op.get("detailAttribute") or {})
                da["certificationTargetExcludeContent"] = _kc.exemption_for({})
                change["detailAttribute"] = da
        box.update(before_name=op.get("name"), before_category=str(op.get("leafCategoryId") or ""), change=sorted(change))
        return change or None

    out = up._modify_origin(rec["product_id"], _mut,
                            channel_mutate=(lambda ch: {"channelProductName": full}) if full else None)
    out.pop("before", None)
    return {"ok": bool(out.get("success")), "unchanged": bool(out.get("unchanged")), **box,
            "error": str(out.get("error") or "")[:600], "status_type": out.get("status_type"),
            "raw": str(out.get("raw") or "")[:2000]}


def run(item: Dict, markets: List[str], *, name: str, coupang_category: str = "", naver_category: str = "",
        save=None) -> Dict:
    """마켓마다 한 번씩 — `{market: 결과}`. 결과는 `save(fn)`으로 등록 기록에 남긴다."""
    from src.seller_console import listing_status as MS
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:                                            # noqa: BLE001
        return {"ok": False, "why": "상품 기록을 읽지 못했어요"}
    out: Dict[str, Dict] = {}
    for rec in MS.records(ex):
        m = rec["market"]
        if m not in markets:
            continue
        try:
            if m.startswith("coupang"):
                r = coupang(rec, name, coupang_category)
            elif m.startswith("smartstore"):
                r = naver(rec, name, naver_category)
            else:
                r = {"ok": False, "error": "이 마켓은 이 작업이 고치지 않아요"}
        except Exception as exc:                                 # noqa: BLE001 — 한 마켓 실패가 다른 마켓을 막지 않는다
            r = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        r["at"] = _now()
        out[m] = r
        logger.info("[등록본 고치기] item=%s market=%s ok=%s err=%s", str(item.get("id") or "")[:8], m, r.get("ok"),
                    str(r.get("error") or "")[:160])
    if save and out:
        def _fn(fresh):
            # 앞으로의 등록(다른 계정·다시 등록)도 같은 이름·카테고리로 — 오너가 정한 값(수집 원문 `title`은 그대로)
            fresh["title_ko"] = name
            fresh["coupang_name"] = name
            if naver_category:
                fresh["naver_category_id"] = str(naver_category)
            if coupang_category:
                fresh["coupang_category_id"] = str(coupang_category)     # Y13-H: 빠져서 고가네 새 등록이 77903으로 갔다
            for u in fresh.get("uploaded") or []:
                if isinstance(u, dict) and u.get("market") in out:
                    u["relist_fix"] = {**out[u["market"]], "name": name, "coupang_category": coupang_category,
                                       "naver_category": naver_category}
            return True
        save(_fn)
    missing = [m for m in markets if m not in out]
    return {"ok": bool(out) and all(r.get("ok") for r in out.values()) and not missing, "markets": out,
            "why": ("등록 기록이 없는 마켓: " + ", ".join(missing)) if missing else ""}
