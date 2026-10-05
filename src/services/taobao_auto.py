"""Z3 자동 경로(오너 2026-10-05) — 폰 전용 유저가 담은 타오바오 초안을 **서버가 mtop으로 채운다**.

흐름: 공유 초안 생성 → (켜져 있으면) 백그라운드 한 건 → `taobao_mtop.fetch`(x5 핸드셰이크 → 토큰 왕복 → getdetail·getdesc)
  → 성공: 확장 보강과 **같은 병합**(`extension_api.apply_enrich`) — 사진·옵션·SKU·가격·상세 이미지
  → 실패(punish/captcha/RGV587·프록시 미설정 등): 그 건은 **(c) 수동 경로** — `extra.auto_enrich = {state: manual, reason}`,
    폰 카드가 「자동 수집 실패 — 사유」 + 「사진 추가」·「옵션 직접 입력」을 보인다.

켜기: `TAOBAO_MTOP_AUTO=1`(기본 끔 — 진단 화면 실측으로 경로가 확정되기 전엔 아무것도 안 부른다).
경로: `TAOBAO_MTOP_ROUTE` = direct | relay | proxy(기본 relay). proxy는 `TAOBAO_PROXY_URL`(한국 주거 회전형)이 있어야 한다.
한 번에 한 건(잠금) — mtop 호출 간격 2~3초는 `taobao_mtop`이 지킨다.

Z3-B: `TAOBAO_DETAIL_PROVIDER=onebound`면 상세를 외부 공급자(`taobao_provider`)로 — 이 설정만으로 자동 경로가 켜진다
(TAOBAO_MTOP_AUTO 불필요). 공급자가 실패하면 (c) 수동 — mtop을 다시 부르지 않는다. 집계 경로 이름은 `onebound`.
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
    if os.getenv("TAOBAO_MTOP_AUTO", "0").strip() == "1":
        return True
    from src.collectors import taobao_provider as P
    return P.provider() == "onebound"


def effective_route() -> str:
    """실제로 상세를 가져올 길 — onebound면 `onebound`, 아니면 mtop 경로(direct·relay·proxy)."""
    from src.collectors import taobao_provider as P
    return "onebound" if P.provider() == "onebound" else route()


def route() -> str:
    """`TAOBAO_MTOP_ROUTE` = direct | relay2(=relay) | proxy. 모르는 값이면 relay."""
    r = os.getenv("TAOBAO_MTOP_ROUTE", "relay").strip().lower()
    r = "relay" if r == "relay2" else r
    return r if r in ("direct", "relay", "proxy") else "relay"


def startup_check() -> str:
    """부팅 1줄 — 자동 경로가 proxy인데 TAOBAO_PROXY_URL이 비면 경고(조용한 폴백 없음: 그 건들은 「프록시 미설정」으로 실패 표기)."""
    if not enabled():
        return ""
    from src.collectors import taobao_mtop as T
    from src.collectors import taobao_provider as P
    if P.provider() == "onebound":
        return P.startup_check()
    if route() == "proxy" and not T.proxy_parts():
        msg = "Z3 자동 경로: TAOBAO_MTOP_ROUTE=proxy인데 TAOBAO_PROXY_URL이 비었어요 — relay2로 돌리지 않고 「프록시 미설정」으로 실패 표기합니다"
        logger.warning(msg)
        return msg
    msg = f"Z3 자동 경로: 켜짐 · 경로 {route()}" + (f" · {T.proxy_label()}" if route() == "proxy" else "")
    logger.info(msg)
    return msg


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
    via = via or effective_route()
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
            iid, _how = T.item_id_from(url, T.resolver_session("direct" if via == "onebound" else via))  # 단축 링크는 직결
        except T.NoProxy:
            iid = ""
    if not iid:
        rec = {"state": "manual", "reason": "상품번호를 못 찾았어요(단축 링크를 펴지 못함)", "route": via, "at": now, "kind": "error"}
        _mark(item_id, user_id, rec)
        try:
            from src.services import mtop_stats as _ms
            _ms.record(via, "error")
        except Exception:
            pass
        return rec
    with _LOCK:
        if via == "onebound":
            from src.collectors import taobao_provider as P
            res = P.fetch_detail(iid)
        else:
            res = T.fetch(iid, via)
    if res["state"] == "ok":
        from src.api.extension_api import apply_enrich
        payload = {k: v for k, v in res["payload"].items() if k != "parse_notes"}
        body, _code = apply_enrich(item_id, {user_id}, user_id, payload)
        rec = {"state": "done" if body.get("ok") else "manual", "route": via, "at": now,
               "reason": "" if body.get("ok") else str(body.get("error") or "병합 실패"),
               "counts": {"images": len(res["payload"]["images"]), "skus": len(res["payload"]["skus"]),
                          "detail_images": len(res["payload"]["detail_images"])}}
    else:
        rec = {"state": "manual", "reason": res["reason"], "route": via, "at": now}
    rec["kind"] = res.get("kind") or ("ok" if res["state"] == "ok" else "error")
    if via == "onebound":                                       # Z3-B: 공급자 호출 크기·시간
        rec["provider_ms"], rec["provider_bytes"] = int(res.get("ms") or 0), int(res.get("size") or 0)
    if via == "proxy":                                          # Z3-P: 상품당 프록시 경유 바이트 · 쓴 session
        rec["proxy_bytes"], rec["session"] = int(res.get("bytes") or 0), res.get("session", "")
        logger.info("[Z3 프록시] item=%s 상품=%s session=%s 바이트=%d 결과=%s", item_id, iid, rec["session"],
                    rec["proxy_bytes"], rec["kind"])
    _mark(item_id, user_id, rec)
    # Z3-C: 집계(경로·갈래) · 첫 10건 담은 시각 → 준비 완료 시각 · 첫 성공 응답 1건(픽스처 교체용)
    try:
        from src.services import mtop_stats as _ms
        _ms.record(via, rec["kind"], nbytes=int(res.get("bytes") or 0) if via == "proxy" else 0)
        _ms.note_item({"item_id": item_id, "collected_at": str(row.get("collected_at") or ""), "done_at": now,
                       "state": rec["state"], "kind": rec["kind"], "route": via, "reason": rec.get("reason", "")[:120]})
        if res["state"] == "ok" and res.get("raw") and via != "onebound":
            _ms.save_sample(res["raw"], item_id=iid, route=via)
    except Exception as exc:                                    # noqa: BLE001 — 집계 실패가 수집을 막지 않는다
        logger.warning("[Z3 집계] 기록 실패: %s", exc)
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
