"""src/china_marketplace/taobao_agent.py — 타오바오 자동 구매 에이전트 mock (Phase 104)."""
from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TaobaoProduct:
    product_id: str
    title: str
    price_cny: float
    original_price_cny: float
    shipping_fee_cny: float
    seller_id: str
    seller_name: str
    stock: int
    rating: float
    sales_count: int
    url: str
    sku_options: Dict = field(default_factory=dict)
    images: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'product_id': self.product_id,
            'title': self.title,
            'price_cny': self.price_cny,
            'original_price_cny': self.original_price_cny,
            'shipping_fee_cny': self.shipping_fee_cny,
            'seller_id': self.seller_id,
            'seller_name': self.seller_name,
            'stock': self.stock,
            'rating': self.rating,
            'sales_count': self.sales_count,
            'url': self.url,
            'sku_options': self.sku_options,
            'images': self.images,
        }


@dataclass
class TaobaoOrder:
    taobao_order_id: str
    product_id: str
    quantity: int
    unit_price_cny: float
    total_price_cny: float
    shipping_address: str
    status: str = 'created'
    coupon_discount_cny: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return {
            'taobao_order_id': self.taobao_order_id,
            'product_id': self.product_id,
            'quantity': self.quantity,
            'unit_price_cny': self.unit_price_cny,
            'total_price_cny': self.total_price_cny,
            'shipping_address': self.shipping_address,
            'status': self.status,
            'coupon_discount_cny': self.coupon_discount_cny,
            'created_at': self.created_at,
        }


