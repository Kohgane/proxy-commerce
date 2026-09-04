"""tests/test_s3_diag_per_market.py — 6-b: S3 신호줄 진단을 마켓별 개별 호출로.

**부검(2026-09-04):** 라이브에서 신호줄이 **상시 '진단 실패'**였다. 원인 둘:
  ① 호출 단위가 틀렸다 — 전체 진단(GET)은 마켓 5개를 **순차로** 실 API 호출한다.
     쿠팡은 릴레이 경유라 요청 하나에 최대 35초, 스스는 OAuth 토큰 발급이 먼저다.
     한 요청에 5마켓을 묶으면 3초는 **구조적으로** 못 맞춘다.
  ② 마켓 코드가 두 벌이었다 — 신호줄은 `elevenst`, 진단 레지스트리는 `11st`.
     11번가만 **영구 404 → 진단 실패**. 신호줄을 만든 이유가 바로 그 마켓이었다.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
TPL = Path("src/seller_console/templates/dashboard.html").read_text(encoding="utf-8")


@pytest.fixture
def client():
    from src.order_webhook import app
    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user_id"] = "u1"
        yield c


def test_signal_row_market_codes_all_resolve():
    """★ 신호줄이 내보내는 코드가 **전부** 진단 레지스트리로 풀린다(11번가 포함)."""
    from src.seller_console import market_credentials as mc
    from src.seller_console.market_integration_diagnostics import resolve_market_key

    for s in mc.all_status("u1"):
        market = s["market"]
        try:
            resolve_market_key(market)
        except KeyError:
            from src.pipeline.register_adapters import TalkStoreAdapter
            # 진단 대상이 아닌 마켓(대행사 심사 전 톡스토어)만 예외로 허용한다.
            assert market == TalkStoreAdapter.market, f"신호줄 코드가 진단에 안 풀린다: {market}"


@pytest.mark.parametrize("alias,expected", [
    ("elevenst", "11st"), ("11st", "11st"), ("naver", "smartstore"),
    ("naver_commerce", "smartstore"), ("wc", "woocommerce"), ("coupang", "coupang"),
])
def test_alias_resolution_single_source(alias, expected):
    """별칭 흡수는 S1의 `canonical_market` 하나만 쓴다(코드가 두 벌이 되지 않게)."""
    from src.seller_console.market_integration_diagnostics import resolve_market_key
    assert resolve_market_key(alias) == expected


def test_post_route_accepts_signal_row_codes(client):
    """라우트가 신호줄 코드를 그대로 받는다 — 전엔 `elevenst`가 404였다."""
    r = client.post("/seller/markets/integration-diagnostics", json={"market": "elevenst"})
    assert r.status_code == 200
    assert (r.get_json() or {}).get("ok") is True


def test_dashboard_calls_per_market_not_all_at_once():
    """★ 처방은 타임아웃 상향이 아니라 **마켓별 개별 호출**이다."""
    block = TPL.split("S3 — 진단은")[1]
    assert "method: 'POST'" in block                      # 단건 진단(POST)
    assert "JSON.stringify({ market: market })" in block  # 마켓 하나씩
    assert "items.forEach" in block                       # 5개를 각자 띄운다
    assert "3000" not in block                            # 전체 3초 캡 폐기
    assert "PER_MARKET_MS" in block


def test_one_slow_market_does_not_poison_the_rest():
    """마켓 하나가 느려도 나머지 표기는 살아 있다 — 타이머·표기가 항목별이다."""
    block = TPL.split("S3 — 진단은")[1]
    # 타임아웃 핸들러가 **그 항목만** 바꾼다(전체 순회 giveUp 금지).
    assert "mark(el, 'is-unknown'" in block
    assert not re.search(r"querySelectorAll\('\.op-sig-item'\)\)?\.forEach\(function \(el\) \{\s*mark", block)


def test_failure_is_counted_not_blanketed():
    """실패는 **몇 개**인지 글자로 말한다 — 점 모양만으론 '미설정'과 구분이 안 된다."""
    assert "개 마켓 진단 실패 — 응답 없음" in TPL
