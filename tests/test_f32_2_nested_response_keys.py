"""F32-2 계약 — 최상위에 없는 값은 한 단 아래 있었다.

## 실측 (오너 2026-09-18, 마켓 연동 「원문 보기」)

반품지 row의 **최상위 키는 아홉 개뿐**이었다:

    createdAt · deliverCode · deliverName · errorMessage · goodsflowStatus
    returnCenterCode · shippingPlaceName · usable · vendorId

우편번호·주소·연락처는 **최상위에 없다.** 그런데 `_pick`은 최상위만 봤고,
`_fetch_one`의 `raw`는 `list`/`dict` 값을 **통째로 버렸다.**

  → 우리가 못 고른 넷이 **화면에도 안 보였다.** 「원문 보기」는 사람이 직접 고르라고
    만든 자리인데, 고를 재료 자체가 화면에 없었다.

> **못 고른 것을 보여 주지 않으면, 그건 못 고른 게 아니라 숨긴 것이다.**

## 이 판이 하는 것 / 안 하는 것

**하는 것** — 같은 후보 이름을 **한 단 더 넓은 자리**에서 찾고, `raw`를
`부모키[i].자식키`로 펴서 문자열 값을 전부 내놓는다. 출고지에 실측이 준
`?pageNum=1&pageSize=50`을 붙인다.

**안 하는 것** — **후보 사전에 새 이름을 넣지 않는다.** 하위 키 이름은 아직 미실측이다.
줄지 않은 칸은 `raw`에 값이 있는데 후보 이름이 안 맞는 것이고, 그건 **다음 커밋**이다
(실측 키 이름을 받고 나서).

라이브 호출 0 — `_api_request`를 목으로 세운다.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

# 오너 실측 최상위 키 아홉 개 — 여기에 ZIP/ADDRESS/CONTACT가 **없다**는 게 이 트랙의 출발점.
LIVE_TOP_KEYS = {
    "createdAt": "2026-09-18", "deliverCode": "KGB", "deliverName": "고가배송",
    "errorMessage": "", "goodsflowStatus": "OK", "returnCenterCode": "1000274592",
    "shippingPlaceName": "장말로", "usable": True, "vendorId": "A01381223",
}


def _fake_up(return_payload, outbound_payload=None):
    class _Up:
        access_key, secret_key, vendor_id = "a", "s", "A01381223"
        seen = []

        def _api_request(self, method, path, data=None):
            _Up.seen.append((method, path))
            return return_payload if "returnShippingCenters" in path else (outbound_payload or [])
    _Up.seen = []
    return _Up()


# ---------------------------------------------------------------------------
# ① 한 단 내려가는 탐색
# ---------------------------------------------------------------------------

def test_a_value_one_level_down_is_found():
    """★ **F32-2의 판정 지점** — 최상위에 없으면 한 단 아래에서 같은 후보로 찾는다."""
    from src.seller_console import coupang_shipping_lookup as L
    row = dict(LIVE_TOP_KEYS)
    row["place"] = {"returnZipCode": "06000", "returnAddress": "서울시 강남구 1"}
    with patch.object(L, "_uploader", lambda a: _fake_up({"data": [row]})):
        out = L.fetch("gogane")
    vals = out["return_centers"]["entries"][0]["values"]
    assert vals["COUPANG_RETURN_ZIP_CODE"] == "06000"
    assert vals["COUPANG_RETURN_ADDRESS"] == "서울시 강남구 1"
    assert vals["COUPANG_RETURN_CENTER_CODE"] == "1000274592", "최상위 매칭이 깨졌다"


def test_a_list_of_dicts_is_searched_from_the_first_element():
    """리스트면 0번부터, **첫 매치 채택**."""
    from src.seller_console import coupang_shipping_lookup as L
    row = dict(LIVE_TOP_KEYS)
    row["placeAddresses"] = [{"returnZipCode": "11111"}, {"returnZipCode": "99999"}]
    with patch.object(L, "_uploader", lambda a: _fake_up({"data": [row]})):
        out = L.fetch("gogane")
    assert out["return_centers"]["entries"][0]["values"]["COUPANG_RETURN_ZIP_CODE"] == "11111"


def test_the_top_level_still_wins_over_a_child():
    """최상위가 있으면 최상위다 — 내려가는 건 **없을 때만**."""
    from src.seller_console import coupang_shipping_lookup as L
    row = dict(LIVE_TOP_KEYS)
    row["returnZipCode"] = "top"
    row["place"] = {"returnZipCode": "child"}
    with patch.object(L, "_uploader", lambda a: _fake_up({"data": [row]})):
        out = L.fetch("gogane")
    assert out["return_centers"]["entries"][0]["values"]["COUPANG_RETURN_ZIP_CODE"] == "top"


def test_we_do_not_dig_deeper_than_one_level():
    """두 단 아래는 안 판다 — 깊이를 늘리면 엉뚱한 가지에서 같은 이름을 주워 온다."""
    from src.seller_console import coupang_shipping_lookup as L
    row = dict(LIVE_TOP_KEYS)
    row["a"] = {"b": {"returnZipCode": "깊은곳"}}
    with patch.object(L, "_uploader", lambda a: _fake_up({"data": [row]})):
        out = L.fetch("gogane")
    assert "COUPANG_RETURN_ZIP_CODE" not in out["return_centers"]["entries"][0]["values"]


def test_candidate_names_are_never_invented():
    """★ **후보 이름을 지어내지 않는다** — 오너가 준 이름과 실측된 이름만 쓴다.

    F32-2에서는 「이 판에선 사전을 아예 안 건드린다」로 못 박았었다.
    F34-3에서 오너가 **`addressDetail`은 기본주소가 아니다**라고 지목했고,
    상세주소 후보 이름(`returnAddressDetail`)도 함께 줬다 — 그건 실측이지 발명이 아니다.
    그래서 계약을 **의도**로 옮긴다(최신 우선): 「안 건드린다」가 아니라 **「안 지어낸다」**.
    """
    from src.seller_console import coupang_shipping_lookup as L
    assert L.RETURN_FIELD_CANDIDATES["COUPANG_RETURN_ZIP_CODE"] == (
        "returnZipCode", "zipCode", "postCode", "postalCode")
    # F34-3: 상세주소는 기본주소 후보에서 빠지고 **자기 칸**으로 갔다.
    assert L.RETURN_FIELD_CANDIDATES["COUPANG_RETURN_ADDRESS"] == (
        "returnAddress", "address", "roadAddress")
    assert L.RETURN_FIELD_CANDIDATES["COUPANG_RETURN_ADDRESS_DETAIL"] == (
        "returnAddressDetail",)
    assert L.OUTBOUND_FIELD_CANDIDATES["COUPANG_OUTBOUND_SHIPPING_PLACE_CODE"] == (
        "outboundShippingPlaceCode", "shippingPlaceCode",
        "outboundShippingPlaceId", "placeCode")
    # 후보는 전부 **우리 env 이름**을 키로 갖고, 값은 쿠팡이 준 이름뿐이다.
    for env in L.RETURN_FIELD_CANDIDATES:
        assert env.startswith("COUPANG_"), env


def test_the_live_top_level_shape_still_maps_what_it_can():
    """실측 그대로(하위 없음)면 **찾을 수 있는 것만** 찾고 나머지는 `unmapped`."""
    from src.seller_console import coupang_shipping_lookup as L
    with patch.object(L, "_uploader", lambda a: _fake_up({"data": [dict(LIVE_TOP_KEYS)]})):
        out = L.fetch("gogane")
    vals = out["return_centers"]["entries"][0]["values"]
    assert vals["COUPANG_RETURN_CENTER_CODE"] == "1000274592"
    assert vals["COUPANG_RETURN_CHARGE_NAME"] == "장말로"      # shippingPlaceName 후보
    for env in ("COUPANG_RETURN_ZIP_CODE", "COUPANG_RETURN_ADDRESS",
                "COUPANG_COMPANY_CONTACT_NUMBER"):
        assert env not in vals
        assert env in out["unmapped"], env


# ---------------------------------------------------------------------------
# ② raw 평탄화 — 못 고른 것을 사람이 고를 수 있게
# ---------------------------------------------------------------------------

def test_nested_values_appear_in_raw_with_a_readable_path():
    """★ `부모키[i].자식키` — 예전엔 이 값들이 **통째로 버려졌다**."""
    from src.seller_console import coupang_shipping_lookup as L
    row = dict(LIVE_TOP_KEYS)
    row["place"] = {"zip": "06000"}
    row["contacts"] = [{"phone": "02-1234-5678"}, {"phone": "010-0000-0000"}]
    with patch.object(L, "_uploader", lambda a: _fake_up({"data": [row]})):
        out = L.fetch("gogane")
    raw = out["return_centers"]["entries"][0]["raw"]
    assert raw["place.zip"] == "06000"
    assert raw["contacts[0].phone"] == "02-1234-5678"
    assert raw["contacts[1].phone"] == "010-0000-0000"
    assert raw["returnCenterCode"] == "1000274592", "최상위가 사라졌다"


def test_raw_keys_list_includes_the_nested_paths():
    """`raw_keys`도 하위를 담는다 — 화면이 그걸 나열한다."""
    from src.seller_console import coupang_shipping_lookup as L
    row = dict(LIVE_TOP_KEYS)
    row["place"] = {"zip": "06000"}
    with patch.object(L, "_uploader", lambda a: _fake_up({"data": [row]})):
        out = L.fetch("gogane")
    assert "place.zip" in out["return_centers"]["raw_keys"]


def test_flatten_and_pick_go_the_same_depth():
    """★ 보이는데 못 고르거나, 고를 수 있는데 안 보이는 일이 없게 — **같은 깊이**다."""
    from src.seller_console import coupang_shipping_lookup as L
    deep = {"a": {"b": {"returnZipCode": "깊은곳"}}}
    flat = L._flatten(deep)
    assert not any("returnZipCode" in k for k in flat), "raw는 두 단을 편다"
    assert L._pick(deep, ("returnZipCode",)) == "", "_pick은 두 단을 안 판다"


def test_a_scalar_list_is_not_lost():
    """문자열 리스트도 값이다 — 버리면 사람이 못 본다."""
    from src.seller_console import coupang_shipping_lookup as L
    flat = L._flatten({"tags": ["A", "B"], "name": "x"})
    assert flat["tags[0]"] == "A" and flat["tags[1]"] == "B" and flat["name"] == "x"


# ---------------------------------------------------------------------------
# ③ 출고지 쿼리 — 400 원문이 준 이름 그대로
# ---------------------------------------------------------------------------

def test_outbound_is_called_with_the_measured_query():
    """★ 실측 400이 준 이름 그대로 — `pageNum & pageSize`."""
    from src.seller_console import coupang_shipping_lookup as L
    up = _fake_up({"data": []}, [])
    with patch.object(L, "_uploader", lambda a: up):
        L.fetch("gogane")
    outbound = [p for _m, p in type(up).seen if "shipping-place/outbound" in p]
    assert outbound, "출고지를 부르지 않았다"
    assert outbound[0].endswith("?pageNum=1&pageSize=50"), outbound[0]


def test_the_query_is_a_separate_constant_from_the_path():
    """경로 상수는 **정본 그대로** 두고, 실측으로 얻은 쿼리만 따로 붙인다."""
    from src.seller_console import coupang_shipping_lookup as L
    assert L.OUTBOUND_PLACES_PATH == (
        "/v2/providers/marketplace_openapi/apis/api/v2/vendor/shipping-place/outbound")
    assert L.OUTBOUND_PLACES_QUERY == "?pageNum=1&pageSize=50"


def test_the_return_centers_call_keeps_no_query():
    """반품지는 파라미터 없이 **실제로 성공했다**(1건) — 그래서 안 붙인다."""
    from src.seller_console import coupang_shipping_lookup as L
    up = _fake_up({"data": [dict(LIVE_TOP_KEYS)]})
    with patch.object(L, "_uploader", lambda a: up):
        L.fetch("gogane")
    ret = [p for _m, p in type(up).seen if "returnShippingCenters" in p]
    assert ret and "?" not in ret[0], ret


def test_a_400_still_comes_through_verbatim():
    """상한이 다르면 **다음 400 원문이 알려 준다** — 그 문장이 그대로 화면에 뜬다."""
    from src.seller_console import coupang_shipping_lookup as L
    said = ('쿠팡 거부 — GET /v2/... status=400 body={"code":"INVALID_ARGUMENT",'
            '"message":"pageSize must be less than or equal to 10"}')

    class _Up:
        access_key, secret_key, vendor_id = "a", "s", "A01381223"

        def _api_request(self, method, path, data=None):
            return {"error": said} if "outbound" in path else {"data": []}

    with patch.object(L, "_uploader", lambda a: _Up()):
        out = L.fetch("gogane")
    assert out["outbound_places"]["error"] == said
    assert "less than or equal to 10" in out["outbound_places"]["error"]


def test_the_signature_covers_the_query_string():
    """서명에 **쿼리가 들어간다** — 그래서 호출부가 쿼리를 경로에 붙여야 맞는다.

    ※ F37(2026-09-19): 이 계약은 원래 **docstring에 「query string 포함」이라 적혀 있나**를
      읽었다. 그 문장은 참이었고, 그런데도 라이브는 401이었다 — 쿼리는 포함하되
      **`?`는 빼야** 한다는 걸 아무도 안 쟀기 때문이다.
      주석을 읽는 계약은 코드가 틀려도 초록이다. **서명되는 문자열을 직접 잰다.**
      `?` 제거 자체는 `test_f37_hmac_query_signature.py`가 정본이다.
    """
    from src.uploaders.coupang_uploader import CoupangUploader
    up = CoupangUploader.__new__(CoupangUploader)
    up.secret_key = "sk"
    a = up._generate_hmac_signature("GET", "/v2/x/outbound?pageNum=1", "260919T000000Z")
    b = up._generate_hmac_signature("GET", "/v2/x/outbound?pageNum=2", "260919T000000Z")
    assert a != b, "쿼리가 바뀌어도 서명이 같다 = 쿼리를 안 서명한다"
    look = (ROOT / "src/seller_console/coupang_shipping_lookup.py").read_text(encoding="utf-8")
    body = "\n".join(l for l in look.splitlines() if not l.strip().startswith("#"))
    assert "OUTBOUND_PLACES_PATH + OUTBOUND_PLACES_QUERY" in body


# ---------------------------------------------------------------------------
# ④ 채점 기준 — unmapped가 줄어야 한다
# ---------------------------------------------------------------------------

def test_unmapped_shrinks_once_the_values_are_reachable():
    """★ 사람이 받는 것: 하위에 값이 있으면 **unmapped 4개가 줄어든다**."""
    from src.seller_console import coupang_shipping_lookup as L
    row = dict(LIVE_TOP_KEYS)
    row["place"] = {"returnZipCode": "06000", "returnAddress": "서울시 강남구 1",
                    "companyContactNumber": "02-1234-5678"}
    outb = [{"place": {"outboundShippingPlaceCode": 7437895}}]
    with patch.object(L, "_uploader", lambda a: _fake_up({"data": [row]}, outb)):
        out = L.fetch("gogane")
    assert out["unmapped"] == [], out["unmapped"]


def test_what_stays_unmapped_is_still_visible_in_raw():
    """줄지 않은 칸도 **값은 화면에 있다** — 그게 다음 커밋의 근거가 된다."""
    from src.seller_console import coupang_shipping_lookup as L
    row = dict(LIVE_TOP_KEYS)
    row["place"] = {"낯선우편번호키": "06000"}          # 후보에 없는 이름
    with patch.object(L, "_uploader", lambda a: _fake_up({"data": [row]})):
        out = L.fetch("gogane")
    assert "COUPANG_RETURN_ZIP_CODE" in out["unmapped"]
    assert out["return_centers"]["entries"][0]["raw"]["place.낯선우편번호키"] == "06000"
