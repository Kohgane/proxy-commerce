"""F29-4 계약 — 쿠팡에서 불러오되, **없는 것을 지어내지 않는다.**

## 경로 (오너 제공 공식 목록 2026-09-16)

    반품지 목록 조회  GET /v2/providers/openapi/apis/api/v5/vendors/{vendorId}/returnShippingCenters
    반품지 단건 조회  GET /v2/providers/openapi/apis/api/v3/return/shipping-places/center-code
    출고지 조회      GET /v2/providers/marketplace_openapi/apis/api/v2/vendor/shipping-place/outbound

내가 검색으로 본 스니펫은 경로에 `v5`, 예시에 `v4`가 나와 **서로 달랐다.** 그래서 안 넣었고,
오너가 정본을 줬다. 이 계약이 그 문자열을 **글자 그대로** 못박는다 — 다음에 누가
「아마 v4」로 고치면 빨개진다.

## 이 파일이 재는 것

  ① 경로 문자열이 정확한가(글자 단위).
  ② 서명·헤더를 **새로 쓰지 않았는가** — `_api_request`가 정본이다.
  ③ 응답에 **실제로 있는 키만** 매핑하는가. 없는 칸은 비우고 그 사실을 말하는가.
  ④ 쿼리 파라미터를 붙이지 않는가(미확인). 4xx면 **응답 원문**을 그대로 올리는가.
  ⑤ 자격이 없으면 **불러온 척 하지 않는가.**

**라이브 호출 0** — `_api_request`를 목으로 세운다(쿠팡에 한 번도 나가지 않는다).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
MOD = "src.seller_console.coupang_shipping_lookup"


# ---------------------------------------------------------------------------
# ① 경로 — 글자 그대로
# ---------------------------------------------------------------------------

def test_paths_are_exactly_what_the_owner_gave():
    """★ 오너 제공 공식 목록과 **글자 단위로** 같아야 한다."""
    from src.seller_console import coupang_shipping_lookup as L
    assert L.RETURN_CENTERS_PATH == (
        "/v2/providers/openapi/apis/api/v5/vendors/{vendor_id}/returnShippingCenters")
    assert L.RETURN_CENTER_ONE_PATH == (
        "/v2/providers/openapi/apis/api/v3/return/shipping-places/center-code")
    assert L.OUTBOUND_PLACES_PATH == (
        "/v2/providers/marketplace_openapi/apis/api/v2/vendor/shipping-place/outbound")


def test_return_center_path_carries_the_vendor_id():
    """업체코드는 계정별이다 — 고정값이 박혀 있으면 한 계정만 동작한다."""
    from src.seller_console import coupang_shipping_lookup as L
    built = L.RETURN_CENTERS_PATH.format(vendor_id="A01504840")
    assert built.endswith("/vendors/A01504840/returnShippingCenters")
    assert "A01381223" not in L.RETURN_CENTERS_PATH


def test_no_query_parameters_are_invented():
    """쿼리 파라미터(페이지 등)는 **미확인** — 붙이지 않는다."""
    from src.seller_console import coupang_shipping_lookup as L
    for path in (L.RETURN_CENTERS_PATH, L.RETURN_CENTER_ONE_PATH, L.OUTBOUND_PLACES_PATH):
        assert "?" not in path, path


# ---------------------------------------------------------------------------
# ② 서명 — 새로 쓰지 않았다
# ---------------------------------------------------------------------------

def test_signing_is_not_reimplemented():
    """HMAC을 여기서 다시 만들면 **두 벌**이 된다 — 한쪽만 고치면 그날 등록이 죽는다."""
    src = (ROOT / "src/seller_console/coupang_shipping_lookup.py").read_text(encoding="utf-8")
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    for leak in ("hmac.new", "HmacSHA256", "hashlib.sha256", "Authorization"):
        assert leak not in body, f"서명을 다시 쓰고 있다: {leak}"
    assert "_api_request" in body, "정본 요청기를 안 쓴다"


def test_the_call_goes_through_the_uploaders_request():
    """실제로 `_api_request('GET', …)`로 나간다 — 목이 그걸 확인한다."""
    from src.seller_console import coupang_shipping_lookup as L
    seen = []

    class _Up:
        access_key, secret_key, vendor_id = "a", "s", "A01381223"

        def _api_request(self, method, path, data=None):
            seen.append((method, path))
            return []

    with patch.object(L, "_uploader", lambda acct: _Up()):
        L.fetch("gogane")
    assert ("GET", "/v2/providers/openapi/apis/api/v5/vendors/A01381223/returnShippingCenters") in seen
    assert ("GET", "/v2/providers/marketplace_openapi/apis/api/v2/vendor/shipping-place/outbound") in seen
    assert all(m == "GET" for m, _ in seen), "조회인데 GET이 아니다"


# ---------------------------------------------------------------------------
# ③ 매핑 — 있는 키만
# ---------------------------------------------------------------------------

def _fake_uploader(return_payload, outbound_payload):
    class _Up:
        access_key, secret_key, vendor_id = "a", "s", "A01381223"

        def _api_request(self, method, path, data=None):
            return return_payload if "returnShippingCenters" in path else outbound_payload
    return _Up()


def test_only_keys_that_exist_are_mapped():
    """★ **발명 금지의 판정 지점** — 응답에 없는 칸은 채우지 않는다."""
    from src.seller_console import coupang_shipping_lookup as L
    ret = {"data": [{"returnCenterCode": "1000274592", "returnZipCode": "06000",
                     "shippingPlaceName": "고가네 반품지"}]}      # 주소·담당자·연락처 없음
    with patch.object(L, "_uploader", lambda a: _fake_uploader(ret, [])):
        out = L.fetch("gogane")
    vals = out["return_centers"]["entries"][0]["values"]
    assert vals["COUPANG_RETURN_CENTER_CODE"] == "1000274592"
    assert vals["COUPANG_RETURN_ZIP_CODE"] == "06000"
    assert "COUPANG_RETURN_ADDRESS" not in vals, "없는 값을 지어냈다"
    assert "COUPANG_COMPANY_CONTACT_NUMBER" not in vals
    assert "COUPANG_RETURN_ADDRESS" in out["unmapped"], "못 채운 칸을 말하지 않는다"


def test_raw_keys_are_handed_to_the_screen():
    """우리가 못 고른 칸을 사람이 고를 수 있게 **원문 키를 그대로** 올린다."""
    from src.seller_console import coupang_shipping_lookup as L
    ret = {"data": [{"returnCenterCode": "C1", "낯선키": "낯선값", "placeAddr": "서울"}]}
    with patch.object(L, "_uploader", lambda a: _fake_uploader(ret, [])):
        out = L.fetch("gogane")
    entry = out["return_centers"]["entries"][0]
    assert entry["raw"]["낯선키"] == "낯선값"
    assert entry["raw"]["placeAddr"] == "서울"
    assert "낯선키" in out["return_centers"]["raw_keys"]


def test_rows_are_found_by_shape_not_by_a_guessed_wrapper_name():
    """감싼 키 이름을 모른다 — `data`든 `content`든 **구조로** 찾는다."""
    from src.seller_console import coupang_shipping_lookup as L
    for payload in ({"content": [{"returnCenterCode": "C1"}]},
                    [{"returnCenterCode": "C1"}],
                    {"result": {"items": [{"returnCenterCode": "C1"}]}}):
        with patch.object(L, "_uploader", lambda a, p=payload: _fake_uploader(p, [])):
            out = L.fetch("gogane")
        got = out["return_centers"]["entries"]
        assert len(got) == 1 and got[0]["values"]["COUPANG_RETURN_CENTER_CODE"] == "C1", payload


def test_several_entries_are_all_offered():
    """여러 개면 **다 보여 준다** — 하나를 골라 주는 건 사람 몫이다."""
    from src.seller_console import coupang_shipping_lookup as L
    ret = {"data": [{"returnCenterCode": "C1", "shippingPlaceName": "본사"},
                    {"returnCenterCode": "C2", "shippingPlaceName": "창고"}]}
    with patch.object(L, "_uploader", lambda a: _fake_uploader(ret, [])):
        out = L.fetch("gogane")
    entries = out["return_centers"]["entries"]
    assert [e["label"] for e in entries] == ["본사", "창고"]


def test_outbound_code_is_mapped_from_its_own_block():
    from src.seller_console import coupang_shipping_lookup as L
    outb = {"data": [{"outboundShippingPlaceCode": 7437895, "placeName": "출고지"}]}
    with patch.object(L, "_uploader", lambda a: _fake_uploader([], outb)):
        out = L.fetch("gogane")
    vals = out["outbound_places"]["entries"][0]["values"]
    assert vals["COUPANG_OUTBOUND_SHIPPING_PLACE_CODE"] == "7437895"


# ---------------------------------------------------------------------------
# ④ 실패 — 원문 그대로
# ---------------------------------------------------------------------------

def test_a_4xx_body_is_carried_through_verbatim():
    """★ 400이면 **그 문장 그대로** 올린다 — 다음 판에서 쿼리 파라미터를 채울 근거다."""
    from src.seller_console import coupang_shipping_lookup as L
    said = "쿠팡 거부 — GET /v2/... status=400 body={\"message\":\"pageNum is required\"}"

    class _Up:
        access_key, secret_key, vendor_id = "a", "s", "A01381223"

        def _api_request(self, method, path, data=None):
            return {"error": said}

    with patch.object(L, "_uploader", lambda a: _Up()):
        out = L.fetch("gogane")
    assert out["return_centers"]["error"] == said
    assert "pageNum is required" in out["return_centers"]["error"]


def test_no_credentials_means_we_do_not_pretend_to_have_asked():
    """자격이 없으면 **부를 수 없다** — 빈 목록을 「없음」이라 부르지 않는다."""
    from src.seller_console import coupang_shipping_lookup as L

    class _Up:
        access_key, secret_key, vendor_id = "", "", ""

        def _api_request(self, *a, **k):        # pragma: no cover - 불려선 안 된다
            raise AssertionError("자격이 없는데 쿠팡을 불렀다")

    with patch.object(L, "_uploader", lambda a: _Up()):
        out = L.fetch("gogane")
    assert out["ok"] is False
    assert "API 키" in out["reason"]


# ---------------------------------------------------------------------------
# ⑤ 라우트 — 저장하지 않는다, 사유는 덮이지 않는다
# ---------------------------------------------------------------------------

def _client():
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u1"
        s["user_email"] = "a@b.c"
    return c


def test_route_returns_entries_and_saves_nothing():
    """불러오기는 **고르기 전 단계**다 — 저장은 기존 「저장」이 한 자리에서."""
    import src.seller_console.views as V
    from src.seller_console import market_credentials as mc
    payload = {"ok": True, "account": "gogane", "vendor_id": "A01381223",
               "return_centers": {"ok": True, "entries": [], "raw_keys": [], "error": ""},
               "outbound_places": {"ok": True, "entries": [], "raw_keys": [], "error": ""},
               "unmapped": []}
    with patch("src.seller_console.coupang_shipping_lookup.fetch", return_value=payload), \
         patch.object(mc, "save", side_effect=AssertionError("불러오기가 저장했다")):
        r = _client().post("/seller/markets/connect/coupang/lookup", json={})
    assert r.status_code == 200, r.get_data(as_text=True)[:200]
    assert r.get_json()["vendor_id"] == "A01381223"


def test_route_passes_the_reason_through_without_rewriting_it():
    """F28 규율 — 화면의 친절 처리기가 덮지 못하게 `user_message`를 단다."""
    payload = {"ok": False, "account": "gogane", "vendor_id": "A01381223",
               "return_centers": {"ok": False, "entries": [], "raw_keys": [],
                                  "error": "쿠팡 거부 — status=400 body={\"message\":\"x\"}"},
               "outbound_places": {"ok": False, "entries": [], "raw_keys": [], "error": ""},
               "unmapped": []}
    with patch("src.seller_console.coupang_shipping_lookup.fetch", return_value=payload):
        r = _client().post("/seller/markets/connect/coupang/lookup", json={})
    assert r.status_code == 409
    d = r.get_json()
    assert d["user_message"] is True
    assert "status=400" in d["error"]


def test_route_requires_login():
    """미인증이면 401.

    ※ `_AUTH_ENABLED`는 **import 시점 상수**다 — 테스트에서 env를 바꿔 봐야 안 바뀐다
      (그렇게 썼다가 이 계약이 통과해 버렸다). 가드 자체를 세워서 잰다.
    """
    import src.seller_console.views as V
    from src.order_webhook import app
    app.config["TESTING"] = True
    with patch.object(V, "_check_auth", return_value=False):
        r = app.test_client().post("/seller/markets/connect/coupang/lookup", json={})
    assert r.status_code == 401, r.status_code


def test_screen_has_the_button_and_shows_raw_keys():
    tpl = (ROOT / "src/seller_console/templates/markets_connect.html").read_text(encoding="utf-8")
    body = "\n".join(l for l in tpl.splitlines() if not l.strip().startswith("//"))
    assert 'data-action="coupang-lookup"' in body
    assert "쿠팡에서 출고지·반품지 불러오기" in body
    assert 'type="radio"' in body, "여러 개일 때 고를 수 없다"
    assert "원문 보기" in body, "우리가 못 고른 칸을 사람이 볼 수 없다"
    assert "lookup-apply" in body


def test_no_live_call_escapes_this_file():
    """이 계약이 쿠팡에 **한 번도** 나가지 않는다.

    ※ 처음엔 자기 소스에서 문자열을 찾게 썼더니 **자기 assert 줄을 읽고 빨개졌다**
      (이 계열 다섯 번째 — C-F17b·D1·F23·F28에 이어). 소스를 읽지 말고
      **import한 것**으로 잰다: 네트워크 라이브러리를 아예 안 들여온다.
    """
    import ast
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    for net in ("requests", "http", "urllib", "socket", "httpx"):
        assert net not in imported, f"네트워크 라이브러리를 들여왔다: {net}"
