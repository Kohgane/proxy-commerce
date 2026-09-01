"""tests/test_k_agency_talkstore.py — K2: 연동대행사(톡스토어) 모델.

**원칙: 실전송 0.** 톡스토어는 통과 이력 정본이 없고, 공개 문서 실측(K0)도 못 했다
(컨테이너에서 카카오 문서 도메인 차단 — HTTP 000). 그래서 이 트랙은 **자리와 잠금**까지다.
쿠팡이 카나리 6차 왕복을 태운 이유가 정확히 "정본 없이 보낸 것"이라 같은 길을 가지 않는다.

계약이 지키는 것: Admin키 노출 0 · 판매자 키 평문 0 · 대행사 경로에서 실전송 함수 호출 0.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.pipeline import agency_link as ag
from src.pipeline.register_adapters import get_adapter
from src.seller_console import market_credentials as mc

AGENCY_SRC = Path("src/pipeline/agency_link.py")


# ── 축 분리: 대행사 키(서버) vs 판매자 키(판매자) ─────────────────────────────

def test_admin_key_is_server_side_only():
    """★ 대행사 Admin키는 **서버 비밀 1개** — 판매자 입력 화면에 자리가 없다."""
    fields = [f["env"] for f in mc.MARKET_CRED_FIELDS["talkstore"]]
    assert fields == ["TALKSTORE_SELLER_API_KEY", "TALKSTORE_STORE_ID"]
    for f in fields:
        assert "ADMIN" not in f.upper(), f
    assert ag.ADMIN_KEY_ENV == "TALKSTORE_ADMIN_KEY"


def test_admin_key_value_never_leaves_the_module(monkeypatch):
    """★ 존재 여부만 답하고 **값은 반환하지 않는다**(로그·응답에 실릴 여지 0)."""
    monkeypatch.setenv(ag.ADMIN_KEY_ENV, "super-secret-admin-key")
    assert ag.admin_key_configured() is True
    blob = json.dumps(ag.mapping_status("u1"), ensure_ascii=False)
    assert "super-secret-admin-key" not in blob
    # 소스에도 값을 찍는 코드가 없어야 한다(로그 노출 0).
    src = AGENCY_SRC.read_text(encoding="utf-8")
    assert "getenv(ADMIN_KEY_ENV)" in src or 'os.getenv(ADMIN_KEY_ENV' in src
    assert not re.search(r"logger\.\w+\([^)]*ADMIN_KEY", src), "Admin키가 로그에 실린다"


def test_seller_key_is_marked_secret_and_not_stored_plaintext():
    """판매자 키는 secret 표시 + 기존 Fernet 저장 경로를 그대로 탄다(새 저장소 0)."""
    fld = next(f for f in mc.MARKET_CRED_FIELDS["talkstore"]
               if f["env"] == "TALKSTORE_SELLER_API_KEY")
    assert fld["secret"] is True and fld["required"] is True
    src = AGENCY_SRC.read_text(encoding="utf-8")
    assert "market_credentials" in src          # 저장은 기존 계층에 위임
    for own_store in ("open(", "json.dump", "INSERT INTO"):
        assert own_store not in src, own_store  # 자체 저장소를 새로 파지 않는다


# ── 매핑 상태 — 가짜 활성 금지 ────────────────────────────────────────────────

def test_unmapped_when_no_seller_key(monkeypatch):
    monkeypatch.setattr(ag, "_seller_creds", lambda sid, market="talkstore": {})
    st = ag.mapping_status("u1")
    assert st["status"] == "unmapped" and st["has_seller_key"] is False
    assert st["blockers"], "무엇이 막는지 말해야 한다"


def test_key_present_but_not_approved_is_pending_not_active(monkeypatch):
    """★ 키가 둘 다 있어도 **매핑 승인 전엔 활성이 아니다** — 가짜 활성 금지."""
    monkeypatch.setenv(ag.ADMIN_KEY_ENV, "k")
    monkeypatch.setattr(ag, "_seller_creds",
                        lambda sid, market="talkstore": {"TALKSTORE_SELLER_API_KEY": "sk"})
    st = ag.mapping_status("u1")
    assert st["status"] == "pending" and st["status_ko"] == "매핑 대기"
    assert st["has_seller_key"] is True and st["admin_ready"] is True


def test_blockers_name_the_missing_side(monkeypatch):
    """막힌 쪽을 **구분해서** 말한다 — 서버 Admin키인지 판매자 키인지."""
    monkeypatch.delenv(ag.ADMIN_KEY_ENV, raising=False)
    monkeypatch.setattr(ag, "_seller_creds", lambda sid, market="talkstore": {})
    blockers = " ".join(ag.mapping_status("u1")["blockers"])
    assert "Admin키" in blockers and "판매자" in blockers


# ── 실전송 0 ──────────────────────────────────────────────────────────────────

def test_ready_to_register_is_false_even_when_keys_present(monkeypatch):
    """★ 키가 다 있어도 **정본 없이는 못 보낸다**. 문서 실측이 먼저다."""
    monkeypatch.setenv(ag.ADMIN_KEY_ENV, "k")
    monkeypatch.setattr(ag, "_seller_creds",
                        lambda sid, market="talkstore": {"TALKSTORE_SELLER_API_KEY": "sk"})
    ok, why = ag.ready_to_register("u1")
    assert ok is False and "정본" in why and "추측 전송 금지" in why


def test_agency_module_calls_no_transport():
    """★ 대행사 코드 경로에 **실전송 함수가 없다**(테스트가 검사 — 실수로도 못 보낸다)."""
    src = AGENCY_SRC.read_text(encoding="utf-8")
    for transport in ("requests.", "relay_request", "urlopen", "httpx", "session.post"):
        assert transport not in src, transport


def test_adapter_reports_not_ready_and_blocks(monkeypatch):
    """어댑터는 `ready=False`를 정직 신고하고, 등록 시도는 **전송 없이** 차단한다."""
    ad = get_adapter("talkstore")
    st = ad.canon_status()
    assert st["ready"] is False and set(st["gaps"]) == {"notice", "delivery", "options", "category"}
    res = ad.register({"sku": "x"}, "seller1")
    assert res["success"] is False and res["held"] is True
    assert "추측 전송 금지" in res["error"]


# ── 화면 — 있고 아직 못 쓴다고 말한다 ─────────────────────────────────────────

def test_register_pipe_shows_talkstore_disabled():
    """노출하되 **비활성**. 감추면 '왜 없냐'가 되고, 고를 수 있으면 추측 전송이 된다."""
    tpl = Path("src/seller_console/templates/register_pipe.html").read_text(encoding="utf-8")
    assert '<option value="talkstore" disabled>' in tpl
    assert "연동 준비 중" in tpl


def test_connect_screen_has_talkstore_without_admin_key():
    """연동 화면에 톡스토어가 있고, 거기에 Admin키 입력란은 **없다**."""
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    html = app.test_client().get("/seller/markets/connect").get_data(as_text=True)
    assert "톡스토어" in html
    assert "TALKSTORE_ADMIN_KEY" not in html and "Admin키" not in html


def test_other_markets_untouched():
    """기존 5마켓은 그대로 — 대행사 축 추가가 회귀를 만들지 않는다."""
    for m in ("coupang", "smartstore", "elevenst", "shopify", "woocommerce"):
        assert m in mc.SUPPORTED_MARKETS
    for m, ready in (("coupang", True), ("smartstore", True), ("woocommerce", True)):
        assert get_adapter(m).canon_status()["ready"] is ready
