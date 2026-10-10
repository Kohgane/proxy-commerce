"""M6(오너 2026-10-08) — listing_status: 등록한 상품의 **마켓 검토·판매 상태** 한 자리(쿠팡·스마트스토어·11번가·멀티샵).

실측(오너 폰 16:26 KST, 플리츠 세트): 쿠팡 우주대행 16407690349 등록 성공 → 「검토 상태 보기」가 아무것도 안 보여 줌.
상태는 이 모듈 하나에서 묻고, 마지막으로 알려진 값은 수집 행 `uploaded[].review`에 남긴다(M7 칩이 목록을 그릴 때
마켓에 묻지 않고 그 값만 쓴다). 마켓에 묻는 건 **팝업을 열 때만** — 같은 상품·마켓은 60초 캐시.

- 쿠팡: `GET seller-products/{sellerProductId}`의 `statusName`(승인대기중·승인완료·승인반려 …) + 반려 사유(이력).
  WING 딥링크는 오너가 준 실제 주소 형식 — `…/vendor-inventory/modify?vendorInventoryId={sellerProductId}`.
- 스마트스토어(Y7-J 오너 2026-10-10): **채널 상품번호 기준** — `GET /v2/products/channel-products/{channelProductNo}`의
  `originProduct.statusType`(채널 번호가 없는 예전 기록만 `origin-products/{originProductNo}`). 구매자 주소도 채널 번호로
  `smartstore.naver.com/{스토어}/products/{channelProductNo}`. 등록 기록은 두 번호를 다 가진다(`product_id`=원상품번호 ·
  `channel_product_no`). 예전 기록은 주소(`…/products/{채널번호}`)에서 읽어 소급한다.
- (옛) 스마트스토어: `GET /v2/products/origin-products/{originProductNo}`의 `originProduct.statusType`
  (문서 값: WAIT·SALE·OUTOFSTOCK·UNADMISSION·REJECTION·SUSPENSION·CLOSE·PROHIBITION·DELETE). 판매자센터는
  상품별 주소 형식을 확인하지 못해 **홈**으로만 연다(추측 주소 금지).
- 11번가·멀티샵·Shopify: 상태 조회를 붙이지 않았다 — 「상태 조회 미연동」이라고 그대로 말한다(지어내지 않음).
- 못 물어보면 그 원문(HTTP·본문 앞부분)을 그대로 싣는다.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

CACHE_SEC = 60
_CACHE: Dict[tuple, tuple] = {}
_LOCK = threading.Lock()

#: 칩 표기(M7) — 등록 레코드의 market 코드 → 짧은 이름. 순서 = 화면 순서.
CHIP_LABELS = (
    ("coupang:gogane", "쿠팡·고가네"), ("coupang:woojoo", "쿠팡·우주대행"), ("coupang", "쿠팡"),
    ("smartstore:chezgoga", "셰고가"), ("smartstore:gocosmos", "고코스모스"), ("smartstore", "스마트스토어"),
    ("elevenst", "11번가"), ("woocommerce", "멀티샵"), ("shopify", "Shopify"),
)
_CHIP = dict(CHIP_LABELS)
_ORDER = {m: i for i, (m, _l) in enumerate(CHIP_LABELS)}

COUPANG_WING_MODIFY = "https://wing.coupang.com/tenants/seller-web/vendor-inventory/modify?vendorInventoryId={sid}"
NAVER_SELLER_HOME = "https://sell.smartstore.naver.com/"
ELEVENST_SELLER_HOME = "https://soffice.11st.co.kr/"

#: 스마트스토어 statusType → (state, 화면 이름)
NAVER_STATES = {
    "SALE": ("approved", "판매중"), "WAIT": ("pending", "판매대기"), "OUTOFSTOCK": ("approved", "품절"),
    "UNADMISSION": ("pending", "승인대기"), "REJECTION": ("rejected", "승인거부"), "SUSPENSION": ("pending", "판매중지"),
    "CLOSE": ("deleted", "판매종료"), "PROHIBITION": ("rejected", "판매금지"), "DELETE": ("deleted", "삭제"),
}
#: 칩 색(M7): 승인대기 회색 · 승인완료 초록 · 반려 빨강 · 실패(조회 실패·확인 못 함) 주황
CHIP_TONE = {"approved": "ok", "pending": "wait", "saved": "wait", "rejected": "bad", "deleted": "bad",
             "unknown": "fail", "unsupported": "wait", "": "wait"}


def chip_label(market: str) -> str:
    return _CHIP.get(market) or market


def records(extra: dict) -> List[Dict]:
    """수집 행의 등록 기록(마켓별 1건, 화면 순서) — 상품번호가 없으면 예전 주소에서 읽는다(소급)."""
    import re
    out = []
    for u in (extra or {}).get("uploaded") or []:
        if not isinstance(u, dict) or not u.get("market"):
            continue
        m = str(u["market"])
        pid = str(u.get("product_id") or "").strip()
        if not pid:
            hit = re.search(r"/(?:vp/products|products)/(\d+)", str(u.get("external_url") or ""))
            pid = hit.group(1) if hit else ""
        rv = u.get("review") if isinstance(u.get("review"), dict) else {}
        acct = str(u.get("account") or m.partition(":")[2])
        ch, url = channel_no_of(u), str(u.get("external_url") or "")
        if m.startswith("smartstore") and ch:
            url = naver_product_url(acct, ch)                    # Y7-J: 스토어 주소로(예전 기록의 `main`도 바로잡아 보인다)
        out.append({"market": m, "chip": chip_label(m), "label": str(u.get("market_label") or chip_label(m)),
                    "product_id": pid, "channel_product_no": ch, "shown_no": ch or pid,     # 칩·「이미 등록됨」 번호(네이버 = 채널 번호)
                    "at": str(u.get("at") or ""), "account": acct,
                    "external_url": url, "review": rv,
                    "price": u.get("price") if isinstance(u.get("price"), dict) else {},   # M8-8: 등록 때 판매가 재료
                    "tone": CHIP_TONE.get(str(rv.get("state") or ""), "wait"),
                    "state_label": str(rv.get("label") or "등록됨")})
    out.sort(key=lambda r: (_ORDER.get(r["market"], 99), r["at"]))
    # Y7-K: 같은 상품·같은 마켓 등록이 2건 이상 — 카드 「중복 n건 — 정리」 재료
    cnt: Dict[str, int] = {}
    for r in out:
        cnt[r["market"]] = cnt.get(r["market"], 0) + 1
    for r in out:
        r["dup_count"] = cnt[r["market"]] if cnt[r["market"]] > 1 else 0
    return out


def chips(extra: dict) -> List[Dict]:
    """M7 칩 — 마켓당 **한 개**(가장 최근 등록). 같은 마켓 등록이 2건 이상이면 `dup_count`로 카드가 「중복 n건 — 정리」를 단다."""
    last: Dict[str, Dict] = {}
    for r in records(extra):
        last[r["market"]] = r                     # records는 (마켓 순서, 등록 시각) 정렬 — 마지막이 최근
    return sorted(last.values(), key=lambda r: _ORDER.get(r["market"], 99))


def duplicates(extra: dict) -> List[Dict]:
    """Y7-K — 마켓별 중복 등록 `[{market, chip, count, numbers}]`(2건 이상만)."""
    by: Dict[str, Dict] = {}
    for r in records(extra):
        if r["dup_count"]:
            d = by.setdefault(r["market"], {"market": r["market"], "chip": r["chip"], "count": r["dup_count"], "numbers": []})
            d["numbers"].append(r.get("shown_no") or r.get("product_id") or "")
    return list(by.values())


def channel_no_of(u: dict) -> str:
    """네이버 등록 기록의 채널 상품번호 — 기록에 있으면 그것, 없으면 예전 주소(`…/products/{채널번호}`)에서(소급).
    네이버 외 마켓은 ''."""
    import re
    if not str((u or {}).get("market") or "").startswith("smartstore"):
        return ""
    ch = str((u or {}).get("channel_product_no") or "").strip()
    if ch:
        return ch
    hit = re.search(r"smartstore\.naver\.com/[^/]+/products/(\d+)", str((u or {}).get("external_url") or ""))
    return hit.group(1) if hit else ""


def naver_product_url(account: str, channel_no: str) -> str:
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    try:
        return NaverSmartStoreUploader(account=account or None).product_url(channel_no)
    except Exception:
        return f"https://smartstore.naver.com/main/products/{channel_no}" if channel_no else ""


def _coupang(rec: dict) -> dict:
    from .views import _coupang_up_for
    sid = rec["product_id"]
    up = _coupang_up_for(rec["account"])
    st = up.review_status(sid)
    st["manage_url"] = COUPANG_WING_MODIFY.format(sid=sid)
    st["manage_label"] = "Wing에서 열기"
    return st


def _naver(rec: dict) -> dict:
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    pid = rec["product_id"]
    ch = str(rec.get("channel_product_no") or "").strip()
    up = NaverSmartStoreUploader(account=rec["account"] or None)
    out = {"sid": ch or pid, "state": "unknown", "label": "확인 못 함", "status_raw": "", "comment": "", "link": "",
           "manage_url": NAVER_SELLER_HOME, "manage_label": "판매자센터 열기", "error": "",
           "origin_product_no": pid, "channel_product_no": ch}
    # Y7-J: 채널 상품번호 기준(구매자 화면 번호) — 없으면(예전 기록) 원상품번호로
    res = up._api_request("GET", f"/v2/products/channel-products/{ch}" if ch else f"/v2/products/origin-products/{pid}")
    if not isinstance(res, dict) or "error" in res:
        out["error"] = str((res or {}).get("error") if isinstance(res, dict) else res)[:300]
        return out
    raw = str(((res.get("originProduct") or {}).get("statusType")) or "").strip()
    state, label = NAVER_STATES.get(raw, ("unknown", raw or "확인 못 함"))
    out.update(state=state, label=label, status_raw=raw)
    ch = ch or str(((res.get("smartstoreChannelProduct") or {}).get("channelProductNo")) or "").strip()
    out["channel_product_no"] = ch
    if ch and state == "approved":
        out["link"] = up.product_url(ch)
    return out


def _unsupported(rec: dict) -> dict:
    home = ELEVENST_SELLER_HOME if rec["market"] == "elevenst" else ""
    return {"sid": rec["product_id"], "state": "unsupported", "label": "상태 조회 미연동 — 등록 기록만",
            "status_raw": "", "comment": "", "link": rec.get("external_url") or "", "error": "",
            "manage_url": home, "manage_label": "셀러오피스 열기" if home else ""}


def query(rec: dict, *, now: Optional[float] = None) -> dict:
    """한 마켓의 지금 상태 — 60초 캐시. 결과에 `cached`(캐시에서 왔나)와 `checked_at`을 싣는다."""
    now = time.time() if now is None else now
    key = (rec["market"], rec["product_id"], rec.get("channel_product_no") or "")
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < CACHE_SEC:
            return dict(hit[1], cached=True)
    m = rec["market"]
    if not rec["product_id"]:
        row = {"state": "unknown", "label": "확인 못 함", "error": "등록 기록에 마켓 상품번호가 없어요", "sid": ""}
    else:
        try:
            if m.startswith("coupang"):
                row = _coupang(rec)
            elif m.startswith("smartstore"):
                row = _naver(rec)
            else:
                row = _unsupported(rec)
        except Exception as exc:                            # noqa: BLE001 — 원문 그대로(C 규칙)
            row = {"sid": rec["product_id"], "state": "unknown", "label": "확인 못 함",
                   "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    row.update(market=m, chip=rec["chip"], market_label=rec["label"], product_id=rec["product_id"],
               dup_count=rec.get("dup_count") or 0,                     # Y7-K: 같은 마켓 2건 이상 — 팝업 「이 기록 빼기」
               registered_at=rec["at"], checked_at=datetime.now(timezone.utc).isoformat(),
               registered_price=str((rec.get("price") or {}).get("line") or ""),
               tone=CHIP_TONE.get(str(row.get("state") or ""), "fail"))
    with _LOCK:
        _CACHE[key] = (now, row)
    return dict(row, cached=False)


#: M8(오너 2026-10-10) — 마켓 하나에 상태를 묻는 시간 상한. 넘으면 그 칸만 「상태 확인 실패」(다른 마켓은 기다리지 않는다).
STATUS_TIMEOUT_SEC = 12.0


def db_row(rec: dict) -> dict:
    """M8 — **DB만으로** 그린 팝업 한 줄(마켓에 묻지 않음). 상태는 마지막으로 알던 값(`uploaded[].review`) — 없으면 「상태 확인 중」.
    등록 기록이 있는 마켓은 전부 즉시 보인다(번호·링크·「본문 다시 보내기」)."""
    rv = rec.get("review") or {}
    m = rec["market"]
    manage = ""
    if m.startswith("coupang") and rec.get("product_id"):
        manage, mlabel = COUPANG_WING_MODIFY.format(sid=rec["product_id"]), "Wing에서 열기"
    elif m.startswith("smartstore"):
        manage, mlabel = NAVER_SELLER_HOME, "판매자센터 열기"
    elif m == "elevenst":
        manage, mlabel = ELEVENST_SELLER_HOME, "셀러오피스 열기"
    else:
        mlabel = ""
    return {"market": m, "chip": rec["chip"], "market_label": rec["label"], "product_id": rec["product_id"],
            "channel_product_no": rec.get("channel_product_no") or "", "sid": rec.get("shown_no") or rec["product_id"],
            "dup_count": rec.get("dup_count") or 0, "registered_at": rec["at"],
            "state": str(rv.get("state") or ""), "label": str(rv.get("label") or ""),
            "comment": str(rv.get("comment") or ""), "status_raw": str(rv.get("status_raw") or ""),
            "last_checked_at": str(rv.get("checked_at") or ""),
            # 쿠팡 구매자 주소는 승인 뒤에만 생긴다(마지막 조회값) · 그 밖은 등록 기록의 주소(네이버 = 채널 번호 주소)
            "link": str(rv.get("link") or "") if m.startswith("coupang") else str(rec.get("external_url") or ""),
            "manage_url": manage, "manage_label": mlabel, "pending": True,
            "registered_price": str((rec.get("price") or {}).get("line") or ""),
            "tone": CHIP_TONE.get(str(rv.get("state") or ""), "wait")}


def query_many(recs: List[dict], *, timeout: float = None, extra_fn=None) -> List[dict]:
    """M8 — 마켓별 상태를 **병렬로** 묻는다. 마켓 하나가 `timeout`(기본 12초)을 넘기면 그 칸만 실패 줄 — 나머지는 기다리지 않는다.

    22:13 KST 실측: 등록 기록 4건을 하나씩 물어 3.6초(릴레이 2.5초 × 직렬). `extra_fn(rec, row)`는 같은 일꾼 안에서
    줄에 덧붙일 재료(네이버 판매가 구성 등). 요청 문맥(계정 키 선택 등 contextvars)은 일꾼마다 복사한다.
    """
    import contextvars
    from concurrent.futures import ThreadPoolExecutor, wait
    timeout = STATUS_TIMEOUT_SEC if timeout is None else float(timeout)
    if not recs:
        return []

    def _one(rec):
        row = query(rec)
        if extra_fn is not None:
            try:
                extra_fn(rec, row)
            except Exception as exc:                        # noqa: BLE001 — 덧붙일 한 줄이라 상태를 막지 않는다
                row.setdefault("extra_error", f"{type(exc).__name__}: {str(exc)[:120]}")
        return row

    pool = ThreadPoolExecutor(max_workers=min(8, len(recs)), thread_name_prefix="mkt-status")
    futs = [pool.submit(contextvars.copy_context().run, _one, r) for r in recs]
    wait(futs, timeout=timeout)
    out = []
    for rec, f in zip(recs, futs):
        if f.done() and f.exception() is None:
            out.append(f.result())
            continue
        why = (f"{int(timeout)}초 안에 마켓이 답하지 않았어요" if not f.done()
               else f"{type(f.exception()).__name__}: {str(f.exception())[:200]}")
        row = db_row(rec)
        row.update(state="unknown", label="상태 확인 실패", error=why, pending=False, tone="fail",
                   checked_at=datetime.now(timezone.utc).isoformat(), cached=False, timed_out=not f.done())
        out.append(row)
    pool.shutdown(wait=False, cancel_futures=True)        # 늦은 일꾼은 혼자 끝난다(캐시에만 남음) — 응답은 기다리지 않는다
    return out


def remember(extra: dict, row: dict) -> bool:
    """마지막으로 알려진 상태를 `uploaded[].review`에 — 조회가 실패했으면 예전 값을 덮지 않는다(실패도 칩 색으로는 안 바꾼다)."""
    if row.get("state") in ("unknown",) and row.get("error"):
        return False
    for u in (extra or {}).get("uploaded") or []:
        if isinstance(u, dict) and u.get("market") == row.get("market") and (
                not row.get("product_id") or not u.get("product_id")
                or str(u.get("product_id")) == str(row.get("product_id"))):   # Y7-K: 같은 마켓 2건이면 번호로 짝짓기
            u["review"] = {k: row.get(k) for k in ("state", "label", "comment", "link", "status_raw", "checked_at")}
            if row.get("product_id") and not u.get("product_id"):
                u["product_id"] = row["product_id"]
            if row.get("channel_product_no") and not u.get("channel_product_no"):
                u["channel_product_no"] = row["channel_product_no"]          # Y7-J: 조회로 알게 된 채널 번호도 남긴다
            return True
    return False


def reset_cache() -> None:
    with _LOCK:
        _CACHE.clear()
