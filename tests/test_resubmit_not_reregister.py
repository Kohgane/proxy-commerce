"""tests/test_resubmit_not_reregister.py — 반려 수리는 **재제출**이지 신규 등록이 아니다.

오너 확인 결과 실측: 카나리 5~10차는 전부 `register_source_rows` → `upload_product` →
**POST .../seller-products**(신규 생성)였다. Fellow Stagg 16358413200도 10차가 새로 만든 상품이다.
`resubmit_product`(PUT)는 #667에서 만들어졌고 카나리 경로에 연결된 적이 없다.

문제: 등록 파이프에 **중복 방지가 없었다** — 같은 URL을 다시 넣으면 또 POST해서 같은 상품이 두 건 생긴다.

계약:
  1. 신규 등록 경로는 POST, 재제출 경로는 PUT 수정 + PUT approvals (섞이지 않는다).
  2. 이미 등록된 SKU면 **신규 등록 안 함** + 기존 sid 안내(반려건이면 재제출 경로 명시).
  3. 조회 실패는 등록을 막지 않는다(가용성 우선 — 조회 장애로 파이프가 멈추면 안 된다).
"""
from __future__ import annotations

import pytest

from src.db import market_registrations_pg as REG
from src.pipeline import register_pipe as RP


@pytest.fixture(autouse=True)
def _clean():
    REG.reset_memory()
    yield
    REG.reset_memory()


_ROWS = [{"url": "https://www.amazon.de/-/en/dp/B0GS4698H2", "title_ko": "Fellow Stagg 주전자",
          "sale_krw": 894000, "excluded": False}]
_ENRICH = {"images": ["https://m.media-amazon.com/images/I/71a.jpg"],
           "description_html": "<p>d</p>", "category_code": "GEN"}


def _run(dispatch, lookup_fn=None):
    return RP.register_source_rows(_ROWS, dispatch_fn=dispatch, enrich_fn=lambda r: dict(_ENRICH),
                                   approved=True, account="gogane", sleep_fn=lambda s: None,
                                   lookup_fn=lookup_fn)


# ── 1. 두 경로가 쓰는 HTTP 메서드가 다르다 ──────────────────────────────────────
def test_new_registration_uses_post_and_resubmit_uses_put():
    """소스 계약: 신규=POST seller-products · 재제출=PUT 수정 + PUT approvals."""
    from pathlib import Path
    src = Path("src/uploaders/coupang_uploader.py").read_text(encoding="utf-8")
    # upload_product(신규)는 POST.
    up_body = src.split("def upload_product")[1].split("def update_product")[0]
    assert "_api_request('POST', path, data=payload)" in up_body
    assert "approvals" in up_body                    # 등록 후 승인요청 2단계(정본)
    # resubmit_product(재제출)는 POST를 쓰지 않는다 — 신규 생성 금지.
    re_body = src.split("def resubmit_product")[1].split("\n    def ")[0]
    assert "'POST'" not in re_body and '"POST"' not in re_body
    assert "update_product" in re_body and "request_approval" in re_body


def test_resubmit_never_creates_new_product(monkeypatch):
    """재제출은 기존 sid만 건드린다 — 새 상품번호가 생기지 않는다."""
    for k, v in {
        "COUPANG_GOGANE_OUTBOUND_SHIPPING_PLACE_CODE": "1",
        "COUPANG_GOGANE_RETURN_CENTER_CODE": "R1",
        "COUPANG_GOGANE_RETURN_ZIP_CODE": "12345",
        "COUPANG_GOGANE_RETURN_ADDRESS": "서울시",
        "COUPANG_GOGANE_RETURN_CHARGE_NAME": "담당자",
        "COUPANG_GOGANE_COMPANY_CONTACT_NUMBER": "02-000-0000",
        "COUPANG_GOGANE_VENDOR_USER_ID": "gogane01",
    }.items():
        monkeypatch.setenv(k, v)
    from src.uploaders.coupang_uploader import CoupangUploader
    monkeypatch.setattr("time.sleep", lambda s: None)
    up = CoupangUploader("ak", "sk", "A01381223", account="gogane")
    seen = []

    def _req(method, path, data=None, **k):
        seen.append((str(method).upper(), path))
        if str(method).upper() == "POST":
            pytest.fail("재제출인데 신규 등록(POST)이 호출됨")
        return {"code": "SUCCESS"}

    monkeypatch.setattr(up, "_api_request", _req)
    out = up.resubmit_product("16358413200", {"sellerProductName": "고친 이름"})
    assert out["success"] is True
    assert [m for m, _ in seen] == ["PUT", "PUT"]                 # 수정 → 승인요청
    assert all("16358413200" in p for _, p in seen)               # 기존 sid만


