"""F45 계약 — 마켓이 거부하면 화면도 실패라고 말한다.

## 실측 (2026-09-21)

`OrderSyncService.update_tracking`의 마지막 줄이 **`return sheets_ok or api_ok`**였다.
쿠팡이 `courierCode`를 거부해도 **우리 DB 저장만 성공하면 화면은 「성공」**.

> ★★★ **구매자에게 송장이 안 붙었는데 우리는 붙었다고 봤다.**
> 카나리 첫 주문에서 바로 밟히는 자리다 — 주문이 나야 송장이 있으니까.

그리고 그 앞에 하나 더 있었다: 일괄 송장 화면의 **자유 입력 문자열이 쿠팡에 그대로** 갔다.
셀러가 「CJ대한통운」이라고 치면 **그 한글이 `courierCode`로** 나갔다.

## 이 파일이 재는 것

| # | 계약 | 오너 지시 |
|---|---|---|
| 1 | 쿠팡 4xx → **화면 실패 + 응답 원문** | 「쿠팡 4xx 목 응답 → 화면 실패 + 원문」 |
| 2 | 한국어 택배사명 → **전송 0회** | 「한국어 택배사명 입력 → 전송 0회」 |
| 3 | `ok`는 **마켓 반영**만 뜻한다 | 「한 필드 두 뜻 금지」 |
| 4 | 우리 기록은 **따로** 표기된다 | 「DB는 '우리 쪽 기록됨, 마켓 미반영'」 |
| 5 | 모르는 택배사는 **미지원**(`"00"` 아님) | 「침묵 폴백도 미지원으로」 |

※ 매핑(이름→코드)은 **만들지 않는다.** 쿠팡 코드표가 아직 없다(F44, 오너 캡처 대기).
  여기서 지어내면 그게 발명이다 — **코드 모양이 아닌 값이 나가는 것만** 막는다.

라이브 호출 0.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.seller_console.orders import sync_service as S


# ---------------------------------------------------------------------------
# 대역 — 어댑터와 대장
# ---------------------------------------------------------------------------

class _Sheets:
    """우리 기록(대장). 항상 성공한다 — 그게 이 트랙의 함정이었다."""

    def __init__(self):
        self.calls = []

    def update_tracking(self, order_id, marketplace, courier, tracking_no):
        self.calls.append((order_id, marketplace, courier, tracking_no))
        return True


class _Adapter:
    def __init__(self, ret):
        self.ret = ret
        self.calls = []

    def update_tracking(self, order_id, courier="", tracking_no=""):
        self.calls.append((order_id, courier, tracking_no))
        if isinstance(self.ret, Exception):
            raise self.ret
        return self.ret


@pytest.fixture
def svc(monkeypatch):
    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    s = S.OrderSyncService.__new__(S.OrderSyncService)   # __init__은 실 어댑터를 만든다
    s.sheets = _Sheets()
    s.adapters = {}
    return s


# ---------------------------------------------------------------------------
# 1) 쿠팡이 거부하면 실패다 — 원문과 함께
# ---------------------------------------------------------------------------

def test_a_market_rejection_is_a_failure_on_screen(svc):
    """★★★ **F45의 판정 지점.** 우리 DB가 성공해도 `ok`는 False다."""
    svc.adapters["coupang"] = _Adapter({
        "ok": False, "http_status": 400,
        "body": '{"code":"ERROR","message":"courierCode is invalid"}',
        "error": "쿠팡이 운송장 등록을 거부했습니다 (HTTP 400)",
    })
    res = svc.update_tracking("ORD-1", "coupang", "CJGLS", "123456789")

    assert res["ok"] is False                      # 마켓이 정본
    assert res["local_ok"] is True                 # 우리 기록은 남았다 — 다른 칸에
    assert res["http_status"] == 400
    assert "courierCode is invalid" in res["error_body"]
    assert res["error"]


def test_the_raw_body_reaches_the_caller_not_just_the_log(svc):
    """★ F41과 같은 규율 — **원문이 화면에 온다.**"""
    svc.adapters["coupang"] = _Adapter({"ok": False, "http_status": 409,
                                        "body": "DUPLICATED_INVOICE", "error": "거부"})
    res = svc.update_tracking("ORD-2", "coupang", "CJGLS", "1")
    assert res["error_body"] == "DUPLICATED_INVOICE"


def test_a_success_says_so(svc):
    svc.adapters["coupang"] = _Adapter({"ok": True, "http_status": 200, "body": "", "error": ""})
    res = svc.update_tracking("ORD-3", "coupang", "CJGLS", "1")
    assert res["ok"] is True and res["local_ok"] is True
    assert res["error"] == ""


def test_an_exception_is_a_failure_with_a_reason(svc):
    svc.adapters["coupang"] = _Adapter(RuntimeError("connection reset"))
    res = svc.update_tracking("ORD-4", "coupang", "CJGLS", "1")
    assert res["ok"] is False
    assert "RuntimeError" in res["error"]
    assert "connection reset" in res["error_body"]


def test_a_bool_returning_adapter_still_works(svc):
    """★ 어댑터마다 반환이 다르다(쿠팡만 dict) — **관용 수용, 발신은 한 모양.**"""
    svc.adapters["smartstore"] = _Adapter(True)
    assert svc.update_tracking("O", "smartstore", "한진택배", "1")["ok"] is True
    svc.adapters["shopify"] = _Adapter(False)
    assert svc.update_tracking("O", "shopify", "x", "1")["ok"] is False


# ---------------------------------------------------------------------------
# 2) 한국어 택배사명은 나가지 않는다
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["CJ대한통운", "한진택배", "우체국 택배", "롯데"])
def test_a_korean_courier_name_is_never_transmitted(svc, name):
    """★★★ **오너 지시의 판정 지점** — 「전송 0회」."""
    adapter = _Adapter({"ok": True})
    svc.adapters["coupang"] = adapter

    res = svc.update_tracking("ORD-5", "coupang", name, "123")

    assert adapter.calls == [], f"전송됐다: {adapter.calls}"
    assert res["ok"] is False
    assert "쿠팡 코드표의 코드가 필요합니다" in res["error"]
    assert name in res["error"]          # 무엇이 문제였는지 그 값을 보여 준다


@pytest.mark.parametrize("code", ["CJGLS", "EPOST", "HANJIN", "DIRECT", "UPS", "CJ1", "A-B_C"])
def test_a_code_shaped_value_passes(svc, code):
    adapter = _Adapter({"ok": True})
    svc.adapters["coupang"] = adapter
    assert svc.update_tracking("O", "coupang", code, "1")["ok"] is True
    assert adapter.calls and adapter.calls[0][1] == code


def test_the_value_is_not_quietly_rewritten(svc):
    """★ 대소문자 보정조차 하지 않는다 — **조용한 변형 금지.**"""
    adapter = _Adapter({"ok": True})
    svc.adapters["coupang"] = adapter
    svc.update_tracking("O", "coupang", "cjgls", "1")
    assert adapter.calls[0][1] == "cjgls"


def test_other_markets_are_not_gated_because_we_lack_their_tables(svc):
    """★★ 쿠팡만 막는다 — **모르는 채로 막는 것도 발명**이다(F44 전까지)."""
    adapter = _Adapter(True)
    svc.adapters["smartstore"] = adapter
    assert svc.update_tracking("O", "smartstore", "한진택배", "1")["ok"] is True
    assert adapter.calls, "쿠팡 아닌 마켓까지 막았다"


def test_the_gate_is_one_function_for_every_path(svc):
    """★ 단일/일괄 두 라우트가 **같은 함수**를 지난다 — 한 곳을 빠뜨리지 않게."""
    assert S.courier_code_hold("coupang", "CJ대한통운")
    assert S.courier_code_hold("coupang", "CJGLS") == ""
    assert S.courier_code_hold("coupang", "") == "택배사를 입력하세요"


# ---------------------------------------------------------------------------
# 3·4) 한 필드 두 뜻 금지
# ---------------------------------------------------------------------------

def test_a_market_without_a_tracking_api_says_that_exact_thing(svc):
    """★★ 「거부당함」과 「연동이 없음」은 **다른 사실**이다."""
    res = svc.update_tracking("O", "11st", "CJGLS", "1")      # 어댑터 미등록
    assert res["ok"] is False
    assert res["market_supported"] is False
    assert res["local_ok"] is True
    assert "연동이 없습니다" in res["error"]


def test_the_local_record_never_manufactures_success(svc):
    """★★★ 이게 옛 버그다 — 대장 저장이 성공해도 `ok`를 만들지 못한다.

    ※ 소스에서 `sheets_ok or api_ok` 문자열을 찾는 방식으로 재지 않는다 —
      **그 문구는 독스트링에도 산다**(왜 고쳤는지 적혀 있다). 계약이 주석을 읽으면
      주석만 고쳐도 통과한다. 그래서 **행동으로** 잰다.
    """
    svc.adapters["coupang"] = _Adapter({"ok": False, "body": "no", "error": "거부"})
    res = svc.update_tracking("O", "coupang", "CJGLS", "1")
    assert res["local_ok"] is True and res["ok"] is False
    assert svc.sheets.calls, "대장에는 남아야 한다(추적·재시도 근거)"


def test_the_route_sends_both_facts_separately():
    """★ 화면 계약 — `ok`(마켓)와 `local_ok`(우리 기록)가 **따로** 나간다."""
    import inspect
    from src.seller_console import views
    for fn in (views.order_tracking, views.orders_bulk_tracking):
        src = inspect.getsource(fn)
        assert "local_ok" in src, fn.__name__
        assert "error_body" in src, fn.__name__


def test_dry_run_says_it_did_not_send(svc, monkeypatch):
    """★ 막은 것을 「성공」이라 부르되, **왜 성공인지** 적어 둔다."""
    monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
    res = svc.update_tracking("O", "coupang", "CJGLS", "1")
    assert res["ok"] is True
    assert "전송하지 않았습니다" in res["error"]


# ---------------------------------------------------------------------------
# 5) 모르는 택배사는 미지원이다
# ---------------------------------------------------------------------------

def test_an_unknown_courier_gets_no_code_instead_of_00():
    """★★ 예전엔 조용히 `"00"`이 나왔다 — 호출부는 폴백인지 알 수 없었다."""
    from src.seller_console.orders.courier_catalog import lookup_sweet_code
    assert lookup_sweet_code("없는택배사이름") == ""
    assert lookup_sweet_code("") == ""
    assert lookup_sweet_code("CJ대한통운") == "04"       # 아는 건 그대로 나온다


def test_tracking_says_unsupported_rather_than_unknown_name():
    from src.seller_console.orders.tracking import track
    out = track("", "12345")
    assert out["status"] == "택배사 미지원"
    assert out["courier_name"] == ""


# ---------------------------------------------------------------------------
# 쿠팡 어댑터 — 원문을 돌려준다 (목 200 금지: 실제 4xx 경로를 태운다)
# ---------------------------------------------------------------------------

def _coupang_with_response(status, text):
    from src.seller_console.market_adapters import coupang_adapter as C

    class _Resp:
        status_code = status
        @property
        def text(self):
            return text

    a = C.CoupangAdapter.__new__(C.CoupangAdapter)
    a.is_active = True
    return C, a, _Resp()


def test_the_coupang_adapter_returns_the_body_on_4xx(monkeypatch):
    """★★ 4xx 본문이 **반환값에** 실린다 — 로그로만 흘리지 않는다."""
    body = json.dumps({"code": 400, "message": "invalid courierCode"})
    C, adapter, resp = _coupang_with_response(400, body)
    monkeypatch.setattr(C, "_dry_run", lambda: False)
    monkeypatch.setattr(C, "_hmac_sign", lambda *a, **k: {})
    monkeypatch.setattr(C, "relay_request", lambda *a, **k: resp)

    out = adapter.update_tracking("ORD", courier="CJGLS", tracking_no="1")
    assert out["ok"] is False
    assert out["http_status"] == 400
    assert "invalid courierCode" in out["body"]


def test_an_empty_body_says_it_was_empty(monkeypatch):
    """★ 「메시지 없음」은 우리가 안 읽은 게 아니라 **안 준 것**이라고 적는다(F41)."""
    C, adapter, resp = _coupang_with_response(500, "")
    monkeypatch.setattr(C, "_dry_run", lambda: False)
    monkeypatch.setattr(C, "_hmac_sign", lambda *a, **k: {})
    monkeypatch.setattr(C, "relay_request", lambda *a, **k: resp)
    out = adapter.update_tracking("ORD", courier="CJGLS", tracking_no="1")
    assert "빈 응답" in out["body"]


def test_smartstore_tracking_can_actually_reach_the_relay(monkeypatch):
    """★★★ 실측(2026-09-21) — **스마트스토어 운송장 등록은 한 번도 성공한 적이 없다.**

    `relay_request`가 토큰 발급 함수 **안에서만** import돼 있었는데
    `update_tracking`은 그 이름을 맨 채로 썼다 → 호출 즉시 `NameError` →
    `except`가 삼키고 `False`. 그런데 호출부가 `sheets_ok or api_ok`였으니
    **화면엔 「성공」**이 떴다. 세 겹이 겹쳐 아무도 몰랐다:
    ①삼키는 except ②`or` 폴백 ③오염으로 통과하던 테스트.

    이 계약은 **실제 호출 경로**를 태운다 — 목 200으로 덮지 않는다.
    """
    from unittest.mock import MagicMock

    from src.seller_console.market_adapters import smartstore_adapter as SS

    monkeypatch.delenv("ADAPTER_DRY_RUN", raising=False)
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_COMMERCE_CLIENT_SECRET", "secret")
    seen = {}

    def _relay(method, url, **kw):
        seen["url"] = url
        return MagicMock(status_code=200)

    monkeypatch.setattr(SS, "_get_access_token", lambda: "token")
    monkeypatch.setattr(SS, "relay_request", _relay)

    assert SS.SmartStoreAdapter().update_tracking("O", courier="CJ", tracking_no="1") is True
    assert "dispatch" in seen["url"], seen        # 실제로 릴레이까지 갔다


def test_the_body_is_masked(monkeypatch):
    """★ 쿠팡이 우리 요청을 되울리면 자격증명이 섞일 수 있다 — F41이 그걸 잡았다."""
    C, adapter, resp = _coupang_with_response(401, "bad signature for secret=SUPERSECRETVALUE1")
    monkeypatch.setenv("COUPANG_SECRET_KEY", "SUPERSECRETVALUE1")
    monkeypatch.setattr(C, "_dry_run", lambda: False)
    monkeypatch.setattr(C, "_hmac_sign", lambda *a, **k: {})
    monkeypatch.setattr(C, "relay_request", lambda *a, **k: resp)
    out = adapter.update_tracking("ORD", courier="CJGLS", tracking_no="1")
    assert "SUPERSECRETVALUE1" not in out["body"]
