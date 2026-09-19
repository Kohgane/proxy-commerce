"""F37 계약 — 쿠팡 CEA 서명에서 `?`를 뺀다.

## 실측 (오너 2026-09-19, 라이브)

| 경로 | 결과 |
|---|---|
| 반품지 `…/v5/vendors/{id}/returnShippingCenters` (쿼리 **없음**) | **200** |
| 출고지 `…/shipping-place/outbound?pageNum=1&pageSize=50` | **401 Invalid signature** |

갈린 것은 **쿼리가 있느냐**뿐이었다. 우리는 `url_path`를 통째로 이어 붙였고 거기엔 `?`가
들어 있었다. 쿠팡은 `?`를 **빼고** 서명한다(`datetime + method + path + query`).
쿼리 없는 경로는 두 규칙이 **같은 답**을 내서 200이었고, 쿼리가 붙는 순간에만 어긋났다.

> ★★★ **쿼리 없는 경로에서 통과한 서명은 「서명이 맞다」의 증거가 아니다.**
> 두 규칙이 같은 답을 내는 입력에서만 재 본 것이다.

## 왜 계약이 이걸 못 잡았나 — 목이 서명을 검증한 척했다

기존 계약들은 `_api_request`를 목으로 세우고 **200을 돌려주게** 해 놓고 「통과」를 봤다.
목은 서명을 검증하지 않는다. **어떤 문자열을 서명하든 200이 나온다.**
그러니 그 초록은 「서명이 맞다」가 아니라 「우리가 200이라고 답하게 시켰다」였다.

또 하나는 **주석을 읽는 계약**이었다(`test_the_signature_covers_the_query_string`):
docstring에 「query string 포함」이 있나만 봤다. 그 문장은 **참이었고 그래도 401이었다.**

> ★★ **목으로 세운 응답은 계약이 아니다. 재야 하는 것은 우리가 내보내는 바이트다.**

여기서는 **서명되는 문자열과 서명 값 자체**를 잰다. 라이브 호출 0.

※ 쿠팡 공개 문서의 예제 벡터는 쓰지 않았다 — 이 세션에서 `developers.coupang.com`이
  닿지 않는다(실측 `000`). **없는 벡터를 지어내지 않는다.** 대신 ①서명 대상 문자열을
  literal로 못박고 ②레포 안의 **독립 구현**(`coupang_adapter._hmac_sign`, 먼저 쓰인 코드로
  `?` 없이 잇는다)과 **교차 검증**한다.
"""
from __future__ import annotations

import hashlib
import hmac

import pytest

DATE = "260919T000000Z"
SECRET = "test-secret-key"
# 오너 실측이 401을 받은 그 경로.
OUTBOUND = ("/v2/providers/marketplace_openapi/apis/api/v2/vendor/shipping-place/outbound"
            "?pageNum=1&pageSize=50")
RETURNS = "/v2/providers/openapi/apis/api/v5/vendors/A01381223/returnShippingCenters"


@pytest.fixture
def up():
    from src.uploaders.coupang_uploader import CoupangUploader
    u = CoupangUploader.__new__(CoupangUploader)      # __init__은 네트워크·로깅을 탄다
    u.secret_key = SECRET
    u.access_key = "ak"
    u.vendor_id = "A01381223"
    return u


def _sign(message: str) -> str:
    return hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# ① 서명되는 문자열 — 물음표가 없다
# ---------------------------------------------------------------------------

def test_the_question_mark_is_not_signed(up):
    """★★ **F37의 판정 지점** — 서명 대상은 `date + method + path + query`, `?`는 없다."""
    expected = _sign(DATE + "GET"
                     + "/v2/providers/marketplace_openapi/apis/api/v2/vendor/shipping-place/outbound"
                     + "pageNum=1&pageSize=50")
    assert up._generate_hmac_signature("GET", OUTBOUND, DATE) == expected


def test_the_old_rule_would_have_differed(up):
    """★ 옛 규칙(`?` 포함)과 **다른 값**이다 — 같으면 이 판이 아무것도 안 한 것이다."""
    old = _sign(DATE + "GET" + OUTBOUND)
    assert up._generate_hmac_signature("GET", OUTBOUND, DATE) != old


def test_a_path_without_a_query_is_unchanged(up):
    """★★ **200이던 반품지를 깨지 않는다** — 쿼리가 없으면 옛 계산과 바이트 동일하다."""
    assert up._generate_hmac_signature("GET", RETURNS, DATE) == _sign(DATE + "GET" + RETURNS)


def test_only_the_first_question_mark_goes(up):
    """★ 쿼리 **값** 안의 `?`는 서명 대상 문자열의 일부다 — 지우면 또 어긋난다."""
    path = "/v2/x?q=a?b&r=c"
    assert up._generate_hmac_signature("GET", path, DATE) == _sign(DATE + "GET" + "/v2/xq=a?b&r=c")


def test_the_query_still_participates(up):
    """쿼리를 통째로 버린 것이 아니다 — 값이 바뀌면 서명도 바뀐다."""
    a = up._generate_hmac_signature("GET", "/v2/x?pageNum=1", DATE)
    b = up._generate_hmac_signature("GET", "/v2/x?pageNum=2", DATE)
    assert a != b


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_method_and_date_still_participate(up, method):
    sig = up._generate_hmac_signature(method, OUTBOUND, DATE)
    assert sig != up._generate_hmac_signature(method, OUTBOUND, "260919T000001Z")
    assert sig == _sign(DATE + method + OUTBOUND.replace("?", "", 1))


