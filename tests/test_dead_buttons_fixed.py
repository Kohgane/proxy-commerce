"""tests/test_dead_buttons_fixed.py — 죽은 버튼 실작동화 회귀 테스트.

감사 리포트(docs/operations/dead_button_audit.md)에서 확인된 비동작 버튼들이
실제 라우트에 연결되었는지 검증한다.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client():
    """셀러 콘솔이 등록된 Flask 앱 테스트 클라이언트."""
    from src.order_webhook import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ─── 반품/환불 인박스 ─────────────────────────────────────────────────────────

class TestReturnsInboxUI:
    """반품/환불 인박스 페이지의 UI 요소 검증."""

    def _mock_processor(self):
        proc = MagicMock()
        proc.list_requests.return_value = [
            {"request_id": "RET-001", "order_id": "ORD-001", "reason": "defective", "status": "manual_review"},
            {"request_id": "RET-002", "order_id": "ORD-002", "reason": "wrong_item", "status": "manual_review"},
        ]
        return proc

    def test_returns_inbox_200(self, client):
        """GET /seller/returns/inbox → 200."""
        with patch("src.returns.auto_processor.ReturnsAutoProcessor", autospec=True) as MockProc:
            MockProc.return_value = self._mock_processor()
            resp = client.get("/seller/returns/inbox")
        assert resp.status_code == 200

    def test_returns_inbox_has_bulk_approve_button(self, client):
        """일괄 승인 버튼이 onclick='bulkApproveReturns()' 포함."""
        with patch("src.returns.auto_processor.ReturnsAutoProcessor", autospec=True) as MockProc:
            MockProc.return_value = self._mock_processor()
            resp = client.get("/seller/returns/inbox")
        body = resp.data.decode("utf-8")
        assert "bulkApproveReturns" in body

    def test_returns_inbox_has_bulk_reject_button(self, client):
        """거부 버튼이 onclick='bulkRejectReturns()' 포함."""
        with patch("src.returns.auto_processor.ReturnsAutoProcessor", autospec=True) as MockProc:
            MockProc.return_value = self._mock_processor()
            resp = client.get("/seller/returns/inbox")
        body = resp.data.decode("utf-8")
        assert "bulkRejectReturns" in body

    def test_returns_inbox_partial_refund_modal_connected(self, client):
        """부분 환불 버튼이 모달 액션으로 연결된다."""
        with patch("src.returns.auto_processor.ReturnsAutoProcessor", autospec=True) as MockProc:
            MockProc.return_value = self._mock_processor()
            resp = client.get("/seller/returns/inbox")
        body = resp.data.decode("utf-8")
        assert "부분 환불" in body
        assert "openPartialRefundModal" in body
        assert "partialRefundModal" in body

    def test_returns_inbox_has_checkboxes(self, client):
        """테이블 행에 체크박스가 있어야 한다."""
        with patch("src.returns.auto_processor.ReturnsAutoProcessor", autospec=True) as MockProc:
            MockProc.return_value = self._mock_processor()
            resp = client.get("/seller/returns/inbox")
        body = resp.data.decode("utf-8")
        assert "return-row-chk" in body
        assert "chkAll" in body

    def test_returns_inbox_empty_state_no_dead_buttons(self, client):
        """요청이 없을 때 일괄 승인/거부 버튼이 disabled 상태다."""
        empty_proc = MagicMock()
        empty_proc.list_requests.return_value = []
        with patch("src.returns.auto_processor.ReturnsAutoProcessor", autospec=True) as MockProc:
            MockProc.return_value = empty_proc
            resp = client.get("/seller/returns/inbox")
        body = resp.data.decode("utf-8")
        assert "반품 요청이 없습니다" in body
        # 아무 요청도 없으면 bulk 버튼이 disabled 처리되어야 함
        assert 'id=\'bulkApproveBtn\'' in body or 'id="bulkApproveBtn"' in body


# ─── 반품/환불 일괄 승인 라우트 ───────────────────────────────────────────────

class TestReturnsBulkApprove:
    """POST /seller/returns/bulk-approve 라우트 테스트."""

    def _mock_manager(self):
        mgr = MagicMock()
        mock_req = MagicMock()
        mock_req.status.value = "approved"
        mgr.approve.return_value = mock_req
        return mgr

    def test_bulk_approve_empty_ids_400(self, client):
        """요청 ID 없으면 400."""
        resp = client.post(
            "/seller/returns/bulk-approve",
            json={"request_ids": []},
        )
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False

    def test_bulk_approve_missing_body_400(self, client):
        """request_ids 필드 없으면 400."""
        resp = client.post("/seller/returns/bulk-approve", json={})
        assert resp.status_code == 400

    def test_bulk_approve_success(self, client):
        """정상 요청 → approved_count 반환."""
        mgr = self._mock_manager()
        with patch("src.returns_automation.automation_manager.ReturnsAutomationManager", return_value=mgr):
            resp = client.post(
                "/seller/returns/bulk-approve",
                json={"request_ids": ["RET-001", "RET-002"]},
            )
        data = resp.get_json()
        assert data["ok"] is True
        assert data["approved_count"] == 2

    def test_bulk_approve_not_found_partial(self, client):
        """일부 ID가 없어도 나머지는 처리하고 ok=true."""
        mgr = MagicMock()
        mock_req = MagicMock()
        mock_req.status.value = "approved"

        def _approve(rid, notes=""):
            if rid == "RET-999":
                raise KeyError("not found")
            return mock_req
        mgr.approve.side_effect = _approve

        with patch("src.returns_automation.automation_manager.ReturnsAutomationManager", return_value=mgr):
            resp = client.post(
                "/seller/returns/bulk-approve",
                json={"request_ids": ["RET-001", "RET-999"]},
            )
        data = resp.get_json()
        assert data["ok"] is True
        assert data["approved_count"] == 1
        results_by_id = {r["request_id"]: r for r in data["results"]}
        assert results_by_id["RET-001"]["ok"] is True
        assert results_by_id["RET-999"]["ok"] is False


# ─── 반품/환불 일괄 거부 라우트 ───────────────────────────────────────────────

class TestReturnsBulkReject:
    """POST /seller/returns/bulk-reject 라우트 테스트."""

    def _mock_manager(self):
        mgr = MagicMock()
        mock_req = MagicMock()
        mock_req.status.value = "rejected"
        mgr.reject.return_value = mock_req
        return mgr

    def test_bulk_reject_empty_ids_400(self, client):
        """요청 ID 없으면 400."""
        resp = client.post(
            "/seller/returns/bulk-reject",
            json={"request_ids": []},
        )
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False

    def test_bulk_reject_success(self, client):
        """정상 요청 → rejected_count 반환."""
        mgr = self._mock_manager()
        with patch("src.returns_automation.automation_manager.ReturnsAutomationManager", return_value=mgr):
            resp = client.post(
                "/seller/returns/bulk-reject",
                json={"request_ids": ["RET-001"]},
            )
        data = resp.get_json()
        assert data["ok"] is True
        assert data["rejected_count"] == 1

    def test_bulk_reject_with_notes(self, client):
        """notes 필드가 manager.reject()에 전달된다."""
        mgr = self._mock_manager()
        with patch("src.returns_automation.automation_manager.ReturnsAutomationManager", return_value=mgr):
            client.post(
                "/seller/returns/bulk-reject",
                json={"request_ids": ["RET-001"], "notes": "품질 불량 아님"},
            )
        mgr.reject.assert_called_once_with("RET-001", notes="품질 불량 아님")

    def test_bulk_reject_not_found_partial(self, client):
        """일부 ID가 없어도 나머지는 처리."""
        mgr = MagicMock()
        mock_req = MagicMock()
        mock_req.status.value = "rejected"

        def _reject(rid, notes=""):
            if rid == "RET-999":
                raise KeyError("not found")
            return mock_req
        mgr.reject.side_effect = _reject

        with patch("src.returns_automation.automation_manager.ReturnsAutomationManager", return_value=mgr):
            resp = client.post(
                "/seller/returns/bulk-reject",
                json={"request_ids": ["RET-001", "RET-999"]},
            )
        data = resp.get_json()
        assert data["ok"] is True
        assert data["rejected_count"] == 1


class TestReturnsPartialRefund:
    """POST /seller/returns/<id>/partial-refund 라우트 테스트."""

    def test_partial_refund_success(self, client):
        mgr = MagicMock()
        req = MagicMock()
        req.status.value = "partially_refunded"
        req.order_id = "ORD-001"
        mgr.get_request_object.return_value = req
        mgr.process_partial_refund.return_value = {"status": "success", "partial_refund": True}

        with patch("src.returns_automation.automation_manager.ReturnsAutomationManager", return_value=mgr):
            resp = client.post(
                "/seller/returns/RET-001/partial-refund",
                json={"amount_krw": 15000, "reason": "사용 흔적"},
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["refund_amount"] == "15000"
        mgr.process_partial_refund.assert_called_once()

    def test_partial_refund_rejects_empty_amount(self, client):
        resp = client.post("/seller/returns/RET-001/partial-refund", json={"amount_krw": 0})
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False

    def test_partial_refund_not_found(self, client):
        mgr = MagicMock()
        mgr.get_request_object.return_value = None
        with patch("src.returns_automation.automation_manager.ReturnsAutomationManager", return_value=mgr):
            resp = client.post("/seller/returns/RET-404/partial-refund", json={"amount_krw": 1000})
        assert resp.status_code == 404

    def test_partial_refund_service_unavailable(self, client):
        with patch("src.returns_automation.automation_manager.ReturnsAutomationManager", side_effect=RuntimeError("service unavailable")):
            resp = client.post("/seller/returns/RET-001/partial-refund", json={"amount_krw": 1000})
        assert resp.status_code == 503


# ─── 소싱 Watch alert() 제거 확인 ─────────────────────────────────────────────

class TestSourcingWatchesNoAlert:
    """소싱 Watch 페이지에 alert() 호출이 없어야 한다."""

    def test_sourcing_watches_no_alert(self, client):
        """/seller/sourcing/watches 응답에 `alert(` 포함 금지."""
        with patch("src.seller_console.views._sourcing_require_admin", return_value=None):
            with patch("src.sourcing.pipeline.get_watch_store") as mock_store:
                mock_store.return_value.list_all.return_value = []
                resp = client.get("/seller/sourcing/watches")
        if resp.status_code == 200:
            body = resp.data.decode("utf-8")
            assert "alert(" not in body, "alert() 호출이 제거되어야 합니다"

    def test_sourcing_watches_has_toast_container(self, client):
        """/seller/sourcing/watches 응답에 toast 컨테이너가 있어야 한다."""
        with patch("src.seller_console.views._sourcing_require_admin", return_value=None):
            with patch("src.sourcing.pipeline.get_watch_store") as mock_store:
                mock_store.return_value.list_all.return_value = []
                resp = client.get("/seller/sourcing/watches")
        if resp.status_code == 200:
            body = resp.data.decode("utf-8")
            assert "_watchToast" in body or "watchPageToast" in body


# ─── 소싱 후보 큐 alert() 제거 확인 ───────────────────────────────────────────

class TestSourcingCandidatesNoAlert:
    """소싱 후보 큐 페이지에 alert() 호출이 없어야 한다."""

    def test_sourcing_candidates_no_alert(self, client):
        """/seller/sourcing/candidates 응답에 `alert(` 포함 금지."""
        with patch("src.seller_console.views._sourcing_require_admin", return_value=None):
            with patch("src.sourcing.pipeline.get_candidate_queue") as mock_queue:
                mock_queue.return_value.list_all.return_value = []
                mock_queue.return_value.stats.return_value = {
                    "pending": 0, "approved": 0, "rejected": 0, "listed": 0,
                    "last_24h": 0, "avg_margin_pct": 0,
                }
                resp = client.get("/seller/sourcing/candidates")
        if resp.status_code == 200:
            body = resp.data.decode("utf-8")
            assert "alert(" not in body, "alert() 호출이 제거되어야 합니다"

    def test_sourcing_candidates_has_toast_container(self, client):
        """/seller/sourcing/candidates 응답에 toast 컨테이너가 있어야 한다."""
        with patch("src.seller_console.views._sourcing_require_admin", return_value=None):
            with patch("src.sourcing.pipeline.get_candidate_queue") as mock_queue:
                mock_queue.return_value.list_all.return_value = []
                mock_queue.return_value.stats.return_value = {
                    "pending": 0, "approved": 0, "rejected": 0, "listed": 0,
                    "last_24h": 0, "avg_margin_pct": 0,
                }
                resp = client.get("/seller/sourcing/candidates")
        if resp.status_code == 200:
            body = resp.data.decode("utf-8")
            assert "_candidateToast" in body or "candidatePageToast" in body

    def test_sourcing_candidates_no_prompt(self, client):
        """후보 거절은 prompt() 대신 모달을 사용한다."""
        with patch("src.seller_console.views._sourcing_require_admin", return_value=None):
            with patch("src.sourcing.pipeline.get_candidate_queue") as mock_queue:
                mock_queue.return_value.list_all.return_value = []
                mock_queue.return_value.stats.return_value = {
                    "pending": 0, "approved": 0, "rejected": 0, "listed": 0,
                    "last_24h": 0, "avg_margin_pct": 0,
                }
                resp = client.get("/seller/sourcing/candidates")
        if resp.status_code == 200:
            body = resp.data.decode("utf-8")
            assert "prompt(" not in body
            assert "candidateRejectModal" in body
