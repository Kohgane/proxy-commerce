"""tests/test_reject_watch_wing.py — P4 실데이터 대응: Wing 상태 스키마 + 재승인 경로.

Fellow Stagg(16358413200) 승인반려로 P4가 **첫 실데이터**를 만났다. 오너 Wing 계기판 실측:
반려 38 · 임시저장 60 · 브랜드수정 2,061 · 증빙 1.

계약:
  1. Wing 상태 유형이 계기판 축과 같다(새 체계 발명 0).
  2. 반려는 다른 상태에 묻히지 않는다(조치 대상 우선).
  3. **브랜드 수정요청·증빙 필요는 자동 조치하지 않는다**(오너 지시 — 분류·집계만).
  4. 재승인 정본 경로 = 수정(PUT) → 승인요청(PUT approvals). 수정 실패면 **승인요청 안 함**.
  5. 승인 게이트는 그대로(비가역).
"""
from __future__ import annotations

import pytest

from src.pipeline import reject_watch as RW


# ── 1·2. Wing 상태 유형 ─────────────────────────────────────────────────────────
def test_wing_states_match_dashboard_axes():
    """계기판 축: 반려·임시저장·브랜드수정·증빙 (+승인·미상)."""
    assert set(RW.WING_STATES) == {"rejected", "saved", "brand_fix", "doc_required",
                                   "approved", "unknown"}
    # 조치 가능 유형은 반려·임시저장뿐 — 브랜드수정 2,061건은 분류·집계만(오너 지시).
    actionable = {k for k, v in RW.WING_STATES.items() if v["actionable"]}
    assert actionable == {"rejected", "saved"}


@pytest.mark.parametrize("status_name,expected", [
    ("승인반려", "rejected"),
    ("REJECTED", "rejected"),
    ("임시저장", "saved"),
    ("SAVED", "saved"),
    ("브랜드 수정요청", "brand_fix"),
    ("증빙 서류 요청", "doc_required"),
    ("승인완료", "approved"),
    ("알 수 없는 상태", "unknown"),
])
def test_wing_state_classification(status_name, expected):
    assert RW.wing_state({"data": [{"statusName": status_name}]}) == expected


def test_rejected_wins_over_other_states():
    """반려가 섞이면 반려 — 조치 대상이 최신 상태에 묻히면 안 된다."""
    hist = {"data": [{"statusName": "승인반려", "comment": "이미지 규격 미달"},
                     {"statusName": "임시저장"}]}
    assert RW.wing_state(hist) == "rejected"


def test_wing_state_unknown_when_unreadable():
    """판정 불가는 unknown — 가짜 확정 0."""
    assert RW.wing_state(None) == "unknown"
    assert RW.wing_state({"data": []}) == "unknown"
    assert RW.wing_state(("200", {"data": [{"statusName": "승인반려"}]})) == "rejected"  # 튜플 안전


def test_scan_attaches_state_and_summary():
    rows_hist = {
        "S1": {"data": [{"statusName": "승인반려", "comment": "대표 이미지 해상도 미달"}]},
        "S2": {"data": [{"statusName": "브랜드 수정요청"}]},
        "S3": {"data": [{"statusName": "임시저장"}]},
    }
    items = [{"sid": s, "title": "t", "account": "gogane"} for s in rows_hist]
    scan = RW.scan_rejections(items, history_fn=lambda sid, acct: rows_hist[sid])
    by = {r["sid"]: r for r in scan["rows"]}
    assert by["S1"]["wing_state"] == "rejected" and by["S1"]["actionable"] is True
    assert by["S2"]["wing_state"] == "brand_fix" and by["S2"]["actionable"] is False
    assert by["S1"]["wing_state_ko"] == "반려"
    # 계기판 축 집계 + 조치 가능/불가 분리.
    assert scan["by_state"] == {"rejected": 1, "brand_fix": 1, "saved": 1}
    assert scan["actionable"] == 2 and scan["info_only"] == 1


def test_scan_state_unknown_on_fetch_failure():
    def _boom(sid, acct):
        raise RuntimeError("타임아웃")
    scan = RW.scan_rejections([{"sid": "S1", "title": "t"}], history_fn=_boom)
    assert scan["rows"][0]["wing_state"] == "unknown"
    assert scan["by_state"] == {"unknown": 1} and scan["actionable"] == 0


