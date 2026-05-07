"""tests/test_ai_budget.py — AI 예산 가드 테스트 (Phase 134)."""
import os
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch


class TestBudgetGuard:
    def _make_guard(self, used_usd: float = 0.0, limit: float = 100.0):
        os.environ["AI_MONTHLY_BUDGET_USD"] = str(limit)
        from src.ai.budget import BudgetGuard
        with patch("src.ai.budget.AISpendSheets._get_ws", return_value=None):
            guard = BudgetGuard()
        mock_sheets = MagicMock()
        mock_sheets.month_to_date.return_value = Decimal(str(used_usd))
        guard.sheets = mock_sheets
        return guard

    def test_can_spend_when_under_limit(self):
        guard = self._make_guard(used_usd=50.0, limit=100.0)
        assert guard.can_spend(Decimal("5")) is True

    def test_cannot_spend_when_at_limit(self):
        guard = self._make_guard(used_usd=99.0, limit=100.0)
        assert guard.can_spend(Decimal("5")) is False

    def test_cannot_spend_when_over_limit(self):
        guard = self._make_guard(used_usd=100.5, limit=100.0)
        assert guard.can_spend(Decimal("0")) is False

    def test_cannot_spend_when_exceeds_by_one_cent(self):
        guard = self._make_guard(used_usd=100.0, limit=100.0)
        assert guard.can_spend(Decimal("0.01")) is False

    def test_can_spend_in_dry_run(self, monkeypatch):
        monkeypatch.setenv("ADAPTER_DRY_RUN", "1")
        guard = self._make_guard(used_usd=200.0, limit=100.0)
        assert guard.can_spend(Decimal("100")) is True

    def test_warning_at_80_pct(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        guard = self._make_guard(used_usd=82.0, limit=100.0)
        guard._warned_this_session = False
        # Should pass (not over limit) but trigger warning
        result = guard.can_spend(Decimal("0.1"))
        assert result is True
        assert guard._warned_this_session is True

    def test_no_double_warning(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        guard = self._make_guard(used_usd=82.0, limit=100.0)
        guard._warned_this_session = True  # already warned
        # Should not warn again
        result = guard.can_spend(Decimal("0.1"))
        assert result is True

    def test_summary_structure(self):
        guard = self._make_guard(used_usd=25.0, limit=100.0)
        summary = guard.summary()
        assert "limit_usd" in summary
        assert "used_usd" in summary
        assert "remaining_usd" in summary
        assert "pct" in summary
        assert "status" in summary
        assert summary["pct"] == 25.0
        assert summary["status"] == "ok"

    def test_summary_status_warning(self):
        guard = self._make_guard(used_usd=85.0, limit=100.0)
        summary = guard.summary()
        assert summary["status"] == "warning"

    def test_summary_status_exceeded(self):
        guard = self._make_guard(used_usd=102.0, limit=100.0)
        summary = guard.summary()
        assert summary["status"] == "exceeded"

    def test_record_appends_to_sheets(self):
        guard = self._make_guard()
        guard.sheets.append.reset_mock()
        guard.record(Decimal("0.05"), provider="openai", tokens=200, note="test")
        guard.sheets.append.assert_called_once()
        call_args = guard.sheets.append.call_args[0][0]
        assert float(call_args["cost_usd"]) == pytest.approx(0.05)
        assert call_args["provider"] == "openai"


class TestBudgetExceededError:
    def test_error_has_summary(self):
        from src.ai.budget import BudgetExceededError
        summary = {"limit_usd": 100.0, "used_usd": 105.0, "remaining_usd": -5.0, "pct": 105.0}
        err = BudgetExceededError(summary)
        assert err.summary == summary
        assert "초과" in str(err)
