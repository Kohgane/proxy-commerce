"""tests/test_r2_rearm.py — R2 재무장: 처방을 실행하면 감시가 다시 걸린다.

부검(2026-09-05): 처방 실행이 대장 status를 안 건드려 **감시 사슬이 끊겼다.**
승인요청은 `{success:true}`만 돌려주고 대장은 옛 상태 그대로다. 이미 큐를 떠난 행에
처방을 걸면 다시 요청해 놓고도 아무도 결과를 안 본다 — **실행할수록 블랙박스**가 되는 구조.

원리: **다시 요청했다 = 결과가 다시 미확정이다.**
"""
from __future__ import annotations

import re
from pathlib import Path

from src.pipeline import reject_watch as RW

ADMIN = Path("src/dashboard/admin_views.py")
TPL = Path("src/seller_console/templates/reject_watch.html")


def _row(kind="saved_pending", sid="16369251981", **kw):
    return {"sid": sid, "kind": kind, "comment": "임시저장", **kw}


# ── 계약: 성공시에만 재무장, 실패시 불변 ──────────────────────────────────────
def test_rearms_on_successful_approval():
    """승인요청이 성공하면 대장을 `submitted`로 되돌린다."""
    seen = []
    out = RW.apply_prescription(
        _row(), approved=True,
        approve_fn=lambda sid: {"success": True, "product_id": sid},
        rearm_fn=lambda sid: seen.append(sid) or True)
    assert out["applied"] is True
    assert out["rearmed"] is True
    assert seen == ["16369251981"], "재무장이 실행된 sid로 정확히 1회 불려야 한다"


def test_does_not_rearm_on_failure():
    """★ 실패는 상태를 건드리지 않는다 — 실패를 '다시 심사 중'으로 만들면 그게 가짜 수치다."""
    seen = []
    out = RW.apply_prescription(
        _row(), approved=True,
        approve_fn=lambda sid: {"success": False, "error": "411"},
        rearm_fn=lambda sid: seen.append(sid) or True)
    assert out["applied"] is False
    assert "rearmed" not in out
    assert seen == [], "실패했는데 재무장이 불렸다 — 감시 상태가 거짓이 된다"


def test_does_not_rearm_when_held_by_gate():
    """승인 게이트에 막힌 건(실행 0)은 재무장도 0이다."""
    seen = []
    out = RW.apply_prescription(_row(), approved=False,
                                approve_fn=lambda sid: {"success": True},
                                rearm_fn=lambda sid: seen.append(sid) or True)
    assert out["applied"] is False and seen == []


def test_does_not_rearm_when_action_not_taken():
    """자동 조치 불가 유형(brand_fix 등)은 마켓을 안 건드리니 재무장도 없다."""
    seen = []
    out = RW.apply_prescription(_row(wing_state="brand_fix"), approved=True,
                                approve_fn=lambda sid: {"success": True},
                                rearm_fn=lambda sid: seen.append(sid) or True)
    assert out["applied"] is False and seen == []


def test_rearm_covers_every_resubmission_path():
    """재제출하는 경로는 **전부** 재무장한다 — 넷 다 밑바닥이 request_approval이다.

    한 경로만 걸면 나머지가 그대로 사슬을 끊는다(이 결함의 원래 모양이 그거였다).
    """
    calls = {}

    def _mk(k):
        return lambda sid, *a: calls.__setitem__(k, sid) or True

    cases = [
        (_row("saved_pending"), {"approve_fn": lambda sid: {"success": True}}),
        (_row("image_spec"), {"resubmit_fn": lambda sid, upd: {"success": True}}),
        (_row("option_value"), {"resubmit_fn": lambda sid, upd: {"success": True}}),
        (_row("apple_category", apple_target="android"), {"reissue_fn": lambda sid: {"success": True}}),
        (_row("image_spec"), {"reupload_fn": lambda sid, row: {"success": True}}),
    ]
    for row, handlers in cases:
        seen = []
        out = RW.apply_prescription(row, approved=True, rearm_fn=lambda sid: seen.append(sid) or True,
                                    **handlers)
        assert out["applied"] is True, (row["kind"], handlers, out)
        assert seen == [row["sid"]], f"{row['kind']}/{list(handlers)} 경로가 재무장을 안 한다"
    assert calls == {}


def test_rearm_failure_does_not_mask_applied():
    """재무장이 실패해도 처방 성공은 성공이다 — 다만 조용히 넘기지 않고 사유를 남긴다."""
    def _boom(sid):
        raise RuntimeError("DB 없음")
    out = RW.apply_prescription(_row(), approved=True,
                                approve_fn=lambda sid: {"success": True}, rearm_fn=_boom)
    assert out["applied"] is True
    assert out["rearmed"] is False and "DB 없음" in out["rearm_error"]


def test_rearm_is_optional():
    """rearm_fn 미주입이면 예전과 똑같이 동작한다(하위호환)."""
    out = RW.apply_prescription(_row(), approved=True,
                                approve_fn=lambda sid: {"success": True})
    assert out["applied"] is True and "rearmed" not in out


# ── 배선·소급 라우트 ─────────────────────────────────────────────────────────
def test_apply_route_injects_rearm():
    """실행 라우트가 재무장을 주입한다 — 안 하면 라이브에서만 사슬이 끊긴다."""
    s = ADMIN.read_text(encoding="utf-8")
    apply_fn = s.split('@admin_panel_bp.post("/reject-watch/apply")')[1]
    assert "rearm_fn=lambda sid: _reject_watch_rearm(sid)" in apply_fn


