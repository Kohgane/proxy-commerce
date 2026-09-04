"""tests/test_f411_approval.py — F' 승인요청 411 수리 + 임시저장 유형 신설.

**부검(2026-09-04):** 승인요청 `PUT .../approvals`가 **411 Length Required**로 끊겼다.
바디 없는 PUT을 requests가 그대로 보내면 **Content-Length가 아예 안 붙고**, 쿠팡 게이트웨이가
길이 없는 PUT을 거부한다. 오너가 본 `body=<HTML>`은 릴레이 오류가 아니라 **쿠팡의 411 에러
페이지가 그대로 릴레이돼 온 것**이다(릴레이는 status·body를 무가공 전달한다).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from src.pipeline import reject_watch as RW
from src.uploaders.coupang_uploader import CoupangUploader


class _Resp:
    headers = {"Content-Type": "application/json"}

    def __init__(self, code, text="{}"):
        self.status_code, self.text = code, text

    def json(self):
        return {"code": "SUCCESS", "data": "16369251981"}

    def raise_for_status(self):
        pass


def _uploader():
    return CoupangUploader(access_key="AK", secret_key="SK", vendor_id="A01381223", account="gogane")


def test_bodyless_put_now_declares_length():
    """★ F1/F2 — 승인요청 PUT에 `Content-Length: 0`과 빈 바디가 실린다."""
    seen = {}

    def fake(method, url, **kw):
        seen.update({"method": method, **kw})
        return _Resp(200)

    with patch("src.market_relay.requests.request", side_effect=fake):
        out = _uploader().request_approval("16369251981")

    assert out["success"] is True
    assert seen["method"] == "PUT"
    assert (seen.get("headers") or {}).get("Content-Length") == "0"
    assert seen.get("data") == b""          # 빈 바디를 **명시**해서 보낸다
    assert "json" not in seen               # json=None으로 흘려보내지 않는다(그게 411의 원인)


def test_411_is_reproducible_without_the_fix():
    """수리 전 동작(길이 미선언)에서 게이트웨이가 411을 준다 — 재현 없는 수리 금지."""
    import src.market_relay as R

    def gateway(method, url, **kw):
        has_len = "Content-Length" in (kw.get("headers") or {}) or kw.get("data") is not None
        if method.upper() == "PUT" and not has_len:
            return _Resp(411, "<html><title>411 Length Required</title></html>")
        return _Resp(200)

    with patch("src.market_relay.requests.request", side_effect=gateway):
        bad = R.relay_request("PUT", "https://api-gateway.coupang.com/x/approvals",
                              json=None, headers={"Content-Type": "application/json"},
                              timeout=30, market="coupang", key="A01381223")
        assert bad.status_code == 411 and "411" in bad.text     # 재현
        good = _uploader().request_approval("16369251981")
        assert good["success"] is True                          # 수리 후 통과


def test_signature_unaffected_by_body():
    """바디를 바꿔도 HMAC은 불변이다 — CEA는 method+path+date만 서명한다."""
    up = _uploader()
    import inspect
    src = inspect.getsource(up._generate_hmac_signature)
    assert "data" not in src and "body" not in src


@pytest.mark.parametrize("comment", ["임시저장", "임시저장중", "SAVED"])
def test_saved_pending_is_its_own_kind(comment):
    """★ F3 — '임시저장'은 미분류가 아니다. 처방이 다르다(승인 재요청)."""
    r = RW.classify_rejection(comment)
    assert r["kind"] == "saved_pending"
    assert r["prescription"] == "request_approval"
    assert "재등록 아님" in r["prescription_ko"]     # 재등록하면 동일상품 다중등록이 된다


@pytest.mark.parametrize("comment,expected", [
    ("임시저장 · 대표이미지 최소 500*500 미달", "image_spec"),
    ("유효하지 않은 구매 옵션 값 혹은 단위 입니다.", "option_unit"),
    ("상표권 침해 우려", "trademark"),
    ("", "unknown"),
])
def test_specific_reason_still_wins(comment, expected):
    """구체 사유가 있으면 그쪽이 이긴다 — 임시저장은 **사유가 없을 때**의 판정이다."""
    assert RW.classify_rejection(comment)["kind"] == expected


def test_approval_action_is_gated_and_not_reissue():
    """★ F4 — 승인 재요청은 오너 승인 게이트 뒤에서만. 그리고 **재등록이 아니다.**"""
    row = {"sid": "16369251981", "kind": "saved_pending"}
    held = RW.apply_prescription(row, approved=False)
    assert held["applied"] is False and "승인 게이트" in held["reason"]

    calls = []
    done = RW.apply_prescription(row, approved=True,
                                 approve_fn=lambda sid: (calls.append(sid), {"success": True})[1],
                                 reissue_fn=lambda sid: pytest.fail("재등록이 호출됐다"),
                                 reupload_fn=lambda sid, r: pytest.fail("재등록이 호출됐다"))
    assert done["applied"] is True and done["action"] == "request_approval"
    assert calls == ["16369251981"]


def test_missing_handler_is_honest():
    """핸들러가 없으면 '했다'고 하지 않는다(가짜 성공 0)."""
    out = RW.apply_prescription({"sid": "1", "kind": "saved_pending"}, approved=True)
    assert out["applied"] is False and "미주입" in out["reason"]


def test_admin_gate_wires_approve_fn():
    """관리자 실행 라우트가 승인요청 핸들러를 실제로 주입한다."""
    from pathlib import Path
    src = Path("src/dashboard/admin_views.py").read_text(encoding="utf-8")
    assert "approve_fn=lambda sid: up.request_approval(sid)" in src


# ── F5: 02 카드가 자기 제목을 반박하던 결함 ──────────────────────────────────────

def test_02_card_no_longer_excludes_rejections():
    """★ F5 — 카드 제목은 '반려 감시'인데 소스가 `watch_queue`뿐이라 **rejected를 구조적으로
    제외**했다. 03에 REJECTED 2건이 떠 있는데 02는 '반려 건이 없습니다'라고 말했다.
    """
    from src.db import market_registrations_pg as REG
    from src.pipeline import ops_snapshot as ops

    assert "rejected" not in REG._WATCH_STATUSES          # 큐가 반려를 빼는 건 설계대로다
    with patch.object(REG, "enabled", return_value=True), \
         patch.object(REG, "watch_queue", return_value=[{"sid": "A1", "title": "감시 대기 건"}]), \
         patch.object(REG, "recent_rejected",
                      return_value=[{"sid": "B1", "title": "반려 확정 건", "reject_kind": "image_spec"}]):
        snap = ops.recent_rejections(limit=5)

    assert snap["connected"] is True
    assert snap["rejected"] == 1 and snap["watching"] == 1
    phases = [r["phase"] for r in snap["rows"]]
    assert phases == ["rejected", "watching"]             # 조치가 필요한 쪽이 위
    assert {r["sid"] for r in snap["rows"]} == {"A1", "B1"}


def test_recent_rejected_reads_what_the_queue_skips():
    """`recent_rejected`는 큐가 건너뛰는 상태를 읽는다 — 큐를 넓히지 않는다(감시 의미 보존)."""
    from src.db import market_registrations_pg as REG
    REG._MEM.clear()
    REG.record("A1", account="gogane", title="감시 대기")
    REG.record("B1", account="gogane", title="반려 확정")
    REG.mark_checked("B1", status="rejected", reject_kind="image_spec", reject_comment="규격 미달")
    try:
        watching = [r["sid"] for r in REG.watch_queue(account="gogane")]
        rejected = [r["sid"] for r in REG.recent_rejected(account="gogane")]
        assert watching == ["A1"] and rejected == ["B1"]   # 겹치지 않고, 둘 다 잡힌다
        assert REG.recent_rejected(account="gogane")[0]["reject_kind"] == "image_spec"
    finally:
        REG._MEM.clear()


def test_card_labels_the_two_phases():
    """두 상태를 한 줄로 뭉개지 않는다 — 라벨로 갈린다."""
    from pathlib import Path
    tpl = Path("src/seller_console/templates/dashboard.html").read_text(encoding="utf-8")
    assert "r.phase == 'rejected'" in tpl
    assert "반려 {{ ops.rejections.rejected }}" in tpl and "감시 대기 {{ ops.rejections.watching }}" in tpl
