"""Z3 자동 경로(오너 2026-10-05) — 폰 전용 유저가 담은 타오바오 초안을 **서버가 mtop으로 채운다**.

흐름: 공유 초안 생성 → (켜져 있으면) 백그라운드 한 건 → `taobao_mtop.fetch`(x5 핸드셰이크 → 토큰 왕복 → getdetail·getdesc)
  → 성공: 확장 보강과 **같은 병합**(`extension_api.apply_enrich`) — 사진·옵션·SKU·가격·상세 이미지
  → 실패(punish/captcha/RGV587·프록시 미설정 등): 그 건은 **(c) 수동 경로** — `extra.auto_enrich = {state: manual, reason}`,
    폰 카드가 「자동 수집 실패 — 사유」 + 「사진 추가」·「옵션 직접 입력」을 보인다.

켜기: `TAOBAO_MTOP_AUTO=1`(기본 끔 — 진단 화면 실측으로 경로가 확정되기 전엔 아무것도 안 부른다).
경로: `TAOBAO_MTOP_ROUTE` = direct | relay | proxy(기본 relay). proxy는 `TAOBAO_PROXY_URL`(한국 주거 회전형)이 있어야 한다.
한 번에 한 건(잠금) — mtop 호출 간격 2~3초는 `taobao_mtop`이 지킨다.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()


def enabled() -> bool:
    return os.getenv("TAOBAO_MTOP_AUTO", "0").strip() == "1"


def route() -> str:
    r = os.getenv("TAOBAO_MTOP_ROUTE", "relay").strip().lower()
    return r if r in ("direct", "relay", "proxy") else "relay"


def _mark(item_id: str, user_id: str, rec: dict) -> None:
    from src.seller_console import collect_history_store as store
    row = store.get(item_id, seller_ids={user_id})
    if not row:
        return
    try:
        ex = json.loads(row.get("extra_json") or "{}") or {}
    except Exception:
        ex = {}
    ex["auto_enrich"] = rec
    store.update(item_id, seller_ids={user_id}, extra_json=json.dumps(ex, ensure_ascii=False))


def run(user_id: str, item_id: str, *, via: str = "") -> dict:
    """한 건 동기 실행 → 기록한 `auto_enrich` dict."""
    from src.collectors import taobao_mtop as T
    from src.seller_console import collect_history_store as store
    via = via or route()
    now = datetime.now(timezone.utc).isoformat()
    row = store.get(item_id, seller_ids={user_id})
    if not row:
        return {"state": "skipped", "reason": "상품이 없어요"}
    try:
        ex = json.loads(row.get("extra_json") or "{}") or {}
    except Exception:
        ex = {}
    url = str(row.get("url") or ex.get("url") or "")
    iid = str(ex.get("item_id_taobao") or ex.get("site_item_id") or "")
    if not iid:
        try:
            s = T.session_for(via) if via != "relay" else T._session()
            iid, _how = T.item_id_from(url, s)
        except T.NoProxy:
            iid = ""
    if not iid:
        rec = {"state": "manual", "reason": "상품번호를 못 찾았어요(단축 링크를 펴지 못함)", "route": via, "at": now}
        _mark(item_id, user_id, rec)
        return rec
    with _LOCK:
        res = T.fetch(iid, via)
    if res["state"] == "ok":
        from src.api.extension_api import apply_enrich
        body, _code = apply_enrich(item_id, {user_id}, user_id, res["payload"])
        rec = {"state": "done" if body.get("ok") else "manual", "route": via, "at": now,
               "reason": "" if body.get("ok") else str(body.get("error") or "병합 실패"),
               "counts": {"images": len(res["payload"]["images"]), "skus": len(res["payload"]["skus"]),
                          "detail_images": len(res["payload"]["detail_images"])}}
    else:
        rec = {"state": "manual", "reason": res["reason"], "route": via, "at": now}
    _mark(item_id, user_id, rec)
    logger.info("[Z3 자동] item=%s 상품=%s 경로=%s → %s %s", item_id, iid, via, rec["state"], rec.get("reason", ""))
    return rec


def kick(user_id: str, item_id: str) -> bool:
    """켜져 있으면 백그라운드로 한 건(응답은 기다리지 않는다). 켜졌는지 돌려준다."""
    if not (enabled() and user_id and item_id):
        return False
    threading.Thread(target=_safe_run, args=(user_id, item_id), daemon=True).start()
    return True


def _safe_run(user_id: str, item_id: str) -> None:
    try:
        run(user_id, item_id)
    except Exception as exc:                                    # noqa: BLE001 — 백그라운드는 죽지 않는다
        logger.warning("[Z3 자동] item=%s 실패: %s", item_id, exc)
        try:
            _mark(item_id, user_id, {"state": "manual", "reason": f"자동 수집 오류 {type(exc).__name__}",
                                     "route": route(), "at": datetime.now(timezone.utc).isoformat()})
        except Exception:
            pass