def test_rearm_is_single_source():
    """실행 경로와 소급 라우트가 **같은 함수**를 쓴다 — 이중 구현이 이 프로젝트의 단골 결함이다."""
    s = ADMIN.read_text(encoding="utf-8")
    assert s.count("def _reject_watch_rearm") == 1
    assert s.count("_reject_watch_rearm") == 3       # 정의 1 + 실행 주입 1 + 소급 라우트 1
    body = s.split("def _reject_watch_rearm")[1].split("\n@")[0]
    assert 'status="submitted"' in body
    # 분류·사유·처방은 건드리지 않는다(mark_checked가 빈 값 컬럼을 건너뛴다).
    assert "reject_kind" not in body and "reject_comment" not in body


def test_rearm_route_makes_no_market_call():
    """소급 재무장은 마켓 호출 0 — 그래서 비가역 게이트를 걸지 않는다.

    ※ 주석·독스트링은 걷어내고 본다. 왜 안 거는지를 적어 둔 문장이 잔재로 잡히면
      설명을 지워야 통과하는 계약이 된다(같은 오탐을 이 세션에서 세 번째로 만난다).
    """
    s = ADMIN.read_text(encoding="utf-8")
    route = s.split('@admin_panel_bp.post("/reject-watch/rearm")')[1].split("\n@")[0]
    route = re.sub(r'"""!?.*?"""', "", route, flags=re.S)          # 독스트링 제거
    route = re.sub(r"#.*", "", route)                               # 줄 주석 제거
    for banned in ("request_approval", "delete_product", "_reject_watch_uploader",
                   "REJECT_WATCH_APPROVED"):
        assert banned not in route, f"재무장 라우트가 {banned}를 부른다"
    assert "50" in route                              # 한 번에 50건 상한


def test_rearm_route_is_honest_about_missing_rows():
    """대장에 없는 번호를 '재무장됨'이라 말하지 않는다(가짜 성공 0)."""
    route = ADMIN.read_text(encoding="utf-8").split(
        '@admin_panel_bp.post("/reject-watch/rearm")')[1].split("\n@")[0]
    assert "등록 대장에 없는 상품번호입니다" in route
    assert '"rearmed": ok' in route


def test_rearm_button_confirms_and_posts():
    """버튼은 확인 다이얼로그를 거치고, 응답 원문을 그대로 화면에 남긴다."""
    t = TPL.read_text(encoding="utf-8")
    assert 'id="rearmBtn"' in t and 'id="rearmSids"' in t and 'id="rearmResult"' in t
    js = t.split("소급 재무장")[-1]
    assert "pcConfirm(" in js and "/admin/reject-watch/rearm" in js
    assert "'HTTP ' + r.status" in js                 # 요약 금지 — 원문 그대로
    assert "전송 실패" in js                           # 실패도 화면에 남긴다


def test_page_states_no_market_call():
    """화면이 '마켓에 아무것도 안 보낸다'를 사용자 말로 밝힌다(정직 표기)."""
    t = TPL.read_text(encoding="utf-8")
    assert "마켓에 아무것도 보내지 않아요" in t
    assert "심사 중" in t


def test_screen_renders():
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    assert app.test_client().get("/seller/sourcing/reject-watch").status_code == 200


# ── R1 회귀: 큐 이탈을 만든 그 판정 ──────────────────────────────────────────
def test_comment_present_still_leaves_the_queue():
    """★ R1 재구성 고정: comment가 있으면 `rejected`가 되고, `rejected`는 감시 큐 밖이다.

    9/03 크론이 임시저장 건을 이 경로로 앉혔고 그날 큐에서 빠졌다(오늘 scanned 0의 원인).
    이 동작 자체는 옳다 — **재무장이 없던 것**이 결함이었다.
    """
    from src.db.market_registrations_pg import _WATCH_STATUSES
    assert RW._next_status({"comment": "임시저장"}) == "rejected"
    assert "rejected" not in _WATCH_STATUSES
    assert RW._next_status({"comment": ""}) == "unknown"
    assert "unknown" in _WATCH_STATUSES               # 사유 없음은 큐에 남는다


def test_2061_has_no_query_behind_it():
    """★ R3: brand_fix 2,061은 **Wing 계기판 육안 실측치**지 우리 DB 숫자가 아니다.

    코드 어디에도 그 숫자를 만드는 쿼리가 없다 — 출처는 주석 한 줄뿐이다.
    '2시간마다 2천 건 재조회'라는 부하 주장은 여기서 성립한 적이 없다.
    """
    src = Path("src/pipeline/reject_watch.py").read_text(encoding="utf-8")
    line = [x for x in src.splitlines() if "2,061" in x]
    assert line and line[0].lstrip().startswith("#"), "2,061이 주석 밖에 있다"
    assert "오너 실측" in line[0]
    hits = [p for p in Path("src").rglob("*.py")
            if re.search(r"\bbrand_fix\b", p.read_text(encoding="utf-8"))]
    assert hits == [Path("src/pipeline/reject_watch.py")], f"brand_fix 사용처가 늘었다: {hits}"