class TaobaoAgent:
    """타오바오 자동 구매 에이전트 mock."""

    DEFAULT_WAREHOUSE_ADDRESS = '广东省广州市番禺区代收仓库001号'

    def __init__(self):
        self._orders: Dict[str, TaobaoOrder] = {}
        logger.info("TaobaoAgent 초기화 완료")

    # ── 상품 검색 ────────────────────────────────────────────────────────────

    def search(self, keyword: str, max_results: int = 10) -> List[TaobaoProduct]:
        """키워드 기반 상품 검색 (mock)."""
        results = []
        for i in range(min(max_results, 5)):
            product = TaobaoProduct(
                product_id=f'tb_{uuid.uuid4().hex[:8]}',
                title=f'{keyword} 관련상품 {i + 1}',
                price_cny=round(random.uniform(10, 500), 2),
                original_price_cny=round(random.uniform(500, 800), 2),
                shipping_fee_cny=round(random.uniform(0, 15), 2),
                seller_id=f'seller_{uuid.uuid4().hex[:6]}',
                seller_name=f'우수판매자{i + 1}号店',
                stock=random.randint(10, 1000),
                rating=round(random.uniform(4.0, 5.0), 1),
                sales_count=random.randint(100, 50000),
                url=f'https://item.taobao.com/item.htm?id={uuid.uuid4().hex[:10]}',
                sku_options={'색상': ['레드', '블루', '블랙'], '사이즈': ['S', 'M', 'L', 'XL']},
                images=[f'https://img.alicdn.com/imgextra/{uuid.uuid4().hex}.jpg'],
            )
            results.append(product)
        logger.info("타오바오 검색: '%s' → %d건", keyword, len(results))
        return results

    def search_by_url(self, url: str) -> Optional[TaobaoProduct]:
        """URL 기반 상품 조회 (mock)."""
        return TaobaoProduct(
            product_id=f'tb_{uuid.uuid4().hex[:8]}',
            title='타오바오 상품 (URL 조회)',
            price_cny=round(random.uniform(20, 300), 2),
            original_price_cny=round(random.uniform(300, 500), 2),
            shipping_fee_cny=round(random.uniform(0, 10), 2),
            seller_id=f'seller_{uuid.uuid4().hex[:6]}',
            seller_name='우수판매자直营店',
            stock=random.randint(5, 500),
            rating=round(random.uniform(4.2, 5.0), 1),
            sales_count=random.randint(50, 10000),
            url=url,
            sku_options={},
            images=[],
        )

    # ── 상품 상세 ────────────────────────────────────────────────────────────

    def get_detail(self, product_id: str) -> Dict:
        """상품 상세 정보 조회 (mock)."""
        return {
            'product_id': product_id,
            'title': f'상품 상세 {product_id}',
            'price_cny': round(random.uniform(10, 500), 2),
            'shipping_fee_cny': round(random.uniform(0, 15), 2),
            'stock': random.randint(10, 500),
            'rating': round(random.uniform(4.0, 5.0), 1),
            'sales_count': random.randint(100, 50000),
            'seller': {
                'seller_id': f'seller_{uuid.uuid4().hex[:6]}',
                'name': '优质卖家직营점',
                'years_active': random.randint(1, 10),
                'rating': round(random.uniform(4.5, 5.0), 2),
            },
            'sku_options': {'색상': ['화이트', '블랙'], '사이즈': ['M', 'L']},
            'description': '고품질 상품입니다.',
        }

    # ── 셀러 신뢰도 평가 ─────────────────────────────────────────────────────

    def evaluate_seller(self, seller_id: str) -> Dict:
        """셀러 신뢰도 평가 (판매량/평점/운영기간 기반 mock)."""
        sales_count = random.randint(1000, 100000)
        rating = round(random.uniform(4.0, 5.0), 2)
        years_active = random.randint(1, 12)
        score = min(100, int(
            (sales_count / 1000) * 0.3 +
            rating * 15 +
            years_active * 2
        ))
        return {
            'seller_id': seller_id,
            'sales_count': sales_count,
            'rating': rating,
            'years_active': years_active,
            'trust_score': score,
            'verified': score >= 70,
            'badges': ['우량판매자'] if score >= 80 else [],
        }

    # ── 주문 생성 ────────────────────────────────────────────────────────────

    def place_order(
        self,
        product_id: str,
        quantity: int,
        unit_price_cny: float,
        shipping_address: Optional[str] = None,
        apply_coupon: bool = True,
    ) -> TaobaoOrder:
        """주문 생성 (배송대행지 주소 자동 설정, 쿠폰 자동 적용 mock)."""
        address = shipping_address or self.DEFAULT_WAREHOUSE_ADDRESS
        coupon = round(random.uniform(0, unit_price_cny * 0.1), 2) if apply_coupon else 0.0
        total = round(unit_price_cny * quantity - coupon, 2)
        order = TaobaoOrder(
            taobao_order_id=f'TB{uuid.uuid4().hex[:12].upper()}',
            product_id=product_id,
            quantity=quantity,
            unit_price_cny=unit_price_cny,
            total_price_cny=total,
            shipping_address=address,
            coupon_discount_cny=coupon,
        )
        self._orders[order.taobao_order_id] = order
        logger.info("타오바오 주문 생성: %s", order.taobao_order_id)
        return order

    # ── 주문 추적 ────────────────────────────────────────────────────────────

    def track_order(self, taobao_order_id: str) -> Dict:
        """주문 상태 추적 (mock)."""
        statuses = ['결제완료', '판매자발송', '운송중', '세관통과', '배송대행지도착']
        return {
            'taobao_order_id': taobao_order_id,
            'status': random.choice(statuses),
            'tracking_number': f'SF{uuid.uuid4().hex[:12].upper()}',
            'carrier': '순풍택배',
            'estimated_arrival': '3-5일',
            'events': [
                {'time': datetime.now(timezone.utc).isoformat(), 'description': '결제 완료'},
            ],
        }

    def get_order(self, taobao_order_id: str) -> Optional[TaobaoOrder]:
        return self._orders.get(taobao_order_id)

    def list_orders(self) -> List[TaobaoOrder]:
        return list(self._orders.values())

    # ── 쿠폰/흥정 ────────────────────────────────────────────────────────────

    def negotiate_price(self, product_id: str, target_price_cny: float) -> Dict:
        """가격 흥정 시뮬레이션 (mock)."""
        accepted = random.random() > 0.4
        final_price = target_price_cny if accepted else round(target_price_cny * 1.05, 2)
        return {
            'product_id': product_id,
            'requested_price': target_price_cny,
            'final_price': final_price,
            'accepted': accepted,
            'message': '판매자가 가격을 수락했습니다.' if accepted else '판매자가 가격을 조정했습니다.',
        }

    def apply_coupon(self, order_id: str, coupon_code: str) -> Dict:
        """쿠폰 적용 시뮬레이션 (mock)."""
        discount = round(random.uniform(1, 20), 2)
        return {
            'order_id': order_id,
            'coupon_code': coupon_code,
            'discount_cny': discount,
            'applied': True,
        }
