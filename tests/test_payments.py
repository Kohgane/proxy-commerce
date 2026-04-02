"""tests/test_payments.py — Phase 22 결제 시스템 테스트."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.payments.pg_client import PGClient  # noqa: E402
from src.payments.toss_client import TossPaymentsClient  # noqa: E402
from src.payments.fee_calculator import FeeCalculator  # noqa: E402
from src.payments.models import Payment, Settlement  # noqa: E402

# ──────────────────────────────────────────────────────────
# TestPGClientAbstract
# ──────────────────────────────────────────────────────────


class TestPGClientAbstract:
    def test_cannot_instantiate(self):
        """PGClient는 추상 클래스이므로 직접 인스턴스화할 수 없다."""
        with pytest.raises(TypeError):
            PGClient()  # type: ignore[abstract]

    def test_has_abstract_methods(self):
        assert hasattr(PGClient, 'request_payment')
        assert hasattr(PGClient, 'confirm_payment')
        assert hasattr(PGClient, 'cancel_payment')


# ──────────────────────────────────────────────────────────
# TestTossPaymentsClient
# ──────────────────────────────────────────────────────────


class TestTossPaymentsClient:
    def _make_client(self, key: str = 'test_secret_key') -> TossPaymentsClient:
        with patch.dict(os.environ, {'TOSS_PAYMENTS_SECRET_KEY': key}):
            return TossPaymentsClient()

    def test_init_reads_env(self):
        client = self._make_client('my_secret')
        assert client._secret_key == 'my_secret'

    def test_init_missing_key_warns(self, caplog):
        import logging
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('TOSS_PAYMENTS_SECRET_KEY', None)
            with caplog.at_level(logging.WARNING, logger='src.payments.toss_client'):
                TossPaymentsClient()
        assert any('TOSS_PAYMENTS_SECRET_KEY' in r.message for r in caplog.records)

    def test_request_payment(self):
        client = self._make_client()
        result = client.request_payment('order-001', 50000.0, order_name='테스트 상품')
        assert result['order_id'] == 'order-001'
        assert result['amount'] == 50000.0
        assert 'payment_key' in result
        assert 'checkout_url' in result

    def test_confirm_payment_calls_post(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'status': 'DONE', 'paymentKey': 'pk_001'}
        mock_resp.raise_for_status = MagicMock()

        with patch('src.payments.toss_client.requests.post', return_value=mock_resp) as mock_post:
            result = client.confirm_payment('pk_001', 'order-001', 50000.0)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert 'payments/confirm' in call_kwargs[0][0]
        assert result['status'] == 'DONE'

    def test_cancel_payment_calls_post(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'status': 'CANCELED'}
        mock_resp.raise_for_status = MagicMock()

        with patch('src.payments.toss_client.requests.post', return_value=mock_resp) as mock_post:
            result = client.cancel_payment('pk_001', '고객 요청')

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert 'pk_001/cancel' in call_kwargs[0][0]
        assert result['status'] == 'CANCELED'

    def test_confirm_payment_raises_on_error(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 400")

        with patch('src.payments.toss_client.requests.post', return_value=mock_resp):
            with pytest.raises(Exception, match="HTTP 400"):
                client.confirm_payment('pk_bad', 'order-bad', 0.0)


# ──────────────────────────────────────────────────────────
# TestFeeCalculator
# ──────────────────────────────────────────────────────────


class TestFeeCalculator:
    def setup_method(self):
        self.calc = FeeCalculator()

    def test_coupang_fee(self):
        fee = self.calc.calculate_fee('COUPANG', 100000.0)
        assert abs(fee - 10800.0) < 0.01

    def test_naver_fee(self):
        fee = self.calc.calculate_fee('NAVER', 100000.0)
        assert abs(fee - 5500.0) < 0.01

    def test_shopify_fee(self):
        fee = self.calc.calculate_fee('SHOPIFY', 100000.0)
        assert abs(fee - 2000.0) < 0.01

    def test_woo_fee_is_zero(self):
        fee = self.calc.calculate_fee('WOO', 100000.0)
        assert fee == 0.0

    def test_unknown_platform_returns_zero(self):
        fee = self.calc.calculate_fee('UNKNOWN_PLATFORM', 100000.0)
        assert fee == 0.0

    def test_get_fee_rate_coupang(self):
        assert self.calc.get_fee_rate('COUPANG') == 0.108

    def test_get_fee_rate_case_insensitive(self):
        assert self.calc.get_fee_rate('coupang') == 0.108
        assert self.calc.get_fee_rate('Naver') == 0.055

    def test_list_platforms(self):
        platforms = self.calc.list_platforms()
        assert isinstance(platforms, list)
        assert 'COUPANG' in platforms
        assert 'NAVER' in platforms
        assert 'SHOPIFY' in platforms
        assert 'WOO' in platforms


# ──────────────────────────────────────────────────────────
# TestPaymentsModel
# ──────────────────────────────────────────────────────────


class TestPaymentsModel:
    def test_payment_dataclass_fields(self):
        p = Payment(
            payment_id='pay-001',
            order_id='ord-001',
            amount=50000.0,
            status='DONE',
            method='카드',
            pg_name='toss',
            created_at='2024-01-01T00:00:00',
        )
        assert p.payment_id == 'pay-001'
        assert p.currency == 'KRW'  # 기본값
        assert p.confirmed_at == ''
        assert p.cancelled_at == ''

    def test_payment_custom_currency(self):
        p = Payment(
            payment_id='pay-002',
            order_id='ord-002',
            amount=100.0,
            currency='USD',
            status='DONE',
            method='card',
            pg_name='stripe',
            created_at='2024-01-01T00:00:00',
        )
        assert p.currency == 'USD'

    def test_settlement_calculate(self):
        s = Settlement(
            order_id='ord-001',
            sale_price=100000.0,
            cost_price=60000.0,
            platform_fee=10800.0,
            shipping_fee=3000.0,
            fx_diff=500.0,
        )
        s.calculate()
        expected = 100000.0 - 60000.0 - 10800.0 - 3000.0 - 500.0
        assert abs(s.net_profit - expected) < 0.01

    def test_settlement_defaults(self):
        s = Settlement(
            order_id='ord-002',
            sale_price=50000.0,
            cost_price=30000.0,
            platform_fee=5000.0,
            shipping_fee=2500.0,
        )
        assert s.fx_diff == 0.0
        assert s.net_profit == 0.0
        assert s.settled is False
        s.calculate()
        assert abs(s.net_profit - 12500.0) < 0.01


# ──────────────────────────────────────────────────────────
# TestPaymentsAPIBlueprint
# ──────────────────────────────────────────────────────────


class TestPaymentsAPIBlueprint:
    def setup_method(self):
        from src.order_webhook import app
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_status_endpoint(self):
        resp = self.client.get('/api/v1/payments/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'ok'
        assert data['module'] == 'payments'

    def test_fee_rates_endpoint(self):
        resp = self.client.get('/api/v1/payments/fee-rates')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'fee_rates' in data
        rates = data['fee_rates']
        assert isinstance(rates, dict)
        assert 'COUPANG' in rates
        assert rates['COUPANG'] == pytest.approx(0.108)

    def test_calculate_settlement_endpoint(self):
        order = {
            'order_id': 'test-001',
            'sale_price': 100000.0,
            'cost_price': 60000.0,
            'platform': 'NAVER',
            'shipping_fee': 3000.0,
        }
        resp = self.client.post('/api/v1/payments/calculate-settlement', json={'order': order})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['order_id'] == 'test-001'
        assert 'net_profit' in data
        assert data['platform_fee'] == pytest.approx(5500.0)

    def test_calculate_settlement_missing_order(self):
        resp = self.client.post('/api/v1/payments/calculate-settlement', json={})
        assert resp.status_code == 400

    def test_calculate_settlement_missing_field(self):
        resp = self.client.post('/api/v1/payments/calculate-settlement', json={'order': {'order_id': 'x'}})
        assert resp.status_code == 400
