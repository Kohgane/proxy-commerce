"""F41 계약 — 11번가가 준 본문을 버리지 않는다.

## 실측 (오너 2026-09-20, 카나리 3차)

11번가 등록이 **500**으로 실패했는데 화면엔 사유가 없었다.

> **「메시지 없음」은 우리가 안 읽은 것이지 11번가가 안 준 게 아니다.** (오너)

본문(XML)을 확보해야 원인을 가를 수 있다 — XML 검증인지, 카테고리인지, IP인지.
**본문 없이는 분류 자체가 추측이다.**

## 고친 자리 셋

| 갈래 | 예전 | 이제 |
|---|---|---|
| HTTP 비-2xx | `HTTP 500: {text[:200]}` — 본문이 비면 `HTTP 500: ` | 앞 300자 + **비었으면 「본문을 주지 않았습니다」** |
| XML 파싱 실패 | **「응답 파싱 실패」** — 원문이 통째로 사라짐 | 원문 앞 300자 |
| 코드만 있고 메시지 태그 없음 | **「메시지 없음 — 코드로 원인 확인 필요」** | 코드 + **원문 앞 300자** |

전체 본문은 **로그**에(앞 2000자), 화면엔 **앞 300자**. 자격 값은 마스킹을 지난다
(F30 규율: **사유는 보여 주고 좌표는 지운다**).

> ★★ **좁은 반환 타입·친절한 요약이 사유를 죽인다.** 태그 이름을 우리가 다 아는 게 아니다 —
> 모르는 모양이면 **원문을 그대로** 넘긴다.

라이브 호출 0.
"""
from __future__ import annotations

import logging

import pytest

XML_ERR = ("<?xml version='1.0' encoding='utf-8'?><Result>"
           "<resultCode>201</resultCode>"
           "<resultMsg>카테고리 코드가 유효하지 않습니다</resultMsg></Result>")
XML_CODE_ONLY = ("<?xml version='1.0' encoding='utf-8'?><Result>"
                 "<resultCode>999</resultCode><detail>XML 스키마 오류 line 12</detail></Result>")


@pytest.fixture
def up(monkeypatch):
    from src.uploaders.elevenst_uploader import ElevenStUploader
    monkeypatch.setenv("ELEVENST_API_KEY", "k")
    return ElevenStUploader()


class _Resp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text
        self.headers: dict = {}


# ---------------------------------------------------------------------------
# ① HTTP 비-2xx — 본문을 싣는다
# ---------------------------------------------------------------------------

def test_a_500_carries_the_body(up, monkeypatch, caplog):
    """★★ **F41의 판정 지점** — 500의 XML 본문이 문장에 온다."""
    import src.uploaders.elevenst_uploader as E
    monkeypatch.setattr(E, "relay_request", lambda *a, **k: _Resp(500, XML_ERR))
    with caplog.at_level(logging.WARNING, logger="src.uploaders.elevenst_uploader"):
        out = up.upload_product({"sku": "s1", "title": "수행방패", "price": 9900})
    assert out["success"] is False
    assert "카테고리 코드가 유효하지 않습니다" in out["error"], out["error"]
    assert out["http_status"] == 500
    # 전체 본문은 로그에 — 화면 300자로 잘린 뒤에도 부검이 된다.
    assert "카테고리 코드가" in " ".join(r.getMessage() for r in caplog.records)


def test_an_empty_500_body_says_so(up, monkeypatch):
    """★ 본문이 정말 비었으면 **그렇게 말한다** — 「HTTP 500: 」로 끝내지 않는다."""
    import src.uploaders.elevenst_uploader as E
    monkeypatch.setattr(E, "relay_request", lambda *a, **k: _Resp(500, ""))
    out = up.upload_product({"sku": "s1", "title": "t", "price": 9900})
    assert "본문을 주지 않았습니다" in out["error"], out["error"]


