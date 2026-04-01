"""src/payments/models.py — 결제/정산 데이터 모델."""

from dataclasses import dataclass, field


@dataclass
class Payment:
    """결제 정보 모델."""
    payment_id: str
    order_id: str
    amount: float
    status: str
    method: str
    pg_name: str
    created_at: str
    currency: str = 'KRW'
    confirmed_at: str = ''
    cancelled_at: str = ''


@dataclass
class Settlement:
    """정산 정보 모델."""
    order_id: str
    sale_price: float
    cost_price: float
    platform_fee: float
    shipping_fee: float
    fx_diff: float = 0.0
    net_profit: float = 0.0
    settled: bool = False

    def calculate(self) -> None:
        """net_profit = sale_price - cost_price - platform_fee - shipping_fee - fx_diff."""
        self.net_profit = self.sale_price - self.cost_price - self.platform_fee - self.shipping_fee - self.fx_diff
