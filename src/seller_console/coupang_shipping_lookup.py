"""src/seller_console/coupang_shipping_lookup.py — 쿠팡에서 출고지·반품지를 **불러온다** (F29-4).

## 왜

배송 7필드를 사람이 Wing에서 찾아 옮겨 적고 있었다. 쿠팡이 그 값을 API로 준다.

## 경로 — 오너 제공 공식 목록 (2026-09-16)

    반품지 목록 조회  GET /v2/providers/openapi/apis/api/v5/vendors/{vendorId}/returnShippingCenters
    반품지 단건 조회  GET /v2/providers/openapi/apis/api/v3/return/shipping-places/center-code
    출고지 조회      GET /v2/providers/marketplace_openapi/apis/api/v2/vendor/shipping-place/outbound

출고지 **생성/수정**은 v5 `outboundShippingCenters`지만 **조회는 marketplace_openapi v2가 정본**이다.
(내가 검색으로 본 스니펫은 v4와 v5가 서로 달라 근거가 못 됐다 — 이 목록이 정본이다.)

## 발명 금지 — 이 파일의 규율

- **서명·헤더는 새로 쓰지 않는다.** `CoupangUploader._api_request`가 정본이다(HMAC·릴레이·4xx 원문).
- **응답 필드명을 지어내지 않는다.** 응답 JSON을 **그대로 보관**하고, 화면엔 **원문 키를 나열**한다.
  매핑은 **응답에 실제로 있는 키에만** 붙인다 — 없으면 비워 두고 「그 칸은 못 채웠다」고 말한다.
- **모양도 지어내지 않는다.** 목록이 `data`에 있는지 `content`에 있는지 모른다 →
  **구조로** 찾는다(payload 안에서 dict들의 리스트를 찾는다). 이름을 찍지 않는다.
- 쿼리 파라미터(페이지 등)는 미확인 → **붙이지 않는다.** 400이 오면 그 응답 문장을 그대로 올린다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# 오너 제공 공식 목록 2026-09-16 — **문자열을 고쳐 쓰지 않는다**(계약이 이 값을 못박는다).
RETURN_CENTERS_PATH = "/v2/providers/openapi/apis/api/v5/vendors/{vendor_id}/returnShippingCenters"
RETURN_CENTER_ONE_PATH = "/v2/providers/openapi/apis/api/v3/return/shipping-places/center-code"
OUTBOUND_PLACES_PATH = "/v2/providers/marketplace_openapi/apis/api/v2/vendor/shipping-place/outbound"
# F32-2 실측(2026-09-18): 파라미터 없이 부르면 **400 INVALID_ARGUMENT**
#   `(pageNum & pageSize) or placeCodes or placeNames must be provided`.
#   **오류 문장이 준 이름을 그대로** 쓴다 — F29-4에서 「미확인이라 안 붙인다」로 둔 것이
#   옳았다(지어냈으면 다른 이름을 넣고 또 400을 받았다).
#   상한이 다르면 다음 400 원문이 알려 준다 — 그 문장이 그대로 화면에 뜬다.
OUTBOUND_PLACES_QUERY = "?pageNum=1&pageSize=50"

# 우리 칸 ← 쿠팡 응답 키 **후보**. 후보는 「이 이름이면 이 칸」이라는 사전일 뿐이고,
#   **응답에 그 키가 실제로 있을 때만** 쓴다. 하나도 없으면 그 칸은 비워 두고 화면이 원문 키를
#   보여 준다 — 사람이 고른다. (지어낸 키로 채우면 그건 값이 아니라 소설이다.)
RETURN_FIELD_CANDIDATES: Dict[str, tuple] = {
    "COUPANG_RETURN_CENTER_CODE": ("returnCenterCode", "shippingPlaceCode", "centerCode"),
    "COUPANG_RETURN_ZIP_CODE": ("returnZipCode", "zipCode", "postCode", "postalCode"),
    # F34-3(오너 2026-09-19): `addressDetail`은 **기본주소가 아니라 상세주소**다.
    #   기본주소 칸에 「4층 101호」가 들어가면, 그 값은 보이는 자리에선 그럴듯하고
    #   쿠팡에 나가는 순간 틀린다 — **같은 줄에 두 뜻을 담지 않는다.**
    "COUPANG_RETURN_ADDRESS": ("returnAddress", "address", "roadAddress"),
    "COUPANG_RETURN_ADDRESS_DETAIL": ("returnAddressDetail",),
    "COUPANG_RETURN_CHARGE_NAME": ("returnChargeName", "shippingPlaceName", "placeName", "name"),
    "COUPANG_COMPANY_CONTACT_NUMBER": ("companyContactNumber", "phoneNumber", "phoneNumber1",
                                       "contactNumber", "tel"),
}
# 채워지면 좋지만 **없어도 등록이 되는** 칸 — 「미매핑」으로 세지 않는다 (F34-3).
OPTIONAL_FIELDS = frozenset({"COUPANG_RETURN_ADDRESS_DETAIL"})

OUTBOUND_FIELD_CANDIDATES: Dict[str, tuple] = {
    "COUPANG_OUTBOUND_SHIPPING_PLACE_CODE": ("outboundShippingPlaceCode", "shippingPlaceCode",
                                             "outboundShippingPlaceId", "placeCode"),
}

# 사람이 고를 때 읽는 이름(라디오 한 줄). 없으면 코드만 보여 준다.
LABEL_CANDIDATES = ("shippingPlaceName", "placeName", "returnCenterName", "name", "companyName")


def _rows(payload: Any) -> List[dict]:
    """응답에서 **항목들**을 꺼낸다 — 감싼 키 이름을 모르니 **구조로** 찾는다.

    `{"data": [...]}`인지 `{"content": [...]}`인지 모른다. 그래서 「dict들의 리스트」를
    찾는다. 이름을 찍으면 그게 발명이고, 틀리면 조용히 빈 목록이 된다.
    """
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    if all(not isinstance(v, (list, dict)) for v in payload.values()):
        return [payload]                      # 단건이 통째로 온 모양
    for value in payload.values():
        if isinstance(value, list) and value and all(isinstance(r, dict) for r in value):
            return value
        if isinstance(value, dict):
            nested = _rows(value)
            if nested:
                return nested
    return []


def _pick(row: dict, candidates) -> str:
    """후보 중 **실제로 있는** 키의 값. 없으면 빈 문자열(추측 0).

    F32-2 실측(2026-09-18, 「원문 보기」): 반품지 row의 **최상위 키는 아홉 개뿐**이다 —
    `createdAt · deliverCode · deliverName · errorMessage · goodsflowStatus ·
    returnCenterCode · shippingPlaceName · usable · vendorId`.
    우편번호·주소·연락처는 **최상위에 없다.** 그래서 최상위만 보던 이 함수는 넷을 못 찾았다.

    → 최상위에서 못 찾으면 **한 단만** 내려간다(값이 dict이거나 list[dict]인 키).
      리스트는 0번부터, **첫 매치 채택**. 두 단 이상은 안 판다 — 깊이를 늘리면
      엉뚱한 가지에서 같은 이름을 주워 올 수 있고, 그건 매핑이 아니라 우연이다.

    **후보 사전은 손대지 않는다.** 하위 키 이름은 아직 미실측이다 — 지어내지 않는다.
    이 수리가 하는 일은 「같은 후보 이름을 한 단 더 넓은 자리에서 찾는다」까지다.
    """
    for key in candidates:
        if key in row and str(row[key] or "").strip():
            return str(row[key]).strip()
    # 한 단 아래 — 순서는 dict 삽입 순서 그대로(응답이 준 순서가 곧 우선순위다).
    for value in row.values():
        for child in ([value] if isinstance(value, dict) else
                      [c for c in value if isinstance(c, dict)]
                      if isinstance(value, list) else []):
            for key in candidates:
                if key in child and str(child[key] or "").strip():
                    return str(child[key]).strip()
    return ""


def _label(row: dict) -> str:
    return _pick(row, LABEL_CANDIDATES)


def _map_row(row: dict, candidates: Dict[str, tuple]) -> dict:
    """`{우리 칸: 값}` — 채운 칸만. 못 채운 칸은 아예 넣지 않는다(빈 값으로 덮지 않게)."""
    out = {}
    for env, cands in candidates.items():
        val = _pick(row, cands)
        if val:
            out[env] = val
    return out


def _uploader(account: str):
    from src.uploaders.coupang_uploader import CoupangUploader
    return CoupangUploader(account=account) if account else CoupangUploader()


def _fetch_one(up, path: str, candidates: Dict[str, tuple]) -> dict:
    """한 경로. `{ok, entries, raw_keys, error}` — 실패 사유는 **응답 원문 그대로**."""
    payload = up._api_request("GET", path)          # 서명·릴레이·4xx 원문은 여기가 정본
    if isinstance(payload, dict) and payload.get("error"):
        return {"ok": False, "entries": [], "raw_keys": [], "error": str(payload["error"])}
    rows = _rows(payload)
    entries = []
    for i, row in enumerate(rows):
        flat = _flatten(row)
        entries.append({
            "index": i,
            "label": _label(row),
            "values": _map_row(row, candidates),
            # 화면이 **원문 키를 나열**한다 — 우리가 못 고른 칸을 사람이 고를 수 있게.
            "raw": flat,
        })
    raw_keys = sorted({k for e in entries for k in e["raw"].keys()})
    return {"ok": True, "entries": entries, "raw_keys": raw_keys, "error": ""}


def _flatten(row: dict) -> dict:
    """중첩을 `부모키[i].자식키`로 펴서 **문자열 값을 전부** 내놓는다 (F32-2).

    예전엔 `isinstance(v, (list, dict))`인 값을 **버렸다.** 그래서 우편번호·주소·연락처가
    하위에 들어 있던 반품지 응답에서, 화면 「원문 보기」에 그 키들이 **아예 안 보였다** —
    우리가 못 고른 것을 사람이 고를 수도 없었다(그러라고 만든 자리인데).

    한 단만 편다. `_pick`이 파는 깊이와 **같은 깊이**여야 한다 —
    화면에 보이는데 못 고르거나, 고를 수 있는데 안 보이는 일이 없게.
    """
    out = {}
    for key, value in (row or {}).items():
        if isinstance(value, dict):
            for ck, cv in value.items():
                if not isinstance(cv, (list, dict)):
                    out[f"{key}.{ck}"] = "" if cv is None else cv
        elif isinstance(value, list):
            for i, child in enumerate(value):
                if isinstance(child, dict):
                    for ck, cv in child.items():
                        if not isinstance(cv, (list, dict)):
                            out[f"{key}[{i}].{ck}"] = "" if cv is None else cv
                elif not isinstance(child, list):
                    out[f"{key}[{i}]"] = "" if child is None else child
        else:
            out[key] = "" if value is None else value
    return out


def fetch(account: str = "") -> dict:
    """반품지·출고지를 불러온다. **저장하지 않는다** — 고르는 것은 사람이다.

    돌려주는 것:
      `{ok, account, vendor_id, return_centers{...}, outbound_places{...}, unmapped: [...]}`
    """
    from src.seller_console.market_cred_view import resolve_upload_account
    acct = str(account or "").strip() or resolve_upload_account()
    try:
        up = _uploader(acct)
    except Exception as exc:
        logger.warning("[쿠팡 불러오기] 업로더 생성 실패: %s", exc)
        return {"ok": False, "reason": "쿠팡 자격을 읽지 못했습니다.", "account": acct}

    vendor_id = str(getattr(up, "vendor_id", "") or "").strip()
    if not (getattr(up, "access_key", "") and getattr(up, "secret_key", "") and vendor_id):
        # **가짜로 불러온 척 하지 않는다.** 자격이 없으면 부를 수 없다.
        return {"ok": False, "account": acct, "vendor_id": vendor_id,
                "reason": "쿠팡 API 키와 업체코드를 먼저 저장해 주세요."}

    ret = _fetch_one(up, RETURN_CENTERS_PATH.format(vendor_id=vendor_id),
                     RETURN_FIELD_CANDIDATES)
    out = _fetch_one(up, OUTBOUND_PLACES_PATH + OUTBOUND_PLACES_QUERY,
                     OUTBOUND_FIELD_CANDIDATES)

    # 우리가 못 채운 칸 — 화면이 「이 칸은 직접」이라고 말할 수 있게 이름으로 올린다.
    filled = set()
    for block in (ret, out):
        for e in block.get("entries") or []:
            filled |= set(e["values"])
    # F34-3: 상세주소는 **선택 칸**이다(화면 라벨도 「(선택)」). 못 채웠다고 「미매핑」에
    #   세면, 다 채워진 응답에도 빨간 칸이 하나 남아 사람이 없는 값을 찾게 된다.
    wanted = ((set(RETURN_FIELD_CANDIDATES) | set(OUTBOUND_FIELD_CANDIDATES))
              - OPTIONAL_FIELDS)
    return {"ok": bool(ret["ok"] or out["ok"]), "account": acct, "vendor_id": vendor_id,
            "return_centers": ret, "outbound_places": out,
            "unmapped": sorted(wanted - filled)}
