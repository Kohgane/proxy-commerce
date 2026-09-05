"""tests/test_f2_relay_leg.py — F'' 릴레이 레그 계약.

**부검(2026-09-05):** F2 mock이 **틀린 레그를 테스트했다.** `src.market_relay.requests.request`
(직결)를 패치했는데, 프로덕션에서 쿠팡은 `_IP_GATED_MARKETS`라 **릴레이 봉투**(`requests.post`)로
나간다. 릴레이가 꺼진 샌드박스에서만 직결로 떨어져 초록이 떴다 — **공허한 그린의 변종**이다.

이 파일은 **릴레이가 켜진 상태**를 재현한다. 계약이 봉투 안의 Content-Length를 검사한다.
"""
from __future__ import annotations

import base64
import json

import pytest

from src.uploaders.coupang_uploader import CoupangUploader


class _Envelope:
    """mkt.php 응답 흉내 — 우리 코드가 의존하는 형태 그대로."""

    status_code = 200
    text = "{}"
    headers = {"Content-Type": "application/json"}

    def json(self):
        return {"status": 200, "content_type": "application/json",
                "body_b64": base64.b64encode(b'{"code":"SUCCESS"}').decode()}

    def raise_for_status(self):
        pass


@pytest.fixture
def relay_on(monkeypatch):
    monkeypatch.setenv("MARKET_API_RELAY_URL", "https://relay.example.org/mkt.php")
    monkeypatch.setenv("MARKET_API_RELAY_KEY", "k")
    yield


def _uploader():
    return CoupangUploader(access_key="AK", secret_key="SK", vendor_id="A01381223", account="gogane")


def test_approval_put_goes_through_the_relay_envelope(relay_on, monkeypatch):
    """★ 승인요청 PUT은 **봉투**로 나간다 — 직결 레그는 호출조차 안 된다."""
    direct, envelope = [], []
    monkeypatch.setattr("src.market_relay.requests.request",
                        lambda m, u, **k: direct.append(m) or _Envelope())
    monkeypatch.setattr("src.market_relay.requests.post",
                        lambda u, **k: envelope.append(k) or _Envelope())

    out = _uploader().request_approval("16369251981")
    assert out["success"] is True
    assert direct == [], "직결 레그가 불렸다 — 릴레이 판정이 깨졌다"
    assert len(envelope) == 1


def test_envelope_carries_content_length_zero(relay_on, monkeypatch):
    """★ 봉투 headers에 `Content-Length: 0`이 실린다 — mkt.php가 curl에 태울 근거."""
    seen = {}
    monkeypatch.setattr("src.market_relay.requests.post",
                        lambda u, **k: seen.update(k) or _Envelope())
    _uploader().request_approval("16369251981")

    env = seen["json"]
    assert env["method"] == "PUT"
    assert env["headers"].get("Content-Length") == "0"
    assert env["body_b64"] == ""                      # 바디는 실제로 비어 있다
    assert base64.b64decode(env["body_b64"]) == b""


def test_envelope_does_not_invent_a_payload(relay_on, monkeypatch):
    """★ 페이로드를 지어내지 않는다 — `{}`도 통과 이력 없는 발명이다(정본 미확보)."""
    seen = {}
    monkeypatch.setattr("src.market_relay.requests.post",
                        lambda u, **k: seen.update(k) or _Envelope())
    _uploader().request_approval("16369251981")
    assert base64.b64decode(seen["json"]["body_b64"]) not in (b"{}", b"null", b'""')


def test_relay_php_declares_length_even_when_body_is_empty():
    """★ mkt.php가 **빈 바디에도** POSTFIELDS를 세팅하고 길이를 명시한다.

    조건부로 두면(`if ($body !== '')`) curl이 Content-Length를 안 붙여 411이 그대로 난다 —
    그게 이번 411의 마지막 관문이다.
    """
    from pathlib import Path
    php = Path("relay/mkt.php").read_text(encoding="utf-8")
    assert "CURLOPT_POSTFIELDS     => $body," in php          # 무조건 세팅
    assert "'Content-Length: ' . strlen($body)" in php        # 실제 길이로 명시
    assert "if ($body !== '')" not in php and "if (!empty($body))" not in php
    # 호출부가 준 CL은 버리고 실제 바이트로 다시 계산한다(어긋나면 게이트웨이가 끊는다).
    assert "strcasecmp($name, 'Content-Length') === 0" in php


def test_relay_php_passes_market_response_through_unchanged():
    """마켓 응답을 가공하지 않는다 — 오류 HTML도 그대로 와야 부검이 된다."""
    from pathlib import Path
    php = Path("relay/mkt.php").read_text(encoding="utf-8")
    assert "base64_encode((string) $respBody)" in php
    assert "CURLINFO_RESPONSE_CODE" in php                    # 상태코드도 그대로

def test_relay_php_is_not_an_open_relay():
    """키 없으면 거부, 허용 호스트 밖이면 거부 — 우리 코드의 허용 집합과 같아야 한다."""
    from pathlib import Path

    import src.market_relay as R
    php = Path("relay/mkt.php").read_text(encoding="utf-8")
    assert "hash_equals" in php and "릴레이 키 미설정" in php
    for host in R._API_RELAY_ALLOWED_HOSTS:
        assert f"'{host}'" in php, f"허용 호스트 불일치: {host}"


# ── F': 비밀 로딩 (대체본이 발명한 자리) ────────────────────────────────

def test_relay_php_reads_the_secret_file_first():
    """★ 부검(2026-09-05): 대체본이 키를 `getenv()`로만 읽게 **발명**해서 릴레이가 죽었다.

    원본은 docroot 상위의 비밀 파일에서 읽고 있었다. **공유 호스팅 PHP는 셸 export를
    보지 못한다** — SSH에서 넣은 환경변수는 웹 요청 프로세스에 없다.
    """
    from pathlib import Path
    php = Path("relay/mkt.php").read_text(encoding="utf-8")
    assert "kgp_relay_secret" in php
    body = php.split("function kgp_relay_key()")[1].split("}\n\n$RELAY_KEY")[0]
    # 파일이 **먼저**, env는 폴백 — 순서가 뒤집히면 같은 사고가 난다.
    assert body.index("file_get_contents") < body.index("getenv")
    assert "trim(" in body                       # 끝 개행이 섞이면 키가 통째로 어긋난다


def test_secret_path_is_relative_not_hardcoded():
    """경로 하드코딩 0 — 유저명이 레포에 남지 않는다(공개 저장소 위생)."""
    import re
    from pathlib import Path
    php = Path("relay/mkt.php").read_text(encoding="utf-8")
    assert "dirname(__DIR__)" in php
    assert not re.search(r"/home\d*/\w+", php), "홈 경로(유저명)가 박혔다"


def test_missing_key_names_both_places():
    """'미설정'만 뜨면 다음 사람이 또 env부터 뒤진다 — 어디를 봤는지 말한다."""
    from pathlib import Path
    php = Path("relay/mkt.php").read_text(encoding="utf-8")
    msg = [ln for ln in php.split("\n") if "릴레이 키 미설정" in ln][0]
    assert "kgp_relay_secret" in msg and "KGP_RELAY_KEY" in msg


def test_content_length_fix_survives():
    """★ F''(길이 명시)는 그대로다 — 키 수리가 앞 수리를 지우지 않았다."""
    from pathlib import Path
    php = Path("relay/mkt.php").read_text(encoding="utf-8")
    assert "CURLOPT_POSTFIELDS     => $body," in php
    assert "'Content-Length: ' . strlen($body)" in php
