"""tests/test_wing_state_priority.py — 폴백 수리: wing_state 확정값 우선.

부검(2026-09-05): 감시 상태 판정이 `comment` **유무만** 봤다. 그런데
`latest_rejection_comment`에는 '조용한 누락 방지' 폴백이 있어 **반려 표기가 없어도
마지막 메모를 돌려준다.** 그래서 심사중 메모 한 줄이 상품을 `rejected`로 만들고
감시 큐 밖으로 밀어냈다.

**'사유가 있다'와 '반려다'는 다른 명제다.**
`wing_state`가 확정값이면 그걸 믿는다. comment는 *무엇이 문제인가*(kind)를 정하는
재료지 *확정인가*(status)를 정하는 근거가 아니다.

폴백은 **제거가 아니라 용도 축소**다 — kind 판정엔 여전히 쓴다(원래 몫만 남긴다).
"""
from __future__ import annotations

from src.db.market_registrations_pg import _WATCH_STATUSES
from src.pipeline import reject_watch as RW


def _hist(status_name: str, comment: str | None = None) -> dict:
    row: dict = {"statusName": status_name}
    if comment is not None:
        row["comment"] = comment
    return {"data": [row]}


def _judge(status_name: str, comment: str | None = None, title: str = "ALPAKA 에어 슬링 크로스백"):
    """실제 파이프와 같은 순서로 판정한다 — 조각을 따로 부르면 통합 결함을 놓친다."""
    h = _hist(status_name, comment)
    c = RW.latest_rejection_comment(h)
    row = {"comment": c, "wing_state": RW.wing_state(h), **RW.classify_rejection(c, title=title)}
    status = RW._next_status(row)
    return {"comment": c, "wing_state": row["wing_state"], "kind": row["kind"],
            "status": status, "stays": status in _WATCH_STATUSES}


# ── A~E 5케이스 (오너 실측표) ────────────────────────────────────────────────
def test_case_a_real_rejection_still_leaves_the_queue():
    """A 진짜 반려 — **현행 판정 유지가 회귀 게이트다.** 반려는 확정이라 큐를 떠난다."""
    r = _judge("승인반려", "대표이미지는 최소 500*500 입니다")
    assert r["wing_state"] == "rejected"
    assert r["status"] == "rejected" and r["stays"] is False
    assert r["kind"] == "image_spec", "사유 분류는 그대로 — comment는 kind 판정엔 계속 쓴다"


def test_case_b_saved_now_stays_in_the_queue():
    """B 임시저장 — 전에는 `rejected`로 앉아 큐를 떠났다. 조치 대상이지 확정이 아니다."""
    r = _judge("임시저장", "임시저장 되었습니다")
    assert r["wing_state"] == "saved"
    assert r["status"] == "saved" and r["stays"] is True
    assert r["kind"] == "saved_pending", "처방은 승인요청 — 재등록이 아니다"


def test_case_c_non_rejection_memo_no_longer_seats_as_rejected():
    """★ C 심사중 메모 — 이 결함의 얼굴. '임시저장' 문자열도 없는 평범한 메모 한 줄이
    상품을 `rejected`로 만들고 큐 밖으로 밀어냈다."""
    r = _judge("승인심사중", "담당자 배정 완료")
    assert r["status"] != "rejected", "메모가 반려로 앉았다 — 폴백이 판정 근거로 승격됐다"
    assert r["status"] == "unknown" and r["stays"] is True


def test_case_d_no_comment_stays():
    """D 코멘트 없음 — 아무것도 확인 못 했으니 큐에 남는다(전부터 옳던 동작)."""
    r = _judge("승인심사중")
    assert r["comment"] == "" and r["status"] == "unknown" and r["stays"] is True


def test_case_e_approved_still_graduates():
    """E 승인 + 메모 — **현행 판정 유지가 회귀 게이트다.** 메모가 있어도 승인은 승인이다."""
    r = _judge("승인완료", "검수 통과")
    assert r["wing_state"] == "approved"
    assert r["status"] == "approved" and r["stays"] is False


# ── 원칙 ────────────────────────────────────────────────────────────────────
def test_comment_alone_never_decides_status():
    """comment는 kind 전용으로 강등됐다 — 같은 메모라도 wing_state가 상태를 정한다."""
    memo = "담당자 배정 완료"
    assert _judge("승인반려", memo)["status"] == "rejected"
    assert _judge("승인심사중", memo)["status"] == "unknown"
    assert _judge("임시저장", memo)["status"] == "saved"
    assert _judge("승인완료", memo)["status"] == "approved"


def test_fallback_is_narrowed_not_removed():
    """★ 폴백은 **제거가 아니라 용도 축소**다 — '조용한 누락 방지'의 원래 몫은 남는다.

    반려 표기가 없어도 메모를 건져 와야 사람이 화면에서 사유를 읽는다.
    달라진 건 그 메모가 **상태를 정하지 않는다**는 것뿐이다.
    """
    r = _judge("승인심사중", "담당자 배정 완료")
    assert r["comment"] == "담당자 배정 완료", "폴백이 사라졌다 — 사유가 화면에서 증발한다"
    assert r["status"] == "unknown"


def test_unknown_wing_state_is_not_settled():
    """WING_STATES에 없는 새 상태는 **확정으로 단정하지 않는다**(가짜 확정 0)."""
    r = _judge("무슨무슨신규상태", "메모")
    assert r["status"] == "unknown" and r["stays"] is True


def test_query_failure_leaves_status_untouched():
    """조회 실패는 상태를 안 바꾼다 — 확인 실패를 '확인함'으로 만들지 않는다."""
    assert RW._next_status({"error": "timeout", "wing_state": "rejected", "comment": "x"}) == ""


def test_graduating_states_unchanged():
    """#700 졸업 경로는 그대로 — approved·brand_fix·doc_required는 확정이라 큐를 떠난다."""
    for st in RW.GRADUATING_STATES:
        assert RW._next_status({"wing_state": st}) == st
        assert st not in _WATCH_STATUSES


# ── 저장 쪽까지 같이 본다(반쪽 수리 금지) ────────────────────────────────────
def test_saved_is_actually_kept_by_the_queue():
    """★ 판정만 고치고 저장 쪽을 빼먹으면 `saved`를 써도 행이 그대로 큐를 떠난다.

    이 프로젝트의 단골 결함이 '이중 구현, 한쪽만 수리'라 두 층을 한 계약에서 본다.
    """
    assert "saved" in _WATCH_STATUSES
    assert set(RW.UNSETTLED_STATES) <= set(_WATCH_STATUSES), \
        "미확정 상태 중 큐가 안 받는 게 있다 — 그 건은 조용히 관측 밖으로 나간다"


def test_cron_log_reports_stay_vs_graduate():
    """실전 검증은 로그로 한다 — 다음 회전에서 **큐에 남았나 떠났나**가 보여야 한다."""
    from pathlib import Path
    cron = Path("src/pricing/cron.py").read_text(encoding="utf-8")
    assert "반려감시 상태(%s): 큐 잔류 %s · 졸업 %s" in cron
    rw = Path("src/pipeline/reject_watch.py").read_text(encoding="utf-8")
    for key in ('"wrote": wrote', '"stayed":', '"graduated":'):
        assert key in rw, key


def test_scan_and_write_use_the_same_judgment():
    """dry-run이 센 것과 실행이 쓰는 게 같은 함수여야 예고가 거짓이 안 된다."""
    rw = __import__("pathlib").Path("src/pipeline/reject_watch.py").read_text(encoding="utf-8")
    assert rw.count("_next_status(") >= 3          # 정의 + dry-run 집계 + 실행 기록
