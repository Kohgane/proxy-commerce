"""tests/test_t1_apply_button.py — T1: 반려 분류표 처방 실행 버튼.

**왜 필요했나(실측 2026-09-04):** 라이브에서 16369251981이 `saved_pending`으로 분류되고
처방 '승인 재요청'까지 떴는데 **화면에 실행 수단이 없었다.** `POST /admin/reject-watch/apply`는
배선돼 있었지만 오너가 그걸 쏠 방법이 브라우저에 없었다 → approvals 로그 0건.

계약: **신규 실행 로직 0**(배선된 라우트를 부르는 버튼만) · 게이트 잠김 시 비활성 ·
한 건씩만(카나리) · 결과는 마켓 원문 그대로.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

TPL = Path("src/seller_console/templates/reject_watch.html").read_text(encoding="utf-8")
CSS = Path("src/static/app.css").read_text(encoding="utf-8")
ADMIN = Path("src/dashboard/admin_views.py").read_text(encoding="utf-8")

_ROW = {"sid": "16369251981", "title": "ALPAKA 크로스백", "comment": "임시저장",
        "kind": "saved_pending", "kind_ko": "임시저장(승인요청 누락)",
        "prescription": "request_approval",
        "prescription_ko": "승인 재요청(PUT approvals) — 재등록 아님"}
_UNKNOWN = {"sid": "9", "comment": "담당자 검토 결과 반려되었습니다.", "kind": "unknown",
            "kind_ko": "미분류", "prescription": "manual", "prescription_ko": "오너 확인 필요"}


def _render(approved, rows=None):
    import os
    os.environ.setdefault("SELLER_CONSOLE_AUTH", "0")
    from flask import render_template

    from src.order_webhook import app
    from src.pipeline import reject_watch as RW
    rows = rows if rows is not None else [_ROW]
    by_kind = {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    app.jinja_env.cache.clear()
    with app.test_request_context("/seller/sourcing/reject-watch"):
        return render_template("reject_watch.html", page="sourcing", account="gogane",
                               scan={"alert": "1건", "rows": rows, "by_kind": by_kind,
                                     "scanned": len(rows)},
                               sids_text="", approved=approved, kinds=RW.REJECTION_KINDS,
                               watch={"connected": True, "note": "", "rows": []})


def _apply_buttons(html):
    return re.findall(r'<button[^>]*class="[^"]*\brw-apply\b[^"]*"[^>]*>', html)


def test_gate_off_renders_no_executable_button():
    """★ 게이트가 잠겨 있으면 **누를 수 있는 버튼이 없다** — 비가역 방어."""
    html = _render(approved=False)
    assert _apply_buttons(html) == []
    assert "게이트 잠김" in html
    locked = re.search(r'<button[^>]*disabled[^>]*>\s*<i[^>]*></i>\s*게이트 잠김', html)
    assert locked, "잠김 버튼이 disabled가 아니다"


def test_gate_on_renders_one_button_per_actionable_row():
    """게이트가 열리면 **행마다 한 개**. 미분류는 실행 대상이 아니다(오너 확인)."""
    html = _render(approved=True, rows=[_ROW, _UNKNOWN])
    assert len(_apply_buttons(html)) == 1               # 미분류 제외
    assert "게이트 잠김" not in html


def test_no_bulk_execute():
    """★ 전체 일괄 실행 없음 — 카나리 원칙. 버튼은 항상 rows 하나만 싣는다."""
    html = _render(approved=True, rows=[_ROW, dict(_ROW, sid="2")])
    assert "rows: [row]" in html                        # 배열에 한 건만
    for word in ("전체 실행", "일괄 실행", "모두 실행"):
        assert word not in html


def test_calls_the_wired_route_not_a_new_one():
    """★ 신규 실행 로직 0 — 이미 배선된 라우트를 부른다."""
    html = _render(approved=True)
    assert "'/admin/reject-watch/apply'" in html
    assert '@admin_panel_bp.post("/reject-watch/apply")' in ADMIN
    # 템플릿이 업로더를 직접 부르지 않는다(실행 로직 재구현 금지).
    for forbidden in ("request_approval(", "upload_product(", "delete_product("):
        assert forbidden not in html


def test_confirm_names_sid_and_prescription_and_irreversibility():
    """확인 다이얼로그가 **무엇을·무엇에** 하는지 말한다. 네이티브 confirm 아님(pcConfirm 관례)."""
    html = _render(approved=True)
    assert "pcConfirm(" in html and "window.confirm" not in html
    assert "'상품번호 ' + sid" in html
    assert "btn.dataset.rxKo" in html
    assert "되돌릴 수 없습니다" in html


def test_result_shows_raw_market_response():
    """★ 결과는 **원문 그대로** — HTTP status + body. 요약하면 다음 부검에서 원문을 다시 찾는다."""
    html = _render(approved=True)
    assert "'HTTP ' + status" in html
    assert "r.text()" in html                            # json 파싱으로 원문을 버리지 않는다
    assert ".rw-result" in CSS and "white-space: pre-wrap" in CSS.split(".rw-result")[1][:200]


def test_transport_failure_is_shown_not_swallowed():
    """못 보낸 것도 화면에 남긴다(조용한 실패 금지)."""
    html = _render(approved=True)
    assert "'전송 실패'" in html and ".catch(" in html


@pytest.mark.parametrize("approved", [True, False])
def test_screen_still_renders(approved):
    assert "반려 분류표" in _render(approved)
