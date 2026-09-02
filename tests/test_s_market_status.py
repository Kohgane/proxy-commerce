"""tests/test_s_market_status.py — S1·S2: 연결 판정 단일화 + 11번가 -997 처방.

**왜 이 계약이 필요했나(실측 2026-09-02):** 같은 질문("이 마켓 연결됐나")에 판정기가 둘이었다.
`/seller/markets`는 마켓별 하드코딩 if로, `/markets/connect`는 필드 정의로 판정했고,
마켓 코드도 달라서(`11st` vs `elevenst`) **11번가 키가 있어도 화면마다 답이 갈렸다.**
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.seller_console import market_credentials as mc

VIEWS = Path("src/seller_console/views.py")
DIAG = Path("src/seller_console/market_integration_diagnostics.py")


# ── S1: 판정기는 하나 ─────────────────────────────────────────────────────────

def test_s1_single_connection_judge():
    """★ 판정기 **2개 존재 금지**. 옛 `_market_is_configured`(하드코딩 if)는 제거됐다."""
    src = VIEWS.read_text(encoding="utf-8")
    body = "\n".join(l for l in re.sub(r'"""[\s\S]*?"""', "", src).splitlines()
                     if not l.lstrip().startswith("#"))
    assert "def _market_is_configured" not in body, "옛 판정기가 살아 있다"
    # 화면용 래퍼는 남되, 판정 자체는 위임한다.
    assert "mc.is_connected(_seller_id(), marketplace)" in body


def test_s1_alias_makes_both_screens_agree(monkeypatch):
    """★ 같은 마켓을 어느 코드로 물어도 같은 답 — 코드 차이로 갈리지 않는다."""
    monkeypatch.setenv("ELEVENST_API_KEY", "k")
    assert mc.canonical_market("11st") == "elevenst"
    assert mc.is_connected("u1", "11st") is mc.is_connected("u1", "elevenst") is True
    for alias, canon in (("naver", "smartstore"), ("wc", "woocommerce")):
        assert mc.canonical_market(alias) == canon
    # 모르는 코드는 조용히 바꾸지 않는다.
    assert mc.canonical_market("someshop") == "someshop"


def test_s1_screens_use_the_same_judge(monkeypatch):
    """두 화면이 실제로 같은 결과를 낸다(회귀 재현 방지)."""
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    monkeypatch.setenv("ELEVENST_API_KEY", "k")
    from src.seller_console import views
    from src.order_webhook import app
    with app.test_request_context("/seller/markets"):
        a = views._market_configured_for_seller("11st")
    b = mc.is_connected("default", "elevenst")
    assert a is b is True


def test_s1_source_badge_distinguishes_origin(tmp_path, monkeypatch):
    """★ '연결됨'만으론 내 키인지 서버 설정인지 모른다 — 출처를 따로 답한다."""
    monkeypatch.setenv("MARKET_CRED_DIR", str(tmp_path))
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.delenv("ELEVENST_API_KEY", raising=False)
    import importlib
    from src.seller_console import market_credentials as m
    importlib.reload(m)
    assert m.credential_source("s1", "elevenst") == ""            # 아무것도 없음
    monkeypatch.setenv("ELEVENST_API_KEY", "server-key")
    assert m.credential_source("s1", "elevenst") == "server"      # 서버 설정
    m.save("s1", "elevenst", {"ELEVENST_API_KEY": "my-key"})
    assert m.credential_source("s1", "elevenst") == "seller"      # 내 키가 우선
    assert m.SOURCE_LABEL["seller"] == "내 키" and m.SOURCE_LABEL["server"] == "서버 설정"
    importlib.reload(m)


# ── S2: 11번가 -997 ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("detail", [
    '{"resultCode":"-997","resultMessage":"등록된 API 정보가 없습니다."}',
    "11st API error: resultCode -997",
    "응답 코드 -997",
])
def test_s2_997_is_its_own_error_code(detail):
    """★ -997은 `api_error`로 뭉개지지 않는다 — 무엇을 해야 하는지가 달라서다."""
    from src.seller_console.market_integration_diagnostics import _parse_error_code
    assert _parse_error_code(detail) == "openapi_not_registered"


def test_s2_other_codes_unchanged():
    """기존 분기는 그대로(회귀 0)."""
    from src.seller_console.market_integration_diagnostics import _parse_error_code
    assert _parse_error_code("HTTP 401 unauthorized") == "token_expired"
    assert _parse_error_code("HTTP 403 scope") == "scope_insufficient"
    assert _parse_error_code("무슨 일인지 모를 오류") == "api_error"


def test_s2_action_text_tells_what_to_do():
    """조치 문구가 **셀러가 할 일**을 말한다. 모르는 코드는 지어내지 않는다."""
    from src.seller_console.market_integration_diagnostics import error_action
    act = error_action("openapi_not_registered")
    assert "셀러오피스" in act and "OpenAPI" in act and "IP" in act
    assert error_action("api_error") == "" and error_action("") == ""


def test_s2_ip_list_not_single_hardcoded(monkeypatch):
    """★ Render 아웃바운드 IP는 복수 — 하나만 등록하면 다른 IP로 나갈 때 다시 막힌다."""
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.seller_console import views
    monkeypatch.setenv("SERVER_OUTBOUND_IP", "74.220.49.7, 74.220.52.223")
    assert views._server_outbound_ips() == ["74.220.49.7", "74.220.52.223"]
    assert views._server_outbound_ip() == "74.220.49.7"           # 단일 표시는 첫 값
    # 템플릿이 목록과 '전부가 아닐 수 있다'는 안내를 갖고 있다.
    tpl = Path("src/seller_console/templates/markets_connect.html").read_text(encoding="utf-8")
    assert "server_ips" in tpl and "Outbound IP 목록을 전부" in tpl
    assert "11번가" in tpl                                         # 11번가도 IP 등록 대상


def test_s2_eleven_st_is_direct_not_relayed():
    """실측 기록 — 11번가는 **Render 직발**이다(릴레이 IP를 안내하면 틀린 답이 된다).

    `relay_request`를 부르지만 `elevenst`가 IP 게이트 목록에 없고 `api.11st.co.kr`도
    릴레이 허용 호스트가 아니라 패스스루로 직접 나간다. 이 전제가 바뀌면 안내 문구도 바뀌어야 한다.
    """
    from urllib.parse import urlparse
    import src.market_relay as R
    from src.uploaders import elevenst_uploader as E
    host = (urlparse(E._BASE_URL).hostname or "").lower()
    assert host == "api.11st.co.kr"
    assert "elevenst" not in R._IP_GATED_MARKETS and "11st" not in R._IP_GATED_MARKETS
    assert host not in R._API_RELAY_ALLOWED_HOSTS
