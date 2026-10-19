"""Y13-F F1(오너 2026-10-19) — 쿠팡 「오늘 등록할 수 있는 구매옵션 개수(5000)」 거부.

실측: 고가네(A01381223) 피샹리 「현재까지 요청: 5000, 현재요청: 10」 · BLACKHOLES 「현재요청: 2」가 `api_error`(재시도 가능)로
나왔다. 같은 날은 다시 눌러도 같은 답이다 → 한도 코드·재시도 없음·KST 00:10 이후 이월 · 브릿지가 보낸 items 수 집계.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.services import coupang_option_quota as Q

KST = timezone(timedelta(hours=9))
RAW = ("[A01381223]가 오늘 등록할 수 있는 구매옵션 개수(5000)를 초과하였습니다. "
       "현재까지 요청: 5000, 현재요청: 10")


@pytest.fixture(autouse=True)
def _clean():
    from src.db import image_translate_queue_pg as st
    from src.db import option_translate_queue_pg as oq
    st.reset_for_tests()
    oq.reset_for_tests()
    yield
    st.reset_for_tests()
    oq.reset_for_tests()


def _resp(status, text):
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.json.return_value = {"code": "SUCCESS", "data": 123}
    r.raise_for_status.return_value = None
    return r


def _up():
    from src.uploaders.coupang_uploader import CoupangUploader
    return CoupangUploader(access_key="ak", secret_key="sk", vendor_id="A01381223")


def test_parse_real_text():
    p = Q.parse(RAW)
    assert p == {"vendor": "A01381223", "limit": 5000, "used": 5000, "req": 10}
    assert Q.parse("쿠팡 거부 — 카테고리 없음") is None


def test_post_put_refresh_items_are_counted_by_kind():
    up = _up()
    path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
    with patch("src.uploaders.coupang_uploader.relay_request", return_value=_resp(200, '{"code":"SUCCESS"}')):
        up._api_request("POST", path, data={"items": [{}] * 10})
        up._api_request("PUT", path, data={"sellerProductId": 1, "items": [{}] * 3})
        up.count_kind = "refresh"
        up._api_request("PUT", path, data={"sellerProductId": 1, "items": [{}] * 2})
        up._api_request("GET", path + "/1")                          # 조회는 안 센다
    u = Q.usage("A01381223")
    assert u["bridge"] == 15
    assert u["kinds"] == {"post": 10, "put": 3, "refresh": 2}


def test_quota_reject_is_not_counted_and_is_observed():
    up = _up()
    path = "/v2/providers/seller_api/apis/api/v1/marketplace/seller-products"
    body = '{"code":"ERROR","message":"%s"}' % RAW
    with patch("src.uploaders.coupang_uploader.relay_request", return_value=_resp(400, body)):
        res = up._api_request("POST", path, data={"items": [{}] * 10})
    assert Q.usage("A01381223")["bridge"] == 0
    out = up._quota_tag({"success": False, "error": res["error"]}, res.get("error_body"))
    assert out["reason_code"] == Q.CODE and out["quota"]["req"] == 10
    u = Q.usage("A01381223")
    assert u["observed"] == 5000 and u["left"] == 0


def test_dispatcher_quota_code_not_retryable():
    from src.channel_sync._channel_bridge import ChannelUploadError
    from src.seller_console.upload_dispatcher import RETRYABLE_CODES, UploadDispatcher
    exc = ChannelUploadError("쿠팡 업로드 실패: " + RAW, lines=[RAW])
    exc.reason_code = Q.CODE
    fake = MagicMock()
    fake.upload.side_effect = exc
    with patch.dict("sys.modules", {"src.channel_sync.coupang_uploader": fake}):
        with patch("src.channel_sync.coupang_uploader", fake, create=True):
            r = UploadDispatcher()._upload_coupang({"title": "x", "price": 1000})
    assert r.error_code == Q.CODE
    assert "내일 자동 재시도" in r.message
    assert Q.CODE not in RETRYABLE_CODES


def test_carry_due_after_kst_0010_next_day_and_repeat_keeps_row():
    Q.carry_add("item1", "coupang:gogane", "u1", Q.parse(RAW))
    assert Q.carry_add("item1", "coupang:gogane", "u1") is False          # 같은 줄 중복 0
    day = Q.carry_rows()[0]["day"]
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=KST)
    same_day = (d + timedelta(hours=23)).astimezone(timezone.utc)
    too_early = (d + timedelta(days=1, minutes=5)).astimezone(timezone.utc)
    ok = (d + timedelta(days=1, minutes=11)).astimezone(timezone.utc)
    assert Q.carry_due(same_day) == []
    assert Q.carry_due(too_early) == []
    assert [r["item_id"] for r in Q.carry_due(ok)] == ["item1"]
    Q.carry_done("item1", "coupang:gogane", {"success": False, "error_code": Q.CODE, "message": "또 한도"})
    assert len(Q.carry_rows()) == 1 and Q.carry_rows()[0]["tries"] == 1   # 또 한도면 남긴다
    Q.carry_done("item1", "coupang:gogane", {"success": True, "message": "등록"})
    assert Q.carry_rows() == []


def test_caution_line_warns_when_items_exceed_left():
    Q.observe("A01381223", {"used": 4995, "limit": 5000})
    Q.count("A01381223", 4, "post")
    line = Q.caution("A01381223", 10)
    assert line.startswith("오늘 쿠팡 옵션 사용(브릿지분) 4/5,000")
    assert "브릿지 밖 포함" in line and "남은 5개를 넘어요" in line
    assert "넘어요" not in Q.caution("A01381223", 3)


def test_refresh_queue_blocks_when_exhausted_or_over_daily_cap(monkeypatch):
    assert Q.refresh_block("V1") == ""
    Q.observe("V1", {"used": 5000, "limit": 5000})
    assert "한도 소진" in Q.refresh_block("V1")
    monkeypatch.setenv("COUPANG_REFRESH_DAILY_ITEMS", "5")
    Q.count("V2", 5, "refresh")
    assert "하루 상한 5개" in Q.refresh_block("V2")


def test_collect_upload_puts_quota_market_in_carry():
    from src.seller_console import views as V
    rd = {"results": [{"market": "coupang:gogane", "success": False, "error_code": Q.CODE},
                      {"market": "smartstore:chezgoga", "success": True}]}
    with patch.object(V, "_seller_id", return_value="u1"):
        V._carry_option_quota("item9", rd)
    rows = Q.carry_rows()
    assert [(r["item_id"], r["market"], r["uid"]) for r in rows] == [("item9", "coupang:gogane", "u1")]
    assert "00:10" in rd["results"][0]["carry"]