# ── 3. 자동 조치 불가 유형 차단 ─────────────────────────────────────────────────
@pytest.mark.parametrize("state", ["brand_fix", "doc_required", "approved"])
def test_non_actionable_states_never_execute(state):
    """브랜드수정 2,061 · 증빙 1은 승인이 있어도 자동 조치하지 않는다(오너 지시)."""
    calls = []
    out = RW.apply_prescription(
        {"sid": "S1", "kind": "image_spec", "wing_state": state}, approved=True,
        resubmit_fn=lambda sid, u: calls.append(sid))
    assert out["applied"] is False and calls == []
    assert RW.WING_STATES[state]["ko"] in out["reason"]


def test_rejected_state_is_actionable():
    out = RW.apply_prescription(
        {"sid": "S1", "kind": "image_spec", "wing_state": "rejected"}, approved=True,
        resubmit_fn=lambda sid, u: {"success": True, "stage": "approval"})
    assert out["applied"] is True and out["action"] == "resubmit"


def test_approval_gate_still_blocks_everything():
    calls = []
    out = RW.apply_prescription({"sid": "S1", "kind": "image_spec", "wing_state": "rejected"},
                                approved=False, resubmit_fn=lambda sid, u: calls.append(sid))
    assert out["applied"] is False and calls == [] and "승인 게이트" in out["reason"]


def test_resubmit_failure_reported_not_swallowed():
    out = RW.apply_prescription(
        {"sid": "S1", "kind": "option_value", "wing_state": "rejected"}, approved=True,
        resubmit_fn=lambda sid, u: {"success": False, "error": "상품 수정 실패", "stage": "update"})
    assert out["applied"] is False and "상품 수정 실패" in out["reason"]


def test_resubmit_receives_updates_from_row():
    seen = {}
    RW.apply_prescription(
        {"sid": "S1", "kind": "option_value", "wing_state": "rejected",
         "updates": {"items": [{"salePrice": 10000}]}},
        approved=True, resubmit_fn=lambda sid, u: seen.update({"sid": sid, "u": u}) or {"success": True})
    assert seen["sid"] == "S1" and seen["u"] == {"items": [{"salePrice": 10000}]}


# ── 4. 업로더 재승인 정본 경로 ──────────────────────────────────────────────────
def _up(monkeypatch):
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
    return CoupangUploader("ak", "sk", "A01381223", account="gogane")


def test_resubmit_approval_only_when_no_updates(monkeypatch):
    up = _up(monkeypatch)
    calls = []
    monkeypatch.setattr(up, "update_product", lambda *a, **k: pytest.fail("수정할 값이 없는데 PUT 호출됨"))
    monkeypatch.setattr(up, "request_approval",
                        lambda sid: calls.append(sid) or {"success": True, "product_id": sid})
    out = up.resubmit_product("16358413200")
    assert out["success"] is True and out["updated"] is False and calls == ["16358413200"]


def test_resubmit_updates_then_approves(monkeypatch):
    up = _up(monkeypatch)
    order = []
    monkeypatch.setattr(up, "update_product",
                        lambda sid, u: order.append(("update", sid)) or {"success": True})
    monkeypatch.setattr(up, "request_approval",
                        lambda sid: order.append(("approval", sid)) or {"success": True})
    out = up.resubmit_product("16358413200", {"sellerProductName": "고친 이름"})
    assert out["success"] is True and out["updated"] is True
    assert order == [("update", "16358413200"), ("approval", "16358413200")]   # 순서 정본


def test_resubmit_stops_when_update_fails(monkeypatch):
    """수정 실패 상태로 승인요청하면 같은 사유로 또 반려된다 — 여기서 멈춘다(왕복 절약)."""
    up = _up(monkeypatch)
    monkeypatch.setattr(up, "update_product", lambda sid, u: {"success": False, "error": "필수값 누락"})
    monkeypatch.setattr(up, "request_approval",
                        lambda sid: pytest.fail("수정 실패인데 승인요청됨"))
    out = up.resubmit_product("16358413200", {"x": 1})
    assert out["success"] is False and out["stage"] == "update" and "필수값 누락" in out["error"]


def test_resubmit_requires_sid(monkeypatch):
    assert _up(monkeypatch).resubmit_product("")["success"] is False
