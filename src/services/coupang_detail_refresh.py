"""Y11-Q(오너 2026-10-16 00:38) — 이미 쿠팡에 등록된 상품의 **상세(contents)를 다시 보낸다**(상품 수정 API).

계기: VRSUK 첫 등록(쿠팡 고가네 16415921785 · 우주대행 16415921921) 때 텐센트 텍스트 번역이 전부 실패해(RequestLimitExceeded·
InvalidParameterValue) 규격 51칸이 빠진 상세로 나갔다. 번역이 성공하면 그 상세로 등록본을 갱신한다.

- 새 상세 = 등록과 **같은 빌더**(`build_dispatch_payload` → `prepared_input` → `prepare_product` → `_build_contents`).
  나갈 상세에 번역 실패 칸이 남아 있으면(규격이 빠진다) 보내지 않고 「번역 대기」로 큐에 둔다.
- 몸통 = 쿠팡 조회 원문(`get_product`)에서 **items[].contents만** 바꾼 것(가격·재고·옵션·이미지는 그대로) — U1b와 같은 방식.
- 수정은 쿠팡 「승인필요」 API — 판매중 상품도 다시 심사. 검토 중이라 막히면 **그 응답 원문**을 기록하고
  「승인 후 자동 갱신」 큐(`app_state coupang_detail_refresh:queue`)에 넣는다. `/cron/coupang-detail-refresh`가 승인되면 다시 보낸다.
- 같은 상세(해시)를 이미 보냈으면 다시 보내지 않는다(쿠팡 재심사를 두 번 부르지 않게).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

QUEUE_KEY = "coupang_detail_refresh:queue"
MAX_TRIES = 48                      # 크론이 30분마다면 하루 — 그 뒤엔 큐에서 빼고 사유를 남긴다


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(contents) -> str:
    return hashlib.sha1(json.dumps(contents, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def coupang_uploads(ex: dict) -> List[dict]:
    """쿠팡 등록 기록 `[{market, account, sid}]`. 예전 기록(09월 · `product_id` 없이 `external_url`만)은 주소에서 번호를 읽는다 —
    Y14(10-21): SPORTLINK 쿠팡 16397045086(09-28)이 여기서만 빠져 조회가 「쿠팡 등록 기록이 없어요」였다(`listing_status.records`·
    화면 `_coupang_uploads`는 이미 주소에서 읽었다)."""
    import re
    out = []
    for u in (ex or {}).get("uploaded") or []:
        if not (isinstance(u, dict) and str(u.get("market") or "").startswith("coupang")):
            continue
        sid = str(u.get("product_id") or "").strip()
        if not sid:
            hit = re.search(r"/(?:vp/products|products)/(\d+)", str(u.get("external_url") or ""))
            sid = hit.group(1) if hit else ""
        if sid:
            out.append({"market": u["market"], "account": u.get("account") or u["market"].partition(":")[2], "sid": sid})
    return out


def _uploader(account: str):
    from src.seller_console.market_cred_view import coupang_account
    from src.channel_sync.coupang_uploader import make_uploader
    with coupang_account(account):
        return make_uploader()[0]


def target(item: dict, up, seller_id: str = "") -> Dict:
    """`{ready, contents, hash, translated, failed, why}` — 지금 등록하면 나갈 상세(등록과 같은 빌더)."""
    from src.seller_console.product_builder import build_product
    from src.seller_console.upload_dispatcher import build_dispatch_payload
    from src.channel_sync.coupang_uploader import prepared_input
    from src.channel_sync._channel_bridge import to_collected
    pd = build_dispatch_payload(build_product(item, edits={}, seller_id=seller_id), item)
    skipped = _effective_detail_images(item, pd)
    failed = int(pd.get("detail_translate_failed") or 0)
    prepared = up.prepare_product(to_collected(prepared_input(pd)))
    contents = up._build_contents(prepared)
    n_img = sum(len(c.get("contentDetails") or []) for c in contents
                if any(str(d.get("detailType") or "").upper() == "IMAGE" for d in c.get("contentDetails") or []))
    sku_images = _sku_image_patch(item, pd)
    # 해시 = 상세 + 옵션 사진 + 정가 규칙(Y11-U) — 셋 중 하나라도 바뀌면 다시 보낸다
    return {"ready": failed == 0, "contents": contents,
            "hash": _hash({"contents": contents, "sku_images": sku_images, "list_price": _list_rule(), "img": 2}),
            "sku_images": sku_images,
            "translated": int(pd.get("detail_auto_translated") or 0), "failed": failed,
            "why": str(pd.get("detail_translate_why") or ""), "detail_images": n_img,
            "detail_images_skipped": skipped, "providers": dict(pd.get("detail_translate_providers") or {})}


def _sku_image_patch(item: dict, pd: dict) -> dict:
    """Y11-U(오너 2026-10-16 14:58) — `{sku_id: 번역본 사진 주소}`(번역본을 쓰기로 된 SKU만). 우리 주소인 장은 뺀다(쿠팡이 못 가져간다)."""
    try:
        from src.services import image_translate_store as _its
        from src.services.image_reachability import is_internal
        ex = json.loads(item.get("extra_json") or "{}") or {}
        mapping = _its.sku_image_map(ex, item_id=str(item.get("id") or ""))
        out = {}
        for k in ex.get("skus") or pd.get("skus") or []:          # 수집 원본 SKU(사진 원본 주소로 짝을 찾는다)
            if not isinstance(k, dict):
                continue
            new = mapping.get(str(k.get("image") or k.get("img") or k.get("pic") or "").strip())
            if new and str(k.get("sku_id") or "") and not is_internal(new):
                out[str(k["sku_id"])] = new
        return out
    except Exception as exc:                                      # noqa: BLE001 — 옵션 사진은 덤 — 상세 갱신은 그대로
        logger.warning("[쿠팡 상세 갱신] 옵션 사진 계산 실패(그대로 둠): %s", exc)
        return {}


def image_summary(sku: str, images: list) -> dict:
    """Y11-W — 보낸 사진 줄 요약(반려 대조용): 장마다 종류·cdnPath 유무·vendorPath 호스트·확장자·쿼리·길이. 주소 전체는 남기지 않는다."""
    from urllib.parse import urlparse
    rows = []
    for x in images or []:
        v = str(x.get("vendorPath") or "")
        u = urlparse(v) if v.startswith(("http://", "https://")) else None
        rows.append({"type": str(x.get("imageType") or ""), "cdn": bool(x.get("cdnPath")),
                     "vendor": (u.netloc if u else ("relative" if v else "")), "ext": (v.rsplit(".", 1)[-1][:5] if "." in v[-6:] else ""),
                     "query": bool(u and u.query), "len": len(v)})
    return {"sku": sku, "n": len(rows), "images": rows[:6]}


def _list_rule() -> str:
    """해시에 넣는 정가 규칙 — 표시 할인율이 바뀌면 다시 보낸다(Y11-U 번복: 「판매가 그대로」로 나간 등록본도 원복)."""
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    return f"markup:{CU.list_markup_pct():g}"


def patch_items(body: dict, tg: dict) -> dict:
    """조회 원문 몸통의 items[]에 — 상세(contents) · 옵션 대표 사진(그 SKU의 번역본) · 정가(판매가 × (1+표시 할인율))를 얹는다.
    `{"images": 바꾼 품목 수, "list_price": 정가를 고친 품목 수}`."""
    from src.uploaders.coupang_uploader import CoupangUploader as CU
    n_img = n_price = 0
    sent: List[dict] = []
    for it in body.get("items") or []:
        it["contents"] = tg["contents"]
        sid = str(it.get("externalVendorSku") or "")
        new = (tg.get("sku_images") or {}).get(sid)
        if new:
            imgs = [x for x in (it.get("images") or []) if isinstance(x, dict)]
            rest = [x for x in imgs if str(x.get("imageType") or "").upper() != "REPRESENTATION"
                    and (x.get("vendorPath") or x.get("cdnPath"))]
            # Y11-W(오너 2026-10-16 23:56 · 고가네 「기타이미지 경로가 잘못되어」×16옵션): 기타 사진은 **쿠팡이 준 그대로**
            #   (cdnPath·vendorPath 둘 다 · 순서만 다시). 예전엔 cdnPath(쿠팡 상대 경로 `vendor_inventory/…`)를 vendorPath(절대 주소 칸)에
            #   옮겨 담아 보냈다 — 10:20 첫 옵션 사진 갱신부터 반려.
            it["images"] = ([{"imageOrder": 0, "imageType": "REPRESENTATION", "vendorPath": new}]
                            + [dict(x, imageOrder=i + 1, imageType=x.get("imageType") or "DETAIL") for i, x in enumerate(rest)])
            n_img += 1
            if len(sent) < 3:
                sent.append(image_summary(sid, it["images"]))
        want = CU.list_price(it.get("salePrice"))
        if want and it.get("originalPrice") != want:
            it["originalPrice"] = want                            # 정가 = 판매가 × (1+표시 할인율 · 오너 설정)
            n_price += 1
    return {"images": n_img, "list_price": n_price, "sent": sent}


def _effective_detail_images(item: dict, pd: dict) -> int:
    """Y11-R — 등록과 같은 규칙으로 **나갈 상세 이미지**(번역본 사용 반영 · 갤러리와 겹치는 장 제외)를 `pd`에 싣는다.

    세션이 없는 크론에서도 돈다(`_outbound_images`는 로그인 세션으로 상품을 다시 읽는다). 아직 우리 서버 주소인 장은
    먼저 CDN으로 올려 보고(`_ensure_outward` — 등록과 같은 단계), 그래도 우리 주소면 **빼고** 그 장 수를 돌려준다
    (쿠팡이 못 가져가는 주소를 실으면 깨진 그림이 된다 — 가짜 이미지 0).
    """
    try:
        from src.services import image_translate_store as _its
        from src.services.image_reachability import is_internal
        try:
            from src.seller_console.views import _ensure_outward
            item = _ensure_outward(item)
        except Exception as exc:                                  # noqa: BLE001 — CDN이 없으면 아래에서 그 장을 뺀다
            logger.info("[쿠팡 상세 갱신] 외부 주소 올리기 건너뜀: %s", exc)
        ex = json.loads(item.get("extra_json") or "{}") or {}
        iid = str(item.get("id") or "")
        gal = _its.effective_images(ex, item_id=iid, originals=pd.get("images") or []) or list(pd.get("images") or [])
        det = _its.effective_images(ex, kind="detail", item_id=iid,
                                    originals=pd.get("detail_images") or []) or list(pd.get("detail_images") or [])
        _g, det = _its.drop_cross_duplicates(gal, det)
        keep = [u for u in det if not is_internal(str(u or ""))]
        pd["detail_images"] = keep
        return len(det) - len(keep)
    except Exception as exc:                                      # noqa: BLE001 — 실패하면 빌더 값 그대로
        logger.warning("[쿠팡 상세 갱신] 상세 이미지 계산 실패(빌더 값 그대로): %s", exc)
        return 0


def _queue_put(entry: dict) -> None:
    from src.db import image_translate_queue_pg as st
    cur = st.state_get(QUEUE_KEY) or {}
    rows = [r for r in (cur.get("rows") or []) if not (r.get("item_id") == entry["item_id"] and r.get("market") == entry["market"])]
    st.state_set(QUEUE_KEY, {"rows": rows + [entry]})


def _queue_drop(item_id: str, market: str) -> None:
    from src.db import image_translate_queue_pg as st
    cur = st.state_get(QUEUE_KEY) or {}
    st.state_set(QUEUE_KEY, {"rows": [r for r in (cur.get("rows") or [])
                                      if not (r.get("item_id") == item_id and r.get("market") == market)]})


LAST_KEY = "coupang_detail_refresh:last"


def record_last(out: dict) -> None:
    """Y11-S — 마지막 드레인 결과를 운영 DB에(로그를 못 볼 때 보고용). 줄은 원문을 잘라서 — 글 내용·키는 없다."""
    try:
        from src.db import image_translate_queue_pg as st
        keep = ("market", "sid", "sent", "ok", "state", "error", "market_status", "body", "detail_images",
                "translate_line", "detail_image", "patched", "waiting", "dropped", "reason", "tries", "at", "sent_images")
        rows = [{k: (str(r.get(k))[:1500] if isinstance(r.get(k), str) else r.get(k)) for k in keep if k in r}
                for r in (out.get("rows") or [])][:10]
        st.state_set(LAST_KEY, {"at": _now(), **{k: out.get(k) for k in ("picked", "sent", "ok", "left")}, "rows": rows})
    except Exception as exc:                                      # noqa: BLE001 — 기록 실패는 로그만
        logger.warning("[쿠팡 상세 갱신] 마지막 결과 기록 실패: %s", exc)


SKU_IMAGE_REASON = "옵션 사진 갱신"


def enqueue_item(item_id: str, extra: dict, seller_id: str = "", reason: str = SKU_IMAGE_REASON) -> int:
    """Y11-U — 이 상품의 쿠팡 등록본마다 갱신 줄을 세운다(이미 서 있으면 그대로). 보낸 수가 아니라 **세운 줄 수**.
    번역 대기 줄이 아니라서 드레인이 검토 상태를 먼저 묻는다(승인·임시저장·반려일 때만 보냄 — 재심사 중엔 기다린다)."""
    n = 0
    try:
        have = {(r.get("item_id"), r.get("market")) for r in queue_rows()}
        for u in coupang_uploads(extra or {}):
            if (str(item_id), u["market"]) in have:
                continue
            _queue_put({"item_id": str(item_id), "market": u["market"], "sid": u["sid"], "account": u["account"],
                        "seller_id": seller_id, "reason": reason, "raw": "", "at": _now(), "tries": 0})
            n += 1
    except Exception as exc:                                     # noqa: BLE001 — 줄 세우기는 덤 — 부른 쪽(편집 저장·다듬기)을 막지 않는다
        logger.warning("[쿠팡 상세 갱신] 줄 세우기 실패 item=%s: %s", str(item_id)[:8], exc)
    return n


def queue_rows() -> List[dict]:
    from src.db import image_translate_queue_pg as st
    return list((st.state_get(QUEUE_KEY) or {}).get("rows") or [])


def providers_line(providers: dict) -> str:
    """`{"deepl": 51}` → 「상세 번역: deepl 51줄(무료(DeepL Free 월 50만 자))」. 없으면 빈 줄."""
    if not providers:
        return ""
    from src.uploaders.detail_translate import billing_of
    return "상세 번역: " + " · ".join(f"{p} {n}줄" + (f"({billing_of(p)})" if billing_of(p) else "")
                                     for p, n in providers.items())


def sync_line(extra: dict, market: str, item_id: str = "", rows: Optional[List[dict]] = None) -> str:
    """Y11-R — 마켓 상태 팝업·드로어 맨 위 한 줄: 이 쿠팡 등록본의 **상세 갱신**이 어디까지 왔나(큐·마지막 전송).
    Y12-A(오너 2026-10-17): 한 줄은 짧게 — 「쿠팡 상세 보내는 중」 · 「10-17 14:10 쿠팡 상세 보냄」 · 「쿠팡 상세 보내기 실패」.
    이유(다듬은 버전·기타이미지 수리·시도 횟수·실패 원문)는 접힘(`sync_why`)."""
    return _sync(extra, market, item_id, rows)[0]


def sync_why(extra: dict, market: str, item_id: str = "", rows: Optional[List[dict]] = None) -> str:
    """접힘 줄 — 한 줄(`sync_line`)의 이유."""
    return _sync(extra, market, item_id, rows)[1]


def _sync(extra: dict, market: str, item_id: str = "", rows: Optional[List[dict]] = None):
    if not str(market or "").startswith("coupang"):
        return "", ""
    try:
        rows = queue_rows() if rows is None else rows
    except Exception:                                             # noqa: BLE001 — 한 줄 재료라 팝업을 막지 않는다
        rows = []
    q = next((r for r in rows if r.get("market") == market and (not item_id or r.get("item_id") == item_id)), None)
    if q:
        tail = f" · {int(q.get('tries') or 0)}번 시도" if q.get("tries") else ""
        return "쿠팡 상세 보내는 중", f"{q.get('reason') or '대기'}{tail}"
    s = ((extra or {}).get("coupang_detail_sync") or {}).get(market) or {}
    from src.seller_console.attention import kst
    if s.get("ok") and s.get("state") != "same":
        return f"{kst(s.get('at'))} 쿠팡 상세 보냄".strip(), "쿠팡이 바뀐 내용을 다시 심사해요"
    if s.get("ok"):
        return "쿠팡 상세 최신", "보낼 것 없음"
    if s.get("error"):
        return "쿠팡 상세 보내기 실패", str(s["error"])[:200]
    return "", ""


def store_save(item_id: str, seller_ids: Optional[set] = None) -> Callable[[dict], None]:
    """Y11X — `refresh_item(save=…)`용: **쿠팡 갱신 기록(`coupang_detail_sync`)만** 지금 DB 값에 덧대 저장한다.
    같은 틱에 도는 네이버 본문 갱신·다듬기 저장과 서로 덮지 않는다(10-17 05:10 VRSUK 기록 소실)."""
    from src.seller_console import collect_history_store as store

    def _save(ex: dict) -> None:
        mine = (ex or {}).get("coupang_detail_sync") or {}

        def _apply(fresh: dict) -> None:
            fresh["coupang_detail_sync"] = {**(fresh.get("coupang_detail_sync") or {}), **mine}
        store.merge_extra(str(item_id), _apply, seller_ids=seller_ids)
    return _save


def refresh_item(item: dict, *, seller_id: str = "", markets: Optional[List[str]] = None,
                 make_up: Optional[Callable[[str], object]] = None, save: Optional[Callable[[dict], None]] = None) -> List[dict]:
    """이 상품의 쿠팡 등록본마다 상세 갱신 시도 — 줄마다 `{market, sid, sent, ok, state, error, market_status, body}`.
    결과는 `extra.coupang_detail_sync[market]`에 남기고(`save(extra)`), 못 보냈으면 큐에 넣는다."""
    make_up = make_up or _uploader
    try:
        ex = json.loads(item.get("extra_json") or "{}") or {}
    except Exception:
        ex = {}
    item_id = str(item.get("id") or "")
    sync = ex.get("coupang_detail_sync") if isinstance(ex.get("coupang_detail_sync"), dict) else {}
    out: List[dict] = []
    for u in coupang_uploads(ex):
        if markets and u["market"] not in markets:
            continue
        row = {"market": u["market"], "sid": u["sid"], "sent": False, "ok": False, "state": "", "error": "",
               "market_status": None, "body": "", "at": _now()}
        try:
            up = make_up(u["account"])
            tg = target(item, up, seller_id)
            # Y11-R 보강: 무엇을 보내려 했나(상세 이미지 장 수 · 번역 제공자별 줄 수와 과금)
            row.update(detail_images=tg.get("detail_images", 0), translate_line=providers_line(tg.get("providers") or {}))
            if (sync.get(u["market"]) or {}).get("hash") == tg["hash"] and (sync.get(u["market"]) or {}).get("ok"):
                row.update(ok=True, state="same", error="이미 같은 상세를 보냈어요")
                out.append(row)
                continue
            if not tg["ready"]:
                row.update(state="translate_wait", error=f"상세 번역 실패 {tg['failed']}칸({tg['why']}) — 번역되면 보내요")
                _queue_put({"item_id": item_id, "market": u["market"], "sid": u["sid"], "account": u["account"],
                            "seller_id": seller_id, "reason": "번역 대기", "raw": row["error"], "at": _now(),
                            "tries": int((sync.get(u["market"]) or {}).get("tries") or 0)})
                out.append(row)
                continue
            # Y13-F F1: 상세 갱신 PUT도 쿠팡 일일 구매옵션 한도(판매자 공용)를 먹는다 — 오늘 한도를 다 썼거나
            #   갱신분이 하루 상한(REFRESH_DAILY_ITEMS)을 넘으면 보내지 않고 줄에 남긴다(내일 같은 자리에서 막히지 않게).
            from src.services import coupang_option_quota as _coq
            _block = _coq.refresh_block(str(getattr(up, "vendor_id", "") or ""))
            if _block:
                row.update(state="option_quota", error=_block)
                _queue_put({"item_id": item_id, "market": u["market"], "sid": u["sid"], "account": u["account"],
                            "seller_id": seller_id, "reason": "쿠팡 옵션 한도", "raw": _block, "at": _now(),
                            "tries": int((sync.get(u["market"]) or {}).get("tries") or 0)})
                out.append(row)
                continue
            up.count_kind = "refresh"
            live = up.get_product(u["sid"])
            if "error" in live:
                row.update(error=f"쿠팡 상품 조회 실패 — {live['error']}")
            else:
                raw_state = str(live.get("statusName") or live.get("status") or "")
                row["state"] = raw_state
                body = json.loads(json.dumps(live))
                row["patched"] = patch_items(body, tg)                   # 상세 + 옵션 사진 + 정가(Y11-U)
                from src.uploaders.coupang_uploader import CoupangUploader as _CU
                row["patched"]["dropped_barcode"] = _CU.strip_empty_barcode_attrs(body)   # Y14: 빈 GTIN·MPN 칸은 안 돌려보냄
                body["requested"] = True
                res = up.modify_product(body)
                row["sent"] = True
                row.update(ok=bool(res.get("success")), error=str(res.get("error") or "")[:500],
                           market_status=res.get("market_status"), body=str(res.get("body") or "")[:2000])
                if res.get("detail_image"):
                    row["detail_image"] = res["detail_image"]          # 이미지 블록 판정 + 응답 원문(거부면 글만 재전송 원문)
                if res.get("contents_sent") is not None:
                    tg = dict(tg, hash=_hash({"contents": res["contents_sent"], "sku_images": tg.get("sku_images") or {},
                                              "list_price": _list_rule(), "img": 2}))   # 실제로 받아진 상세로 해시(글만 재전송이면 그것)
                # Y11X: 보낸 사진 주소 목록(해시+URL) — 실제로 받아진 상세(글만 재전송이면 그것) + 옵션 사진
                from src.services import sent_images as _si
                _sent = dict(body)
                if res.get("contents_sent") is not None:
                    _sent["items"] = [dict(it, contents=res["contents_sent"]) for it in body.get("items") or []]
                row["sent_images"] = _si.from_coupang(_sent)
            if row["ok"]:
                _queue_drop(item_id, u["market"])
            else:
                tries = int((sync.get(u["market"]) or {}).get("tries") or 0) + 1
                row["tries"] = tries
                _queue_put({"item_id": item_id, "market": u["market"], "sid": u["sid"], "account": u["account"],
                            "seller_id": seller_id, "reason": "승인 후 자동 갱신" if row["state"] else "조회 실패",
                            "raw": (row["error"] + " " + row["body"])[:1500], "market_status": row["market_status"],
                            "state": row["state"], "at": _now(), "tries": tries})
            sync[u["market"]] = {"hash": tg["hash"], "ok": row["ok"], "at": row["at"], "state": row["state"],
                                 "error": row["error"][:300], "market_status": row["market_status"],
                                 "lines": tg["translated"], "tries": row.get("tries", 0)}
            if row.get("sent_images"):
                sync[u["market"]]["sent_images"] = row["sent_images"]
        except Exception as exc:                                  # noqa: BLE001 — 한 마켓 실패가 다른 마켓을 막지 않는다
            row["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.warning("[쿠팡 상세 갱신] %s %s 실패: %s", item_id[:8], u["market"], row["error"])
        logger.info("[쿠팡 상세 갱신] item=%s %s sid=%s sent=%s ok=%s state=%s err=%s", item_id[:8], u["market"], u["sid"],
                    row["sent"], row["ok"], row["state"], row["error"][:200])
        out.append(row)
    ex["coupang_detail_sync"] = sync
    if save and out:
        save(ex)
    return out


def drain(get_item: Callable[[str, str], Optional[dict]], save_for: Callable[[str, str], Callable[[dict], None]],
          make_up: Optional[Callable[[str], object]] = None, budget: int = 10) -> Dict:
    """큐를 비운다 — 번역 대기는 다시 만들어 보고, 승인 대기는 상태를 물어 승인됐으면 보낸다. `{picked, sent, ok, left, rows}`."""
    make_up = make_up or _uploader
    rows = queue_rows()
    out = {"picked": 0, "sent": 0, "ok": 0, "left": len(rows), "rows": []}
    for q in rows[:budget]:
        out["picked"] += 1
        item = get_item(q["item_id"], q.get("seller_id") or "")
        if not item:
            _queue_drop(q["item_id"], q["market"])
            continue
        if int(q.get("tries") or 0) >= MAX_TRIES:
            _queue_drop(q["item_id"], q["market"])
            out["rows"].append({**q, "dropped": "시도 상한"})
            continue
        if q.get("reason") != "번역 대기":
            st = make_up(q["account"]).review_status(q["sid"])
            if st.get("state") not in ("approved", "saved", "rejected"):
                out["rows"].append({**q, "waiting": st.get("state") or "unknown"})
                continue                                          # 아직 검토 중 — 다음 회전에
        res = refresh_item(item, seller_id=q.get("seller_id") or "", markets=[q["market"]], make_up=make_up,
                           save=save_for(q["item_id"], q.get("seller_id") or ""))
        for r in res:
            out["sent"] += int(bool(r.get("sent")))
            out["ok"] += int(bool(r.get("ok")))
            out["rows"].append(r)
    out["left"] = len(queue_rows())
    return out
