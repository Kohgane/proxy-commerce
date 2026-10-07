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


def _onebound() -> bool:
    # ★ `src.collectors` 패키지를 import하지 않고 env만 본다 — 이 함수는 앱 부팅(`order_webhook` → startup_check)에서
    #   불린다. 패키지 `__init__`이 사이트 어댑터 전부를 import하고, 어댑터들은 import 시점에 ADAPTER_DRY_RUN을 굳힌다
    #   (#835 CI 실측: 부팅에서 끌려와 dry-run 어댑터 계약 4건이 실네트워크로 돎). 판정은 `taobao_provider.provider()`와 같다.
    return os.getenv("TAOBAO_DETAIL_PROVIDER", "mtop").strip().lower() == "onebound"


def enabled() -> bool:
    return os.getenv("TAOBAO_MTOP_AUTO", "0").strip() == "1" or _onebound()


def effective_route() -> str:
    """실제로 상세를 가져올 길 — onebound면 `onebound`, 아니면 mtop 경로(direct·relay·proxy)."""
    return "onebound" if _onebound() else route()


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


def _keep_provider(item_id: str, user_id: str, payload: dict) -> None:
    """공급자 전용 칸을 병합 **뒤에** 남긴다(공용 병합 `apply_enrich`는 그대로): 규격표는 기존 `detail_specs`가
    비었을 때만(Z5 무게·치수 재료) · 원산지·티몰·동영상·총재고·옵션값 사진·캐시 기준은 `provider_detail`에."""
    from src.seller_console import collect_history_store as store
    row = store.get(item_id, seller_ids={user_id})
    if not row:
        return
    try:
        ex = json.loads(row.get("extra_json") or "{}") or {}
    except Exception:
        ex = {}
    pv = dict(payload.get("provider") or {})
    if payload.get("detail_specs") and not ex.get("detail_specs"):
        ex["detail_specs"] = payload["detail_specs"]
    ex["provider_detail"] = {k: pv.get(k) for k in ("name", "price_cny", "original_price_cny", "origin_city", "is_tmall",
                                                   "video_url", "stock_total", "option_images", "cache", "data_update",
                                                   "price_asof", "parse_notes", "total_sold", "sales", "post_fee",
                                                   "express_fee", "ems_fee", "freight", "item_weight", "brand")}
    store.update(item_id, seller_ids={user_id}, extra_json=json.dumps(ex, ensure_ascii=False))


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


def run(user_id: str, item_id: str, *, via: str = "", src: str = "auto") -> dict:
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
        rec = {"state": "manual", "route": via, "at": now, "kind": "error",
               "reason": ("상품번호 해석 실패" if via == "onebound" else "상품번호를 못 찾았어요(단축 링크를 펴지 못함)")}
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
            from src.collectors.taobao_provider_onebound import as_source
            with as_source(src):                                # Z3-D: 나간 호출을 출처별로 센다
                res = P.fetch_detail(iid)
        else:
            res = T.fetch(iid, via)
    if res["state"] == "ok":
        from src.api.extension_api import apply_enrich
        payload = {k: v for k, v in res["payload"].items() if k != "provider"}
        body, _code = apply_enrich(item_id, {user_id}, user_id, payload)
        if body.get("ok") and res["payload"].get("provider"):
            _keep_provider(item_id, user_id, res["payload"])
            # M5 후속: 원본 동영상이 있으면 무음 mp4로(백그라운드 — 보강·등록을 막지 않는다)
            kick_video(user_id, item_id, str((res["payload"].get("provider") or {}).get("video_url") or ""))
        rec = {"state": "done" if body.get("ok") else "manual", "route": via, "at": now,
               "reason": "" if body.get("ok") else str(body.get("error") or "병합 실패"),
               "counts": {"images": len(res["payload"]["images"]), "skus": len(res["payload"]["skus"]),
                          "detail_images": len(res["payload"]["detail_images"])}}
    else:
        rec = {"state": "manual", "reason": res["reason"], "route": via, "at": now}
    rec["kind"] = res.get("kind") or ("ok" if res["state"] == "ok" else "error")
    if via == "onebound":                                       # Z3-B: 공급자 호출 크기·시간
        rec["provider_ms"], rec["provider_bytes"] = int(res.get("ms") or 0), int(res.get("bytes") or 0)
        rec["provider_reused"] = bool(res.get("reused"))
        pv = ((res.get("payload") or {}).get("provider") or {})
        if pv.get("price_asof"):
            rec["price_asof"] = pv["price_asof"]                # 캐시 응답이 하루 넘음 → 카드에 「가격 기준 …」
    if via == "proxy":                                          # Z3-P: 상품당 프록시 경유 바이트 · 쓴 session
        rec["proxy_bytes"], rec["session"] = int(res.get("bytes") or 0), res.get("session", "")
        logger.info("[Z3 프록시] item=%s 상품=%s session=%s 바이트=%d 결과=%s", item_id, iid, rec["session"],
                    rec["proxy_bytes"], rec["kind"])
    _mark(item_id, user_id, rec)
    if via == "onebound":                                       # Z3-C 이월: 하루 한도에 막히면 대기 → 한도 풀리면 자동
        try:
            from src.services import onebound_carry as _carry
            if rec["kind"] in _carry.CARRY_KINDS:
                _carry.add(user_id, item_id, url=url, share=str(ex.get("share_raw") or ""), kind=rec["kind"])
            else:
                _carry.remove(item_id, f"자동 수집 {rec['state']}")
        except Exception as exc:                                # noqa: BLE001 — 대기 실패가 수집 기록을 막지 않는다
            logger.warning("[이월 대기] 기록 실패: %s", exc)
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


def kick_video(user_id: str, item_id: str, source_url: str) -> bool:
    """M5 후속(오너 2026-10-07): 온바운드 `item.video.url` → 무음 mp4 → Cloudinary → `extra.video`(+`video_url`).
    `VIDEO_COLLECT=0`이면 끈다. 실패해도 사유만 남기고 등록은 그대로."""
    if not (source_url and user_id and item_id) or os.getenv("VIDEO_COLLECT", "1").strip() == "0":
        return False
    threading.Thread(target=_video_job, args=(user_id, item_id, source_url), daemon=True).start()
    return True


def _video_job(user_id: str, item_id: str, source_url: str) -> None:
    from src.seller_console import collect_history_store as store
    try:
        from src.media import video_silent
        rec = video_silent.process(source_url, label=f"video-{item_id}")
    except Exception as exc:                                    # noqa: BLE001 — 백그라운드는 죽지 않는다
        rec = {"state": "failed", "source_url": source_url, "why": f"{type(exc).__name__}: {str(exc)[:120]}",
               "at": datetime.now(timezone.utc).isoformat()}
    row = store.get(item_id, seller_ids={user_id})
    if not row:
        return
    try:
        ex = json.loads(row.get("extra_json") or "{}") or {}
    except Exception:
        ex = {}
    ex["video"] = rec
    if rec.get("state") == "done":
        ex["video_url"] = rec["url"]
    store.update(item_id, seller_ids={user_id}, extra_json=json.dumps(ex, ensure_ascii=False))
    logger.info("[동영상] item=%s → %s %s", item_id, rec.get("state"), rec.get("why") or rec.get("mode") or "")


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
