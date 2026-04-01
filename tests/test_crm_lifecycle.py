"""tests/test_crm_lifecycle.py — 라이프사이클 자동화 테스트."""
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _customer(email="a@a.com", name="고객", days_ago=10, total_orders=1):
    dt = (datetime.now(tz=timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        "email": email,
        "name": name,
        "total_orders": total_orders,
        "total_spent_krw": 100000,
        "last_order_date": dt,
        "first_order_date": dt,
        "segment": "NEW",
    }


class TestCustomerLifecycle:
    def _make_lc(self, enabled=True):
        with patch.dict(os.environ, {"CRM_LIFECYCLE_ENABLED": "1" if enabled else "0"}):
            from src.crm.lifecycle import CustomerLifecycle
            return CustomerLifecycle()

    def test_is_enabled(self):
        """환경변수 활성화 시 is_enabled()가 True여야 한다."""
        with patch.dict(os.environ, {"CRM_LIFECYCLE_ENABLED": "1"}):
            from src.crm.lifecycle import CustomerLifecycle
            lc = CustomerLifecycle()
            assert lc.is_enabled() is True

    def test_is_disabled_by_default(self):
        """기본값은 비활성화여야 한다."""
        with patch.dict(os.environ, {"CRM_LIFECYCLE_ENABLED": "0"}):
            from src.crm.lifecycle import CustomerLifecycle
            lc = CustomerLifecycle()
            assert lc.is_enabled() is False

    def test_send_welcome_disabled_returns_false(self):
        """비활성화 시 send_welcome이 False를 반환해야 한다."""
        lc = self._make_lc(enabled=False)
        result = lc.send_welcome({"email": "a@a.com"})
        assert result is False

    def test_send_welcome_enabled_sends_notification(self):
        """활성화 시 send_welcome이 알림을 발송해야 한다."""
        with patch.dict(os.environ, {"CRM_LIFECYCLE_ENABLED": "1"}):
            from src.crm.lifecycle import CustomerLifecycle
            lc = CustomerLifecycle()
            with patch.object(lc, '_send_notification', return_value=True) as mock_notify:
                result = lc.send_welcome({"email": "a@a.com", "name": "테스터"})
            mock_notify.assert_called_once()
            assert result is True

    def test_repurchase_nudge_disabled_returns_empty(self):
        """비활성화 시 send_repurchase_nudge가 빈 리스트를 반환해야 한다."""
        lc = self._make_lc(enabled=False)
        result = lc.send_repurchase_nudge(customers=[_customer()])
        assert result == []

    def test_repurchase_nudge_sends_for_old_customers(self):
        """마지막 주문이 N일+ 경과한 고객에게 알림을 발송해야 한다."""
        with patch.dict(os.environ, {"CRM_LIFECYCLE_ENABLED": "1"}):
            from src.crm.lifecycle import CustomerLifecycle
            lc = CustomerLifecycle()
            customers = [_customer("old@a.com", days_ago=40)]
            with patch.object(lc, '_send_notification', return_value=True):
                result = lc.send_repurchase_nudge(customers=customers, days=30)
            assert "old@a.com" in result

    def test_repurchase_nudge_skips_recent_customers(self):
        """최근 구매 고객은 재구매 유도 대상에서 제외되어야 한다."""
        with patch.dict(os.environ, {"CRM_LIFECYCLE_ENABLED": "1"}):
            from src.crm.lifecycle import CustomerLifecycle
            lc = CustomerLifecycle()
            customers = [_customer("new@a.com", days_ago=5)]
            with patch.object(lc, '_send_notification', return_value=True):
                result = lc.send_repurchase_nudge(customers=customers, days=30)
            assert result == []

    def test_vip_benefit_disabled_returns_empty(self):
        """비활성화 시 send_vip_benefit이 빈 리스트를 반환해야 한다."""
        lc = self._make_lc(enabled=False)
        result = lc.send_vip_benefit(customers=[_customer()])
        assert result == []

    def test_vip_benefit_notifies_customers(self):
        """VIP 고객에게 혜택 알림을 발송해야 한다."""
        with patch.dict(os.environ, {"CRM_LIFECYCLE_ENABLED": "1"}):
            from src.crm.lifecycle import CustomerLifecycle
            lc = CustomerLifecycle()
            customers = [_customer("vip@a.com")]
            with patch.object(lc, '_send_notification', return_value=True):
                result = lc.send_vip_benefit(customers=customers)
            assert "vip@a.com" in result

    def test_at_risk_alert_disabled_returns_empty(self):
        """비활성화 시 send_at_risk_alert가 빈 리스트를 반환해야 한다."""
        lc = self._make_lc(enabled=False)
        result = lc.send_at_risk_alert(customers=[_customer()])
        assert result == []

    def test_run_all_disabled_returns_early(self):
        """비활성화 시 run_all이 enabled=False를 반환해야 한다."""
        lc = self._make_lc(enabled=False)
        result = lc.run_all()
        assert result.get("enabled") is False

    def test_run_all_returns_counts(self):
        """활성화 시 run_all이 count 정보를 포함해야 한다."""
        with patch.dict(os.environ, {"CRM_LIFECYCLE_ENABLED": "1"}):
            from src.crm.lifecycle import CustomerLifecycle
            lc = CustomerLifecycle()
            with patch.object(lc, 'send_repurchase_nudge', return_value=[]):
                with patch.object(lc, 'send_vip_benefit', return_value=[]):
                    with patch.object(lc, 'send_at_risk_alert', return_value=[]):
                        result = lc.run_all()
            assert "repurchase_nudge_count" in result
            assert "vip_benefit_count" in result
            assert "at_risk_alert_count" in result
