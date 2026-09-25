"""F44-b 계약 — **17TRACK 교체**(TrackingMore 퇴출, 병존 금지).

## 결정 (오너 2026-09-21)

> TrackingMore 무료 쿼터 **소진**(`code 4190`, 실측) → 17TRACK으로 **교체**.
> 키는 서버 env, 측정은 같은 「택배사 판별 테스트」 화면.
> **17TRACK도 무료 한도가 있으니 남은 쿼터를 화면에 적어라.**

## ★★ 볼트 지뢰를 미리 밟아 둔다 — [[17TRACK 등록 조용한 실패]]

다른 프로젝트에서 이미 당했다: `add()`가 **register 실패를 무시하고 DB에만 기록**해
송장 하나가 「조회 불가」로 방치됐다.

> ★ **「등록했다」는 응답이 아니라 `accepted` 배열이 증거다.**

그리고 한 겹 더 있다 — `accepted`는 **등록 성공이지 추적 성공은 아니다.**
캐리어 자동감지가 실패하면(`-18019903`) **코드를 지정**해야 등록된다.

## 라이브 호출 0

「키를 옮기지 말고 측정을 옮긴다」 — 여기서 재는 것은 **배선과 규율**이고,
실측은 오너가 관리자 화면에서 버튼으로 한다.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from src.seller_console.orders import tracking_17track as T
from tests._ast_probe import importers_of

KEY = "T17-SECRET-KEY-123456"


class _Resp:
    def __init__(self, status=200, payload=None, text=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}
        self.text = json.dumps(self._payload) if text is None else text

    def json(self):
        return self._payload


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(T.API_KEY_ENV, KEY)
    return T.SeventeenTrackClient()


# ---------------------------------------------------------------------------
# 문서에서 확인한 것만 (발명 0)
# ---------------------------------------------------------------------------

def test_the_endpoint_and_auth_header_are_the_documented_ones(client):
    """★ 주소·헤더는 **문서 값**이다. 하나라도 어긋나면 전부 401이거나 404다."""
    seen = {}

    def _post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, headers=headers or {}, body=json)
        return _Resp(200, {"code": 0, "data": {"accepted": [], "rejected": []}})

    with patch("requests.post", side_effect=_post):
        client.register([{"number": "N1"}])

    assert seen["url"] == "https://api.17track.net/track/v2.4/register"
    assert seen["headers"]["17token"] == KEY
    assert seen["headers"]["Content-Type"] == "application/json"
    assert seen["body"] == [{"number": "N1"}]


def test_the_quota_call_posts_an_empty_array(client):
    """★ 문서: `getquota`의 본문은 **빈 배열**이다."""
    seen = {}

    def _post(url, json=None, **kw):
        seen.update(url=url, body=json)
        return _Resp(200, {"code": 0, "data": {"quota_remain": 7}})

    with patch("requests.post", side_effect=_post):
        got = client.quota()

    assert seen["url"].endswith("/getquota") and seen["body"] == []
    assert got["ok"] is True and got["remain"] == 7


def test_the_batch_cap_is_refused_before_it_is_sent(client):
    """★ 문서 상한 40 — 넘겨 보내면 공급사가 **말없이 자른다**(쿼터만 쓰고)."""
    rows = [{"number": f"N{i}"} for i in range(T.MAX_BATCH + 1)]
    with patch("requests.post", side_effect=AssertionError("보내면 안 된다")):
        got = client.register(rows)
    assert got["ok"] is False and str(T.MAX_BATCH) in got["error"]


# ---------------------------------------------------------------------------
# ★★★ accepted 배열이 증거다
# ---------------------------------------------------------------------------

def test_a_200_without_accepted_is_not_a_registration(client):
    """★★★ **판정 지점** — 200을 「등록됐다」로 읽으면 조용한 실패가 된다(볼트 실증)."""
    with patch("requests.post", return_value=_Resp(200, {"code": 0, "data": {
            "accepted": [],
            "rejected": [{"number": "N", "error": {"code": -18019903,
                                                   "message": "Carrier cannot be detected."}}]}})):
        got = client.register([{"number": "N"}])
    assert got["ok"] is False
    assert got["rejected"] and not got["accepted"]


def test_an_accepted_row_is_a_registration(client):
    with patch("requests.post", return_value=_Resp(200, {"code": 0, "data": {
            "accepted": [{"origin": 1, "number": "N", "carrier": 3011}], "rejected": []}})):
        got = client.register([{"number": "N"}])
    assert got["ok"] is True and got["accepted"][0]["carrier"] == 3011


def test_neither_list_is_reported_not_swallowed(client):
    """★★ 200 + 양쪽 다 빈 응답 = **아무도 무슨 일인지 말하지 않았다.** 성공이 아니다."""
    with patch("requests.post", return_value=_Resp(200, {"code": 0, "data": {}})):
        got = client.register([{"number": "N"}])
    assert got["ok"] is False and "accepted" in got["error"]


def test_a_vendor_error_code_on_http_200_is_a_failure(client):
    """★★ 쿼터 소진을 공급사는 **200 + code**로 말한다(TrackingMore의 4190이 그랬다)."""
    with patch("requests.post", return_value=_Resp(200, {"code": 4190, "data": None})):
        got = client.register([{"number": "N"}])
    assert got["ok"] is False and "4190" in got["error"]


# ---------------------------------------------------------------------------
# 판별 = 등록의 부산물
# ---------------------------------------------------------------------------

def test_detect_reads_the_carrier_from_accepted(client):
    with patch("requests.post", return_value=_Resp(200, {"code": 0, "data": {
            "accepted": [{"number": "N", "carrier": 100003}], "rejected": []}})):
        got = client.detect_detail("N")
    assert got["codes"] == [100003] and got["accepted"] is True


def test_detect_says_a_carrier_code_would_fix_it(client):
    """★★★ 볼트 지뢰 — 자동감지 실패는 **코드를 지정하면 풀린다**(FedEx=100003 실증).

    사유에 그 말이 없으면 다음 사람이 「이 택배사는 안 되는구나」로 잘못 읽는다.
    """
    with patch("requests.post", return_value=_Resp(200, {"code": 0, "data": {
            "accepted": [],
            "rejected": [{"number": "N", "error": {"code": T.ERR_CARRIER_NOT_DETECTED,
                                                   "message": "Carrier cannot be detected."}}]}})):
        got = client.detect_detail("N")
    assert got["codes"] == [] and "코드를 지정" in got["error"]


def test_a_given_carrier_code_is_sent_through(client):
    """★ 코드를 지정하면 **그대로 실려 나간다** — 그게 위 지뢰의 해법이다."""
    seen = {}

    def _post(url, json=None, **kw):
        seen["body"] = json
        return _Resp(200, {"code": 0, "data": {
            "accepted": [{"number": "N", "carrier": 100003}], "rejected": []}})

    with patch("requests.post", side_effect=_post):
        client.detect_detail("N", carrier=100003)
    assert seen["body"] == [{"number": "N", "carrier": 100003}]


# ---------------------------------------------------------------------------
# 키가 없을 때 · 원문 · 마스킹
# ---------------------------------------------------------------------------

def test_no_key_is_a_reason_not_an_empty_result(monkeypatch):
    monkeypatch.delenv(T.API_KEY_ENV, raising=False)
    c = T.SeventeenTrackClient()
    with patch("requests.post", side_effect=AssertionError("부르면 안 된다")):
        got = c.detect_detail("N")
    assert got["codes"] == [] and T.API_KEY_ENV in got["error"]


def test_the_key_is_masked_out_of_the_raw_body(client):
    with patch("requests.post", return_value=_Resp(401, {}, text=f"bad key {KEY}")):
        got = client.detect_detail("N")
    assert KEY not in got["raw"] and got["http_status"] == 401


def test_health_check_uses_quota_not_registration(client):
    """★★ 헬스 체크가 **등록**을 부르면 살아 있는지 물을 때마다 칸을 태운다."""
    seen = []

    def _post(url, json=None, **kw):
        seen.append(url)
        return _Resp(200, {"code": 0, "data": {"quota_remain": 5, "quota_total": 10}})

    with patch("requests.post", side_effect=_post):
        got = client.health_check()
    assert all(u.endswith("/getquota") for u in seen), seen
    assert got["status"] == "ok" and got["remain"] == 5


def test_health_check_without_a_key_says_which_env(monkeypatch):
    monkeypatch.delenv(T.API_KEY_ENV, raising=False)
    got = T.SeventeenTrackClient().health_check()
    assert got["status"] == "missing" and T.API_KEY_ENV in got["hint"]


# ---------------------------------------------------------------------------
# 병존 금지 — 옛 공급사가 남아 있지 않다
# ---------------------------------------------------------------------------

def test_the_old_vendor_module_is_gone():
    """★★★ 오너 지시 **「병존 금지」** — 죽은 공급사를 남겨 두면 쓰지도 않는 키를 묻는다."""
    with pytest.raises(ImportError):
        __import__("src.seller_console.orders.tracking_trackingmore")


def test_nothing_imports_the_old_vendor():
    """★★ 글자가 아니라 **import**를 잰다 — 설명문에 이름이 남는 건 병존이 아니다."""
    assert importers_of("tracking_trackingmore") == []


def test_the_env_catalog_names_the_new_key():
    from src.utils.env_catalog import API_REGISTRY as API_KEYS

    names = {k.name for k in API_KEYS}
    assert "seventeentrack" in names and "trackingmore" not in names
    envs = {e for k in API_KEYS for e in k.env_vars}
    assert "SEVENTEENTRACK_API_KEY" in envs and "TRACKINGMORE_API_KEY" not in envs


def test_the_carrier_list_url_is_not_guessed(monkeypatch):
    """★★★ 문서는 목록을 **링크로만** 말했다 — 주소를 짐작해 박지 않는다.

    박아 두면 매 요청이 없는 곳을 두드리고, 실패는 조용한 빈 목록이 된다.
    """
    monkeypatch.delenv(T.CARRIER_LIST_URL_ENV, raising=False)
    assert T.carrier_list_url() == ""
    from src.seller_console.orders.courier_catalog import _vendor_rows
    assert _vendor_rows() == []


def test_our_carrier_code_column_is_empty_and_says_so():
    """★ 17TRACK 코드 축은 **빈칸**이다 — 「아직 안 붙였다」를 정직하게 말한다."""
    from src.seller_console.orders.courier_catalog import get_courier_catalog

    rows = get_courier_catalog(include_dynamic=False, include_coupang=False)
    assert rows and all("seventeentrack_code" in r for r in rows)
    assert all(r["seventeentrack_code"] == "" for r in rows)


# ---------------------------------------------------------------------------
# 멈춘 것은 멈췄다고 말한다
# ---------------------------------------------------------------------------

def test_the_tracking_cron_says_it_is_paused_instead_of_faking_work(monkeypatch):
    """★★★ 공급사 교체 중 상태 폴링은 **멈춰 있다.** 그걸 `ok`로 말하면 거짓말이다.

    17TRACK 상태 조회 응답 모양을 아직 확인하지 못했다 — 짐작해 파서를 쓰면
    배송완료를 잘못 찍거나 조용히 못 찍는다. 그래서 **안 하고, 안 한다고 말한다.**
    """
    from src.order_webhook import app

    monkeypatch.setenv(T.API_KEY_ENV, KEY)
    with app.test_client() as c:
        r = c.get("/cron/track-shipments")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "paused" and body["updated"] == 0
    assert body["key_present"] is True
    assert "17TRACK" in body["detail"]
