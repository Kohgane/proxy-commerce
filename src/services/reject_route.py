"""순찰 137(오너 2026-10-27 22:20 「4번은 사유를 상세하게 끌어오게 그래서 확실하게 파악해서 조치를 취할수있게 세팅하고 … 바로바로 가라」)
— 마켓 반려 사유 **전문** 수집 + 유형별 **자동 조치** 라우팅.

무엇을 하나:
  collect  쿠팡 `histories` 전 이력(시각·상태·comment 전문 — 500자 자르기 없음)을 `extra.review_detail[market]`에 적는다.
           네이버는 API가 사유를 주지 않는다(statusType만) → 그 사실을 그대로 적고 판매자센터 길을 남긴다(지어내지 않는다).
  route    `reject_watch.classify_rejection`(기존 표준 — 새 분류 발명 0) → 유형별 조치:
             saved_pending            → 승인 재요청 PUT 한 방(자동)
             image_spec               → 대표 자동 교체(`auto_rep_pick`) + 사진 묶음 재구성 → 수정 PUT(조회 원문 위에) → 승인 재요청(자동)
             apple_category(android)  → 승인 재요청(자동)
             option_unit·option_value → 사전검증 줄에 다시 올린다(글자 자동 수정 `reject_autofix`가 그 길에 있다) + 보고
             trademark·apple(iPhone)·unknown → 자동 조치 0 — 사유 전문 그대로 보고(오너 확인)
  반려 1건(사유 서명 `sig`)당 자동 조치 **1회** — 같은 서명으로 다시 반려되면 멈추고 보고한다(무한 왕복 금지).

되돌리기: 승인 재요청·수정 PUT은 쿠팡 재심사를 다시 거친다(지우지 않는다). 자동 조치 기록은 `review_detail[market].routed`.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

TIMELINE_LIMIT = 50
COMMENT_MAX = 4000                      # 전문 — 쿠팡 comment는 보통 수백 자
AUTO_KINDS = ("saved_pending", "image_spec", "apple_category")
SEMI_KINDS = ("option_unit", "option_value")
OWNER_KINDS = ("trademark", "unknown")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sig(market: str, comment: str, status_raw: str) -> str:
    return hashlib.sha1(f"{market}|{status_raw}|{comment}".encode("utf-8")).hexdigest()[:12]


def _ex(item: Dict) -> Dict:
    try:
        return json.loads(item.get("extra_json") or "{}") or {}
    except Exception:                                            # noqa: BLE001
        return {}


def _title(ex: Dict, item: Dict) -> str:
    return str(ex.get("title_ko") or ex.get("coupang_name") or item.get("title") or "")


# ── 수집 ──────────────────────────────────────────────────────────────────────

def collect_coupang(up, sid: str) -> Dict:
    """쿠팡 이력 전문 → `{status_raw, comment, timeline, kind, …}`. 조회 실패는 `error`로 그대로."""
    from src.pipeline import reject_watch as RW
    hist = up.get_status_histories(sid)
    if not isinstance(hist, dict) or hist.get("error"):
        return {"error": str((hist or {}).get("error") if isinstance(hist, dict) else hist)[:300]}
    tl = RW.timeline(hist, limit=TIMELINE_LIMIT)
    comment = str(RW.latest_rejection_comment(hist) or "")[:COMMENT_MAX]
    status_raw = str(tl[-1]["status"] if tl else "")
    return {"status_raw": status_raw, "comment": comment, "timeline": tl, "wing_state": RW.wing_state(hist)}


def collect_naver(row: Dict) -> Dict:
    """네이버 커머스 API는 승인거부 사유를 내려주지 않는다 — statusType만. 지어내지 않고 그 사실을 적는다."""
    return {"status_raw": str(row.get("status_raw") or ""), "comment": "",
            "timeline": [], "api_reason": "네이버 커머스 API는 승인거부 사유를 주지 않아요 — 판매자센터 › 상품관리 › 승인거부 상품에서 사유 확인",
            "link": str(row.get("link") or "")}


# ── 조치 ──────────────────────────────────────────────────────────────────────

def _resubmit_images(item_id: str, uid: str, ex: Dict, up, sid: str) -> Dict:
    """image_spec — 대표 자동 교체 → 사진 묶음 재구성 → **조회 원문 위에** images만 바꿔 수정 PUT → 승인 재요청."""
    from src.seller_console import collect_history_store as store
    from src.services import coupang_image_check as CIC
    from src.services import image_translate_store as ITS
    pick = CIC.auto_rep_pick(ex, by="reject_route")
    if pick.get("changed"):
        store.merge_extra(item_id, lambda f: f.update(rep_image=ex.get("rep_image"), rep_auto_pick=ex.get("rep_auto_pick")),
                          seller_ids={uid} if uid else None)
    imgs = ITS.effective_images(ex, item_id=item_id, originals=list(ex.get("images") or []))
    rb = up.rebuild_images_for_resubmit(imgs)
    if not rb.get("ok"):
        return {"applied": False, "action": "resubmit_images", "rep_pick": pick,
                "reason": f"교체할 사진이 없어요 — {rb.get('reason') or ''}(탈락 {len(rb.get('dropped') or [])})"[:300]}
    live = up.get_product(sid)
    if not isinstance(live, dict) or live.get("error"):
        return {"applied": False, "action": "resubmit_images", "rep_pick": pick,
                "reason": f"조회 원문 못 읽음 — {str((live or {}).get('error') if isinstance(live, dict) else live)[:200]}"}
    body = dict(live)
    body["items"] = [dict(it, images=rb["images"]) if isinstance(it, dict) else it for it in (live.get("items") or [])]
    mod = up.modify_product(body)
    if not mod.get("success"):
        return {"applied": False, "action": "resubmit_images", "rep_pick": pick, "stage": "modify",
                "reason": str(mod.get("error") or "")[:300], "body": str(mod.get("body") or "")[:500]}
    appr = up.request_approval(sid)
    return {"applied": bool(appr.get("success")), "action": "resubmit_images", "rep_pick": pick,
            "stage": "approval", "images_sent": len(rb["images"]),
            **({} if appr.get("success") else {"reason": str(appr.get("error") or "")[:300]})}


def route(item_id: str, uid: str, ex: Dict, market: str, detail: Dict, *, up=None, enqueue: Callable = None) -> Dict:
    """유형 → 조치. 반환 `{kind, kind_ko, rx_ko, applied, action?, reason?, needs_owner}`. 같은 서명 재반려는 멈춘다."""
    from src.pipeline import reject_watch as RW
    cls = RW.classify_rejection(detail.get("comment") or "", title=_title(ex, {}))
    kind = cls["kind"]
    base = {"kind": kind, "kind_ko": cls["kind_ko"], "rx_ko": cls["prescription_ko"], "sig": detail.get("sig") or "",
            "comment": str(detail.get("comment") or "")[:COMMENT_MAX], "applied": False, "needs_owner": False}
    prev = ((ex.get("review_detail") or {}).get(market) or {}).get("routed") or {}
    if prev.get("sig") and prev.get("sig") == base["sig"]:
        return {**base, "needs_owner": True,
                "reason": f"같은 사유로 다시 반려 — 자동 조치는 1회({prev.get('action') or prev.get('kind')} · {str(prev.get('at') or '')[:16]}) 끝, 오너 확인"}
    if not market.startswith("coupang"):
        return {**base, "needs_owner": True, "reason": detail.get("api_reason") or "자동 조치는 쿠팡만"}
    sid = str(detail.get("sid") or "")
    if kind == "saved_pending" or (kind == "apple_category" and cls.get("apple_target") == "android"):
        r = up.request_approval(sid)
        return {**base, "applied": bool(r.get("success")), "action": "request_approval",
                **({} if r.get("success") else {"reason": str(r.get("error") or "")[:300]})}
    if kind == "image_spec":
        return {**base, **_resubmit_images(item_id, uid, ex, up, sid)}
    if kind in SEMI_KINDS:
        q = bool(enqueue and enqueue({"op": "prevalidate", "item_id": item_id, "markets": [market], "why": f"반려 {cls['kind_ko']} — 글자 자동 수정 뒤 재등록 판단"}))
        return {**base, "action": "prevalidate_queued", "applied": q, "needs_owner": not q,
                "reason": "옵션 값·단위는 사전검증의 글자 자동 수정(reject_autofix)로 — 통과하면 재등록 줄로 보고"}
    return {**base, "needs_owner": True,
            "reason": {"trademark": "상표권(담당자 검토) — 삭제·브랜드 증빙은 오너 결정(되돌릴 수 없음)",
                       "apple_category": "iPhone·애플 대상 — 사전승인 보류",
                       "unknown": "사유 문구가 분류표에 없음 — 전문 그대로 보고"}.get(kind, "자동 조치 없음")}


# ── 입구(원샷 op `reject_route`) ─────────────────────────────────────────────────

def run(item_id: str, market: str, *, make_up: Callable = None, enqueue: Callable = None, now_row: Optional[Dict] = None) -> Dict:
    """한 상품·한 마켓: 사유 전문 수집 → `extra.review_detail[market]` 저장 → 자동 조치 → 기록. 읽기 실패는 그대로."""
    from src.seller_console import collect_history_store as store
    from src.services import coupang_detail_refresh as CDR
    from src.services import ocr_compare_diag as D
    item, uid = D._item(item_id)
    if not item:
        return {"ok": False, "why": "상품을 찾지 못했어요"}
    item_id = str(item.get("id") or item_id)
    ex = _ex(item)
    make_up = make_up or CDR._uploader
    up, sid = None, ""
    if market.startswith("coupang"):
        ups = [u for u in CDR.coupang_uploads(ex) if u["market"] == market]
        if not ups:
            return {"ok": False, "why": f"쿠팡 등록 기록 없음({market})"}
        sid = ups[-1]["sid"]
        try:
            up = make_up(ups[-1]["account"])
        except Exception as exc:                                 # noqa: BLE001
            return {"ok": False, "why": f"쿠팡 계정 준비 실패 — {type(exc).__name__}: {str(exc)[:160]}"}
        detail = collect_coupang(up, sid)
    else:
        detail = collect_naver(now_row or {})
    if detail.get("error"):
        return {"ok": False, "market": market, "why": f"이력 조회 실패 — {detail['error']}"}
    detail.update(sid=sid, at=_now(), sig=_sig(market, detail.get("comment") or "", detail.get("status_raw") or ""))
    routed = route(item_id, uid, ex, market, detail, up=up, enqueue=enqueue)
    rec = {k: detail.get(k) for k in ("at", "sid", "status_raw", "comment", "timeline", "wing_state", "api_reason", "link", "sig")}
    rec["kind"], rec["kind_ko"], rec["rx_ko"] = routed["kind"], routed["kind_ko"], routed["rx_ko"]
    prev_routed = ((ex.get("review_detail") or {}).get(market) or {}).get("routed")
    if routed.get("applied") or (routed.get("action") and not routed.get("needs_owner")):
        rec["routed"] = {"sig": detail["sig"], "kind": routed["kind"], "action": routed.get("action"), "at": _now(),
                         "applied": bool(routed.get("applied"))}
    elif prev_routed:
        rec["routed"] = prev_routed

    def _apply(fresh: Dict) -> None:
        rd = dict(fresh.get("review_detail") or {})
        rd[market] = rec
        fresh["review_detail"] = rd
    saved = store.merge_extra(item_id, _apply, seller_ids={uid} if uid else None)
    return {"ok": True, "market": market, "sid": sid, "saved": bool(saved), "status_raw": detail.get("status_raw"),
            "kind": routed["kind"], "kind_ko": routed["kind_ko"], "rx_ko": routed["rx_ko"],
            "applied": bool(routed.get("applied")), "action": routed.get("action") or "",
            "needs_owner": bool(routed.get("needs_owner")), "reason": str(routed.get("reason") or "")[:400],
            "comment": str(detail.get("comment") or "")[:COMMENT_MAX], "timeline_n": len(detail.get("timeline") or []),
            "rep_pick": routed.get("rep_pick")}