# ── 2. 중복 등록 방지 ───────────────────────────────────────────────────────────
def test_already_registered_sku_is_not_reregistered():
    REG.record("16358413200", account="gogane", vendor_sku="B0GS4698H2",
               title="Fellow Stagg 주전자")
    calls = []
    out = _run(lambda pd, a: calls.append(pd) or {"success": True, "product_id": "NEW"},
               lookup_fn=lambda sku, acct: REG.find_by_vendor_sku(sku, account=acct))
    assert calls == []                                            # POST 안 함
    r = out["results"][0]
    assert r["duplicate"] is True and r["registered"] is False
    assert r["product_id"] == "16358413200"                       # 기존 상품번호 안내
    assert out["duplicates"] == 1 and out["registered"] == 0
    assert out["failed"] == 0                                     # 중복은 '실패'가 아니다


def test_rejected_item_points_to_resubmit_path():
    """반려건이면 사유에 **재제출 경로**를 명시한다(신규 등록 유도 금지)."""
    REG.record("16358413200", account="gogane", vendor_sku="B0GS4698H2")
    REG.mark_checked("16358413200", status="rejected", reject_kind="image_spec",
                     prescription="reupload")
    out = _run(lambda pd, a: pytest.fail("반려건인데 신규 등록됨"),
               lookup_fn=lambda sku, acct: REG.find_by_vendor_sku(sku, account=acct))
    r = out["results"][0]
    assert r["existing_status"] == "rejected"
    assert "재제출" in r["reason"] and "16358413200" in r["reason"]


def test_unregistered_sku_still_registers():
    """대장에 없으면 정상 신규 등록 — 과잉 차단 0."""
    calls = []
    out = _run(lambda pd, a: calls.append(pd) or {"success": True, "product_id": "NEW1"},
               lookup_fn=lambda sku, acct: REG.find_by_vendor_sku(sku, account=acct))
    assert len(calls) == 1 and out["registered"] == 1 and out["duplicates"] == 0


def test_other_account_registration_does_not_block():
    """계정이 다르면 별개 등록이다(고가네/우주대행 양계정 운영)."""
    REG.record("16358413200", account="woojoo", vendor_sku="B0GS4698H2")
    calls = []
    out = _run(lambda pd, a: calls.append(pd) or {"success": True, "product_id": "NEW1"},
               lookup_fn=lambda sku, acct: REG.find_by_vendor_sku(sku, account=acct))
    assert len(calls) == 1 and out["registered"] == 1


def test_lookup_failure_does_not_block_registration():
    """조회 장애로 파이프가 멈추면 안 된다 — 가용성 우선(정직: 중복 위험은 대장 유니크가 최종 방어)."""
    def _boom(sku, acct):
        raise RuntimeError("PG 연결 실패")
    calls = []
    out = _run(lambda pd, a: calls.append(pd) or {"success": True, "product_id": "NEW1"},
               lookup_fn=_boom)
    assert len(calls) == 1 and out["registered"] == 1


def test_no_lookup_fn_keeps_old_behavior():
    """lookup_fn 미주입(구 호출부)은 기존 동작 — 무회귀."""
    calls = []
    out = _run(lambda pd, a: calls.append(pd) or {"success": True, "product_id": "NEW1"})
    assert len(calls) == 1 and out["registered"] == 1


# ── 대장 조회 ───────────────────────────────────────────────────────────────────
def test_find_by_vendor_sku():
    REG.record("SP1", account="gogane", vendor_sku="B0GS4698H2", title="t")
    assert REG.find_by_vendor_sku("B0GS4698H2")["product_id"] == "SP1"
    assert REG.find_by_vendor_sku("B0GS4698H2", account="woojoo") is None
    assert REG.find_by_vendor_sku("") is None
    assert REG.find_by_vendor_sku("UNKNOWN") is None


def test_route_wires_lookup_fn():
    from pathlib import Path
    src = Path("src/seller_console/views.py").read_text(encoding="utf-8")
    assert "lookup_fn=_lookup_registration" in src
    assert "find_by_vendor_sku" in src