def test_the_body_is_capped_at_300_chars(up, monkeypatch):
    """화면 문장은 앞 300자 — 전체는 로그다(오너 지시)."""
    import src.uploaders.elevenst_uploader as E
    long_body = "<Result>" + ("가" * 900) + "</Result>"
    monkeypatch.setattr(E, "relay_request", lambda *a, **k: _Resp(500, long_body))
    out = up.upload_product({"sku": "s1", "title": "t", "price": 9900})
    assert out["error"].count("가") <= 300


# ---------------------------------------------------------------------------
# ② 200인데 사유가 XML 안에 있는 갈래
# ---------------------------------------------------------------------------

def test_a_code_without_a_message_tag_still_shows_the_raw_xml(up):
    """★★ 「메시지 없음」이 사유를 죽이던 자리 — 이제 원문이 붙는다."""
    parsed = up._parse_response(XML_CODE_ONLY)
    assert parsed["ok"] is False
    assert "999" in parsed["message"]
    assert "XML 스키마 오류" in parsed["message"], parsed["message"]
    assert "메시지 없음" not in parsed["message"]


def test_unparseable_xml_keeps_the_original(up):
    """★ 「응답 파싱 실패」 한 줄이 원문을 통째로 버렸다."""
    parsed = up._parse_response("<<not xml>>")
    assert "<<not xml>>" in parsed["message"], parsed["message"]
    assert parsed["message"] != "응답 파싱 실패"


def test_an_empty_response_is_distinguished_from_an_unreadable_one(up):
    """★ **「못 읽었다」와 「안 줬다」는 다른 사건이다.**"""
    assert "본문을 주지 않았습니다" in up._parse_response("")["message"]


def test_a_normal_error_message_is_unchanged(up):
    """무회귀 — 코드·메시지가 다 오면 예전 그대로 `[코드] 메시지`."""
    parsed = up._parse_response(XML_ERR)
    assert parsed["message"].startswith("[201]")
    assert "카테고리 코드가 유효하지 않습니다" in parsed["message"]


def test_success_is_still_success(up):
    ok = ("<?xml version='1.0' encoding='utf-8'?><Result>"
          "<resultCode>100</resultCode><ProductNo>123456</ProductNo></Result>")
    parsed = up._parse_response(ok)
    assert parsed["ok"] is True and parsed["product_no"] == "123456"


# ---------------------------------------------------------------------------
# ③ 사유는 보여 주고 좌표는 지운다 (F30 규율)
# ---------------------------------------------------------------------------

def test_the_api_key_never_rides_along(up, monkeypatch):
    """★ 본문에 키가 섞여 와도 화면엔 안 나간다 — 마스킹을 지난다."""
    import src.uploaders.elevenst_uploader as E
    monkeypatch.setenv("ELEVENST_API_KEY", "SUPERSECRETKEY123456")
    leaky = "<Result><resultMsg>bad key SUPERSECRETKEY123456</resultMsg></Result>"
    monkeypatch.setattr(E, "relay_request", lambda *a, **k: _Resp(500, leaky))
    out = E.ElevenStUploader().upload_product({"sku": "s", "title": "t", "price": 9900})
    assert "SUPERSECRETKEY123456" not in out["error"], out["error"]


def test_the_error_reaches_the_dispatcher_message(monkeypatch):
    """★★ 업로더가 실은 사유가 **화면까지** 온다 — 중간에서 요약되지 않는다."""
    from src.channel_sync import _channel_bridge as B

    class _Up:
        @staticmethod
        def prepare_product(c):
            return c

        @staticmethod
        def upload_product(p):
            return {"success": False, "error": "HTTP 500: 카테고리 코드가 유효하지 않습니다"}

    monkeypatch.setenv("ELEVENST_API_KEY", "k")
    with pytest.raises(B.ChannelUploadError) as err:
        B.run_upload(_Up(), {"title": "t", "sell_price_krw": 19900},
                     required_envs=["ELEVENST_API_KEY"], market_label="11번가")
    assert "카테고리 코드가 유효하지 않습니다" in str(err.value)
