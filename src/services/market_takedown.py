"""오너 11-25 ①c 「이 마켓에서 내리기」 — 이미 나간 마켓을 **판매중지**한다. 오너가 결과 카드에서 누르고 한 번 더 확인했을 때만 불린다.

· 쿠팡: 판매자 상품번호 → 옵션(vendorItemId) 전부 `sales/stop`(relist가 운영에서 쓰는 그 경로) → `on_sale`이 False로 읽혀야 「내렸어요」
· 스마트스토어: 채널 상품번호 → 원상품번호 → `PUT /v1/products/origin-products/{no}/change-status {statusType: SUSPENSION}`
  (커머스 API 문서 — 상태값 SUSPENSION) → 다시 읽어 SUSPENSION이어야 「내렸어요」. 못 읽으면 「확인 못 함」(가짜 성공 금지)
· 그 밖의 마켓: 여기서 내리지 않는다 — 판매자센터 안내
지우지 않는다(판매중지 = 되돌릴 수 있다).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _coupang(rec: Dict[str, Any], account: str) -> Dict[str, Any]:
    from src.services import coupang_relist as R
    sid = str(rec.get("product_id") or "").strip()
    if not sid.isdigit():
        return {"ok": False, "error": "쿠팡 상품번호가 기록에 없어요 — WING에서 내려 주세요."}
    up = R._uploader(account)
    live = up.get_product(sid)
    if "error" in live:
        return {"ok": False, "error": f"쿠팡 상품을 읽지 못했어요 — {live['error']}"}
    vids = R._vids(live)
    if not vids:
        return {"ok": False, "error": "쿠팡 옵션 번호를 못 찾았어요 — WING에서 내려 주세요."}
    done, left = [], []
    for vid in vids:
        s = up.stop_sale(vid)
        if s.get("ok") and up.on_sale(vid) is False:
            done.append(vid)
        else:
            left.append(f"{vid}: {s.get('error') or '중지 뒤에도 판매중으로 읽힘'}")
    return {"ok": bool(done) and not left, "stopped": len(done), "of": len(vids),
            "error": "" if not left else "일부 옵션을 못 내렸어요 — " + " · ".join(left)[:300]}


def _smartstore(rec: Dict[str, Any], account: str) -> Dict[str, Any]:
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    ch = str(rec.get("channel_product_no") or rec.get("product_id") or "").strip()
    if not ch.isdigit():
        return {"ok": False, "error": "스마트스토어 상품번호가 기록에 없어요 — 판매자센터에서 내려 주세요."}
    up = NaverSmartStoreUploader(account=account or None)
    got = up._api_request("GET", f"/v2/products/channel-products/{ch}")
    if not isinstance(got, dict) or "error" in got:
        return {"ok": False, "error": "스마트스토어 상품을 읽지 못했어요 — " + str((got or {}).get("error") if isinstance(got, dict) else got)[:200]}
    origin = str(got.get("originProductNo") or (got.get("originProduct") or {}).get("originProductNo") or rec.get("product_id") or "").strip()
    if not origin.isdigit():
        return {"ok": False, "error": "원상품번호를 못 찾았어요 — 판매자센터에서 내려 주세요."}
    res = up._api_request("PUT", f"/v1/products/origin-products/{origin}/change-status", data={"statusType": "SUSPENSION"})
    if not isinstance(res, dict) or "error" in res:
        return {"ok": False, "error": "판매중지 요청이 거절됐어요 — " + str((res or {}).get("error") if isinstance(res, dict) else res)[:200]}
    after = up._api_request("GET", f"/v2/products/channel-products/{ch}")
    st = str(((after or {}).get("originProduct") or {}).get("statusType") or "") if isinstance(after, dict) else ""
    if st != "SUSPENSION":
        return {"ok": False, "error": f"요청은 갔는데 다시 읽은 상태가 「{st or '모름'}」이에요 — 판매자센터에서 확인해 주세요."}
    return {"ok": True, "status": st, "origin_no": origin}


def take_down(rec: Dict[str, Any]) -> Dict[str, Any]:
    market = str(rec.get("market") or "")
    base, _, account = market.partition(":")
    account = account or str(rec.get("account") or "")
    try:
        if base == "coupang":
            out = _coupang(rec, account)
        elif base == "smartstore":
            out = _smartstore(rec, account)
        else:
            out = {"ok": False, "error": "이 마켓은 여기서 내릴 수 없어요 — 그 마켓 판매자센터에서 내려 주세요."}
    except Exception as exc:                                       # noqa: BLE001 — 사유를 돌려준다
        out = {"ok": False, "error": f"내리는 중 오류 — {type(exc).__name__}: {str(exc)[:160]}"}
    logger.warning("[내리기] %s %s → ok=%s %s", market, rec.get("channel_product_no") or rec.get("product_id"), out.get("ok"), out.get("error", "")[:120])
    return out
