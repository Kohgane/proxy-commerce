"""src/mobile_api/mobile_order.py — 모바일 주문/장바구니 서비스."""
from __future__ import annotations

import base64
import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CartItem:
    item_id: str
    user_id: str
    sku: str
    quantity: int
    price: float
    added_at: float = field(default_factory=time.time)


class MobileOrderService:
    """모바일 주문/장바구니 서비스."""

    ORDER_STATUSES = ['pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled']

    def __init__(self):
        self._carts: dict[str, list[CartItem]] = {}
        self._orders: dict[str, dict] = {}

    def get_cart(self, user_id: str) -> list[dict]:
        items = self._carts.get(user_id, [])
        return [
            {'item_id': i.item_id, 'user_id': i.user_id, 'sku': i.sku,
             'quantity': i.quantity, 'price': i.price, 'added_at': i.added_at}
            for i in items
        ]

    def add_to_cart(self, user_id: str, sku: str, quantity: int, price: float) -> CartItem:
        cart = self._carts.setdefault(user_id, [])
        for item in cart:
            if item.sku == sku:
                item.quantity += quantity
                return item
        item = CartItem(item_id=str(uuid.uuid4()), user_id=user_id, sku=sku,
                        quantity=quantity, price=price)
        cart.append(item)
        return item

    def update_cart_item(self, user_id: str, item_id: str, quantity: int) -> Optional[dict]:
        cart = self._carts.get(user_id, [])
        for i, item in enumerate(cart):
            if item.item_id == item_id:
                if quantity <= 0:
                    del cart[i]
                    return None
                item.quantity = quantity
                return {'item_id': item.item_id, 'sku': item.sku, 'quantity': item.quantity, 'price': item.price}
        return None

    def remove_from_cart(self, user_id: str, item_id: str) -> bool:
        cart = self._carts.get(user_id, [])
        for i, item in enumerate(cart):
            if item.item_id == item_id:
                del cart[i]
                return True
        return False

    def create_order(self, user_id: str, shipping_address: dict, payment_method: str,
                     coupon_code: Optional[str] = None) -> dict:
        cart = self._carts.get(user_id, [])
        if not cart:
            raise ValueError('Cart is empty')
        items_snapshot = [
            {'sku': i.sku, 'quantity': i.quantity, 'price': i.price}
            for i in cart
        ]
        total = sum(i.price * i.quantity for i in cart)
        order_id = str(uuid.uuid4())
        order = {
            'order_id': order_id,
            'user_id': user_id,
            'items': items_snapshot,
            'total': total,
            'currency': 'USD',
            'status': 'pending',
            'shipping_address': shipping_address,
            'payment_method': payment_method,
            'coupon_code': coupon_code,
            'created_at': time.time(),
            'updated_at': time.time(),
        }
        self._orders[order_id] = order
        self._carts[user_id] = []  # clear cart
        return order

    def list_orders(self, user_id: str, cursor: Optional[str] = None, limit: int = 20) -> dict:
        orders = [o for o in self._orders.values() if o['user_id'] == user_id]
        orders.sort(key=lambda o: o['created_at'], reverse=True)
        offset = 0
        if cursor:
            try:
                offset = int(base64.b64decode(cursor.encode()).decode())
            except Exception:
                offset = 0
        page = orders[offset:offset + limit]
        has_more = offset + limit < len(orders)
        next_cursor = None
        if has_more:
            next_cursor = base64.b64encode(str(offset + limit).encode()).decode()
        return {'items': page, 'next_cursor': next_cursor, 'has_more': has_more}

    def get_order(self, order_id: str) -> Optional[dict]:
        return self._orders.get(order_id)

    def get_order_tracking(self, order_id: str) -> dict:
        order = self._orders.get(order_id)
        if not order:
            return {}
        return {
            'order_id': order_id,
            'status': order.get('status', 'pending'),
            'tracking_number': f'TRK{order_id[:8].upper()}',
            'carrier': 'FedEx',
            'estimated_delivery': time.time() + 3 * 86400,
            'events': [
                {'status': 'pending', 'description': 'Order placed', 'timestamp': order['created_at']},
            ],
        }

    def create_import_order(self, user_id: str, source_country: str, product_url: str,
                             quantity: int, estimated_price: float) -> dict:
        order_id = str(uuid.uuid4())
        order = {
            'order_id': order_id,
            'type': 'import',
            'user_id': user_id,
            'source_country': source_country,
            'product_url': product_url,
            'quantity': quantity,
            'estimated_price': estimated_price,
            'status': 'pending',
            'created_at': time.time(),
        }
        self._orders[order_id] = order
        return order

    def calculate_customs(self, price: float, currency: str, country: str, hs_code: str) -> dict:
        duty_rate = 0.08
        vat_rate = 0.10
        duty = price * duty_rate
        vat = (price + duty) * vat_rate
        return {
            'price': price,
            'currency': currency,
            'country': country,
            'hs_code': hs_code,
            'duty_rate': duty_rate,
            'duty_amount': round(duty, 2),
            'vat_rate': vat_rate,
            'vat_amount': round(vat, 2),
            'total_customs': round(duty + vat, 2),
            'total_landed_cost': round(price + duty + vat, 2),
        }
