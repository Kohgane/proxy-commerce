"""tests/test_t2_approve_graduation.py — T2: 승인 졸업.

**부검(2026-09-04):** P4 크론이 쓰는 상태가 `rejected` / `unknown` **둘뿐이었다.**
`WING_STATES`에 `approved`가 있는데도 **아무도 그 값을 쓰지 않았다** → 심사를 통과한 상품이
`unknown`에 머물러 `_WATCH_STATUSES`에 계속 걸리고, **2시간마다 영원히 재조회**됐다.
큐가 줄지 않으니 진짜 감시 대상이 그 안에 묻힌다.
"""
from __future__ import annotations

import pytest

from src.db import market_registrations_pg as REG
from src.pipeline import reject_watch as RW

_HIST = {
    "APPROVED": [{"statusName": "승인완료"}],
    "REJECTED": [{"statusName": "반려", "comment": "대표이미지 최소 500*500 미달"}],
    "SAVED": [{"statusName": "임시저장중"}],
}


@pytest.fixture(autouse=True)
def _clean():
    REG._MEM.clear()
    yield
    REG._MEM.clear()


def _run(sids):
    for sid in sids:
        REG.record(sid, account="gogane", title=f"상품 {sid}")
    return RW.watch_registered(
        queue_fn=lambda n: [{"sid": r["sid"], "title": r["title"], "account": "gogane"}
                            for r in REG.watch_queue(account="gogane", limit=n)],
        history_fn=lambda sid, acct: _HIST[sid],
        record_fn=lambda sid, **kw: REG.mark_checked(sid, **kw), limit=10)


def test_approved_graduates_out_of_the_queue():
    """★ 승인된 건은 큐에서 나간다 — 여태 `unknown`에 갇혀 영원히 재조회됐다."""
    _run(["APPROVED"])
    assert REG.get("APPROVED")["status"] == "approved"
    assert [r["sid"] for r in REG.watch_queue(account="gogane")] == []


def test_rejected_and_saved_keep_their_meaning():
    """반려는 나가고(처방 대상), 임시저장은 남는다(아직 조치가 필요하다)."""
    _run(["APPROVED", "REJECTED", "SAVED"])
    assert REG.get("REJECTED")["status"] == "rejected"
    assert REG.get("SAVED")["status"] == "unknown"
    # 큐에 남는 건 임시저장 하나 — 승인·반려는 확정이라 빠진다.
    assert [r["sid"] for r in REG.watch_queue(account="gogane")] == ["SAVED"]


def test_lookup_failure_never_marks_as_checked():
    """★ 조회 실패를 '확인함'으로 만들지 않는다 — 상태를 건드리지 않고 큐에 남긴다."""
    REG.record("X1", account="gogane", title="상품 X1")

    def boom(sid, acct):
        raise RuntimeError("네트워크 실패")

    RW.watch_registered(
        queue_fn=lambda n: [{"sid": "X1", "title": "상품 X1", "account": "gogane"}],
        history_fn=boom, record_fn=lambda sid, **kw: REG.mark_checked(sid, **kw), limit=10)
    assert REG.get("X1")["status"] == "submitted"          # 그대로
    assert [r["sid"] for r in REG.watch_queue(account="gogane")] == ["X1"]


def test_queue_shrinks_across_runs():
    """졸업의 요점은 **큐가 줄어드는 것**이다 — 두 번 돌려도 승인 건이 되살아나지 않는다."""
    _run(["APPROVED", "SAVED"])
    first = [r["sid"] for r in REG.watch_queue(account="gogane")]
    RW.watch_registered(
        queue_fn=lambda n: [{"sid": r["sid"], "title": r["title"], "account": "gogane"}
                            for r in REG.watch_queue(account="gogane", limit=n)],
        history_fn=lambda sid, acct: _HIST[sid],
        record_fn=lambda sid, **kw: REG.mark_checked(sid, **kw), limit=10)
    assert first == ["SAVED"]
    assert [r["sid"] for r in REG.watch_queue(account="gogane")] == ["SAVED"]


def test_approved_is_a_known_wing_state():
    """`approved`는 발명한 값이 아니다 — 이미 스키마에 있던 걸 비로소 쓰는 것이다."""
    assert RW.WING_STATES["approved"]["actionable"] is False
    assert "approved" not in REG._WATCH_STATUSES          # 큐가 그걸 빼도록 이미 돼 있었다