# ---------------------------------------------------------------------------
# ② 레포 안의 독립 구현과 교차 검증
# ---------------------------------------------------------------------------

def test_it_agrees_with_the_other_implementation_in_this_repo(up, monkeypatch):
    """★★ 같은 규칙을 **따로 쓴 코드**와 값이 같다 — 자기 자신을 다시 말한 게 아니다.

    `coupang_adapter._hmac_sign`은 이 판보다 **먼저** 쓰였고, 처음부터
    `f"{datetime_str}{method}{url_path}{query}"`로 이었다(호출부가 `?` 없이 넘긴다).
    어긋나 있던 건 업로더 쪽 하나였다.
    """
    from src.seller_console.market_adapters import coupang_adapter as CA

    monkeypatch.setenv("COUPANG_ACCESS_KEY", "ak")
    monkeypatch.setenv("COUPANG_SECRET_KEY", SECRET)
    path, query = OUTBOUND.split("?", 1)

    class _FixedDT:
        @staticmethod
        def now(tz=None):
            from datetime import datetime, timezone
            return datetime(2026, 9, 19, 0, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(CA, "datetime", _FixedDT)
    auth = CA._hmac_sign("GET", path, query)["Authorization"]
    other = auth.split("signature=")[1].strip()

    assert up._generate_hmac_signature("GET", OUTBOUND, DATE) == other


# ---------------------------------------------------------------------------
# ③ 우리가 실제로 내보내는 헤더 — 목은 네트워크만 막는다
# ---------------------------------------------------------------------------

def test_the_header_we_actually_send_carries_that_signature(up, monkeypatch):
    """★★ 목이 돌려주는 **응답**이 아니라, 목이 **받은 요청**을 잰다.

    목이 200을 준다고 서명이 맞는 게 아니다. 나간 `Authorization`에서 서명을 꺼내
    우리가 따로 계산한 값과 맞춰 본다 — 틀리면 그 자리에서 빨개진다.
    """
    import src.uploaders.coupang_uploader as CU

    seen = {}

    class _Resp:
        status_code = 200
        headers: dict = {}

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"data": []}

    def _capture(method, url, **kw):
        seen["method"], seen["url"] = method, url
        seen["headers"] = dict(kw.get("headers") or {})
        return _Resp()

    class _FixedDT:
        @staticmethod
        def now(tz=None):
            from datetime import datetime, timezone
            return datetime(2026, 9, 19, 0, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(CU, "relay_request", _capture)
    monkeypatch.setattr(CU, "datetime", _FixedDT)
    up._api_request("GET", OUTBOUND)

    assert seen["url"].endswith(OUTBOUND), seen["url"]
    auth = seen["headers"]["Authorization"]
    assert f"signed-date={DATE}" in auth
    sent = auth.split("signature=")[1].strip()
    expected = _sign(DATE + "GET" + OUTBOUND.replace("?", "", 1))
    assert sent == expected, "나간 서명이 CEA 규칙과 다르다 — 라이브에서 401이 난다"


def test_a_mocked_200_alone_proves_nothing():
    """★ 이 계약 파일이 **200을 성공의 근거로 쓰지 않는다**(오너 지시).

    목은 서명을 검증하지 않는다. 그래서 여기 어떤 테스트도 `ok is True`류로 끝내지 않는다 —
    전부 **서명 문자열/값**을 잰다.
    """
    import ast
    import pathlib

    src = pathlib.Path(__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for fn in [n for n in tree.body if isinstance(n, ast.FunctionDef)
               and n.name.startswith("test_")]:
        asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
        assert asserts, f"{fn.name}: 재는 것이 없다"
        body = ast.get_source_segment(src, fn) or ""
        if "status_code" in body:
            assert "signature=" in body, f"{fn.name}: 목 응답만 보고 통과시킨다"


# ---------------------------------------------------------------------------
# ④ 다른 곳은 손대지 않았다 (오너 지시)
# ---------------------------------------------------------------------------

def test_only_the_uploader_signer_changed():
    """오너 지시: **다른 곳은 손대지 않는다.** 나머지 서명 자리는 그대로다."""
    import inspect
    from src.pipeline import coupang_replicate as CR
    from src.seller_console.market_adapters import coupang_adapter as CA

    assert 'f"{datetime_str}{method}{url_path}{query}"' in inspect.getsource(CA._hmac_sign)
    assert "_coupang_sign" in inspect.getsource(CR)


def test_the_poller_orders_its_message_differently_and_is_left_alone():
    """★ 정직 기록 — 주문 폴러는 `method + date + ...` 순서다(여기와 **다르다**).

    이 판은 오너 지시대로 손대지 않는다. 실측 없이 고치면 그게 발명이고,
    지금 401이 난 것은 출고지 조회 하나다. 다만 **다르다는 사실은 남긴다** —
    주문 폴링이 언젠가 401을 내면 여기서부터 본다.
    """
    import inspect
    from src.order_alerts import coupang_order_poller as P

    src = inspect.getsource(P)
    assert 'f"{method}{datetime_str}{path}{query}"' in src
