"""M6(오너 2026-10-08) — 등록한 상품의 **마켓 검토·판매 상태** 한 자리(쿠팡·스마트스토어·11번가·멀티샵).

실측(오너 폰 16:26 KST, 플리츠 세트): 쿠팡 우주대행 16407690349 등록 성공 → 「검토 상태 보기」가 아무것도 안 보여 줌.
상태는 이 모듈 하나에서 묻고, 마지막으로 알려진 값은 수집 행 `uploaded[].review`에 남긴다(M7 칩이 목록을 그릴 때
마켓에 묻지 않고 그 값만 쓴다). 마켓에 묻는 건 **팝업을 열 때만** — 같은 상품·마켓은 60초 캐시.

- 쿠팡: `GET seller-products/{sellerProductId}`의 `statusName`(승인대기중·승인완료·승인반려 …) + 반려 사유(이력).
  WING 딥링크는 오너가 준 실제 주소 형식 — `…/vendor-inventory/modify?vendorInventoryId={sellerProductId}`.
- 스마트스토어: `GET /v2/products/origin-products/{originProductNo}`의 `originProduct.statusType`
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
        out.append({"market": m, "chip": chip_label(m), "label": str(u.get("market_label") or chip_label(m)),
                    "product_id": pid, "at": str(u.get("at") or ""), "account": str(u.get("account") or m.partition(":")[2]),
                    "external_url": str(u.get("external_url") or ""), "review": rv,
                    "tone": CHIP_TONE.get(str(rv.get("state") or ""), "wait"),
                    "state_label": str(rv.get("label") or "등록됨")})
    out.sort(key=lambda r: _ORDER.get(r["market"], 99))
    return out


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
    up = NaverSmartStoreUploader(account=rec["account"] or None)
    out = {"sid": pid, "state": "unknown", "label": "확인 못 함", "status_raw": "", "comment": "", "link": "",
           "manage_url": NAVER_SELLER_HOME, "manage_label": "판매자센터 열기", "error": ""}
    res = up._api_request("GET", f"/v2/products/origin-products/{pid}")
    if not isinstance(res, dict) or "error" in res:
        out["error"] = str((res or {}).get("error") if isinstance(res, dict) else res)[:300]
        return out
    raw = str(((res.get("originProduct") or {}).get("statusType")) or "").strip()
    state, label = NAVER_STATES.get(raw, ("unknown", raw or "확인 못 함"))
    out.update(state=state, label=label, status_raw=raw)
    ch = str(((res.get("smartstoreChannelProduct") or {}).get("channelProductNo")) or "").strip()
    if ch and state == "approved":
        out["link"] = f"https://smartstore.naver.com/main/products/{ch}"
    return out


def _unsupported(rec: dict) -> dict:
    home = ELEVENST_SELLER_HOME if rec["market"] == "elevenst" else ""
    return {"sid": rec["product_id"], "state": "unsupported", "label": "상태 조회 미연동 — 등록 기록만",
            "status_raw": "", "comment": "", "link": rec.get("external_url") or "", "error": "",
            "manage_url": home, "manage_label": "셀러오피스 열기" if home else ""}


def query(rec: dict, *, now: Optional[float] = None) -> dict:
    """한 마켓의 지금 상태 — 60초 캐시. 결과에 `cached`(캐시에서 왔나)와 `checked_at`을 싣는다."""
    now = time.time() if now is None else now
    key = (rec["market"], rec["product_id"])
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
               registered_at=rec["at"], checked_at=datetime.now(timezone.utc).isoformat(),
               tone=CHIP_TONE.get(str(row.get("state") or ""), "fail"))
    with _LOCK:
        _CACHE[key] = (now, row)
    return dict(row, cached=False)


def remember(extra: dict, row: dict) -> bool:
    """마지막으로 알려진 상태를 `uploaded[].review`에 — 조회가 실패했으면 예전 값을 덮지 않는다(실패도 칩 색으로는 안 바꾼다)."""
    if row.get("state") in ("unknown",) and row.get("error"):
        return False
    for u in (extra or {}).get("uploaded") or []:
        if isinstance(u, dict) and u.get("market") == row.get("market"):
            u["review"] = {k: row.get(k) for k in ("state", "label", "comment", "link", "status_raw", "checked_at")}
            if row.get("product_id") and not u.get("product_id"):
                u["product_id"] = row["product_id"]
            return True
    return False


def reset_cache() -> None:
    with _LOCK:
        _CACHE.clear()
