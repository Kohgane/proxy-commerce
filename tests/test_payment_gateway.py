"""tests/test_payment_gateway.py — Phase 45: 결제 게이트웨이 테스트."""
import pytest


class TestTossPaymentsGateway:
    def setup_method(self):
        from src.payment_gateway.toss import TossPaymentsGateway
        self.gw = TossPaymentsGateway()

    def test_initiate_payment(self):
        payment = self.gw.initiate_payment(10000, 'KRW', 'ORDER-001')
        assert payment['gateway'] == 'toss'
        assert payment['status'] == 'initiated'
        assert 'payment_id' in payment

    def test_confirm_payment(self):
        payment = self.gw.initiate_payment(10000, 'KRW', 'ORDER-001')
        confirmed = self.gw.confirm_payment(payment['payment_id'])
        assert confirmed['status'] == 'confirmed'

    def test_refund_payment(self):
        payment = self.gw.initiate_payment(10000, 'KRW', 'ORDER-001')
        self.gw.confirm_payment(payment['payment_id'])
        refunded = self.gw.refund_payment(payment['payment_id'])
        assert refunded['status'] == 'refunded'

    def test_partial_refund(self):
        payment = self.gw.initiate_payment(10000, 'KRW', 'ORDER-001')
        refunded = self.gw.refund_payment(payment['payment_id'], amount=5000)
        assert refunded['refund_amount'] == 5000

    def test_get_status(self):
        payment = self.gw.initiate_payment(10000, 'KRW', 'ORDER-001')
        status = self.gw.get_status(payment['payment_id'])
        assert status['status'] == 'initiated'

    def test_confirm_nonexistent(self):
        with pytest.raises(KeyError):
            self.gw.confirm_payment('nonexistent')


class TestStripeGateway:
    def setup_method(self):
        from src.payment_gateway.stripe import StripeGateway
        self.gw = StripeGateway()

    def test_initiate_payment(self):
        payment = self.gw.initiate_payment(100.0, 'USD', 'ORDER-001')
        assert payment['gateway'] == 'stripe'
        assert 'client_secret' in payment

    def test_confirm_payment(self):
        payment = self.gw.initiate_payment(100.0, 'USD', 'ORDER-001')
        confirmed = self.gw.confirm_payment(payment['payment_id'])
        assert confirmed['status'] == 'succeeded'

    def test_refund_creates_refund_id(self):
        payment = self.gw.initiate_payment(100.0, 'USD', 'ORDER-001')
        refunded = self.gw.refund_payment(payment['payment_id'])
        assert 'refund_id' in refunded


class TestPayPalGateway:
    def setup_method(self):
        from src.payment_gateway.paypal import PayPalGateway
        self.gw = PayPalGateway()

    def test_initiate_payment(self):
        payment = self.gw.initiate_payment(50.0, 'USD', 'ORDER-001')
        assert payment['gateway'] == 'paypal'
        assert 'approval_url' in payment

    def test_confirm_payment(self):
        payment = self.gw.initiate_payment(50.0, 'USD', 'ORDER-001')
        confirmed = self.gw.confirm_payment(payment['payment_id'])
        assert confirmed['status'] == 'approved'

    def test_get_status_not_found(self):
        status = self.gw.get_status('nonexistent')
        assert status['status'] == 'not_found'


class TestGatewayManager:
    def setup_method(self):
        from src.payment_gateway.gateway_manager import GatewayManager
        from src.payment_gateway.toss import TossPaymentsGateway
        from src.payment_gateway.stripe import StripeGateway
        from src.payment_gateway.paypal import PayPalGateway
        self.mgr = GatewayManager()
        self.mgr.register('toss', TossPaymentsGateway())
        self.mgr.register('stripe', StripeGateway())
        self.mgr.register('paypal', PayPalGateway())

    def test_route_krw_to_toss(self):
        gw = self.mgr.route('KRW')
        from src.payment_gateway.toss import TossPaymentsGateway
        assert isinstance(gw, TossPaymentsGateway)

    def test_route_usd_to_stripe(self):
        gw = self.mgr.route('USD')
        from src.payment_gateway.stripe import StripeGateway
        assert isinstance(gw, StripeGateway)

    def test_list_gateways(self):
        gws = self.mgr.list_gateways()
        assert 'toss' in gws
        assert 'stripe' in gws
        assert 'paypal' in gws
