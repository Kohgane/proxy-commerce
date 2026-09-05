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


# ── W5: 폴링 큐 졸업 확대 + dry-run ─────────────────────────────────────────────

_W5_HIST = {
    "A": [{"statusName": "승인완료"}],
    "B": [{"statusName": "반려", "comment": "대표이미지 최소 500*500"}],
    "C": [{"statusName": "임시저장중"}],
    "D": [{"statusName": "브랜드 수정 요청"}],
    "E": [{"statusName": "증빙 서류 첨부 요청"}],
}


def _w5_run(**kw):
    q = [{"sid": k, "title": f"상품 {k}", "account": "gogane"} for k in _W5_HIST]
    return RW.watch_registered(queue_fn=lambda n: q,
                               history_fn=lambda s, a: _W5_HIST[s], limit=10, **kw)


def test_dry_run_writes_nothing_but_counts():
    """★ 2천 건 일괄 변경 앞이라 **쓰기 전에 세는** 길이 있어야 한다."""
    def boom(*a, **k):
        raise AssertionError("dry-run이 기록했다")

    out = _w5_run(record_fn=boom, dry_run=True)
    assert out["dry_run"] is True and out["recorded"] == 0
    assert out["would_change"] == {"approved": 1, "rejected": 1, "unknown": 1,
                                   "brand_fix": 1, "doc_required": 1}
    assert out["would_graduate"] == 3          # approved + brand_fix + doc_required


def test_dry_run_does_not_notify():
    """세어 보는 것만으로 사람을 깨우지 않는다."""
    def ring(*a, **k):
        raise AssertionError("dry-run이 알림을 보냈다")

    _w5_run(record_fn=lambda *a, **k: True, notify_fn=ring, dry_run=True)


def test_dry_run_and_write_use_the_same_judge():
    """★ 세는 쪽과 쓰는 쪽이 갈리면 **미리 본 숫자가 거짓**이 된다 — 판정 함수는 하나다."""
    REG._MEM.clear()
    for sid in _W5_HIST:
        REG.record(sid, account="gogane", title=f"상품 {sid}")
    preview = _w5_run(record_fn=lambda *a, **k: True, dry_run=True)["would_change"]
    _w5_run(record_fn=lambda sid, **kw: REG.mark_checked(sid, **kw))
    actual = {}
    for sid in _W5_HIST:
        st = REG.get(sid)["status"]
        actual[st] = actual.get(st, 0) + 1
    assert preview == actual


def test_non_actionable_classifications_leave_the_polling_queue():
    """브랜드 수정요청·증빙 필요는 분류가 확정된 건 — 폴링만 멈춘다(대장 행은 남는다)."""
    REG._MEM.clear()
    for sid in _W5_HIST:
        REG.record(sid, account="gogane", title=f"상품 {sid}")
    _w5_run(record_fn=lambda sid, **kw: REG.mark_checked(sid, **kw))
    assert [r["sid"] for r in REG.watch_queue(account="gogane")] == ["C"]   # 임시저장만 남는다
    for sid in ("A", "D", "E"):
        assert REG.get(sid) is not None, "졸업이 대장 행을 지웠다"          # 기록은 유지


def test_unknown_never_graduates():
    """★ `unknown`도 actionable=False지만 졸업 대상이 아니다.

    '미상'은 아직 아무것도 확정 안 된 상태다 — 졸업은 "확정됐다"는 뜻이지
    "조치 안 한다"는 뜻이 아니다.
    """
    assert "unknown" not in RW.GRADUATING_STATES
    assert RW.WING_STATES["unknown"]["actionable"] is False       # 그런데도 남는다
