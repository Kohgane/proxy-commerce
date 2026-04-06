"""src/china_marketplace/alibaba_agent.py — 1688 B2B 자동 구매 에이전트 mock (Phase 104)."""
from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Alibaba1688Product:
    product_id: str
    title: str
    moq: int  # 최소주문수량
    price_tiers: List[Dict]  # [{'min_qty': 10, 'price_cny': 5.0}, ...]
    supplier_type: str  # 'factory' | 'wholesaler'
    supplier_id: str
    supplier_name: str
    stock: int
    rating: float
    url: str
    certifications: List[str] = field(default_factory=list)
    sample_available: bool = False
    sample_price_cny: float = 0.0

    def get_price_for_qty(self, qty: int) -> float:
        """수량에 맞는 단가 반환."""
        applicable = [t for t in self.price_tiers if qty >= t['min_qty']]
        if not applicable:
            return self.price_tiers[0]['price_cny'] if self.price_tiers else 0.0
        return min(applicable, key=lambda t: t['price_cny'])['price_cny']

    def to_dict(self) -> Dict:
        return {
            'product_id': self.product_id,
            'title': self.title,
            'moq': self.moq,
            'price_tiers': self.price_tiers,
            'supplier_type': self.supplier_type,
            'supplier_id': self.supplier_id,
            'supplier_name': self.supplier_name,
            'stock': self.stock,
            'rating': self.rating,
            'url': self.url,
            'certifications': self.certifications,
            'sample_available': self.sample_available,
            'sample_price_cny': self.sample_price_cny,
        }


@dataclass
class Alibaba1688Order:
    order_id: str
    product_id: str
    supplier_id: str
    quantity: int
    unit_price_cny: float
    total_price_cny: float
    is_sample: bool = False
    bulk_discount_rate: float = 0.0
    status: str = 'created'
    certifications_checked: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return {
            'order_id': self.order_id,
            'product_id': self.product_id,
            'supplier_id': self.supplier_id,
            'quantity': self.quantity,
            'unit_price_cny': self.unit_price_cny,
            'total_price_cny': self.total_price_cny,
            'is_sample': self.is_sample,
            'bulk_discount_rate': self.bulk_discount_rate,
            'status': self.status,
            'certifications_checked': self.certifications_checked,
            'created_at': self.created_at,
        }


class Alibaba1688Agent:
    """1688 B2B 자동 구매 에이전트 mock."""

    def __init__(self):
        self._orders: Dict[str, Alibaba1688Order] = {}
        logger.info("Alibaba1688Agent 초기화 완료")

    # ── 상품 검색 ────────────────────────────────────────────────────────────

    def search(self, keyword: str, max_results: int = 10, supplier_type: Optional[str] = None) -> List[Alibaba1688Product]:
        """키워드 기반 상품 검색 (mock)."""
        results = []
        for i in range(min(max_results, 5)):
            stype = supplier_type or random.choice(['factory', 'wholesaler'])
            product = Alibaba1688Product(
                product_id=f'ali_{uuid.uuid4().hex[:8]}',
                title=f'{keyword} B2B상품 {i + 1}',
                moq=random.choice([10, 50, 100, 200, 500]),
                price_tiers=[
                    {'min_qty': 10, 'price_cny': round(random.uniform(5, 50), 2)},
                    {'min_qty': 100, 'price_cny': round(random.uniform(3, 40), 2)},
                    {'min_qty': 500, 'price_cny': round(random.uniform(1, 30), 2)},
                ],
                supplier_type=stype,
                supplier_id=f'sup_{uuid.uuid4().hex[:6]}',
                supplier_name=f'{"工厂直供" if stype == "factory" else "批发商"}{i + 1}号',
                stock=random.randint(1000, 100000),
                rating=round(random.uniform(3.8, 5.0), 1),
                url=f'https://detail.1688.com/offer/{uuid.uuid4().hex[:10]}.html',
                certifications=random.sample(['ISO9001', 'CE', 'RoHS', 'SGS'], k=random.randint(0, 2)),
                sample_available=random.random() > 0.5,
                sample_price_cny=round(random.uniform(20, 100), 2),
            )
            results.append(product)
        logger.info("1688 검색: '%s' → %d건", keyword, len(results))
        return results

    def search_by_url(self, url: str) -> Optional[Alibaba1688Product]:
        """URL 기반 상품 조회 (mock)."""
        return Alibaba1688Product(
            product_id=f'ali_{uuid.uuid4().hex[:8]}',
            title='1688 상품 (URL 조회)',
            moq=100,
            price_tiers=[
                {'min_qty': 100, 'price_cny': 8.5},
                {'min_qty': 500, 'price_cny': 6.0},
                {'min_qty': 1000, 'price_cny': 4.5},
            ],
            supplier_type='factory',
            supplier_id=f'sup_{uuid.uuid4().hex[:6]}',
            supplier_name='공장직공급업체',
            stock=50000,
            rating=4.7,
            url=url,
            certifications=['ISO9001'],
            sample_available=True,
            sample_price_cny=50.0,
        )

    # ── MOQ / 단가 체크 ──────────────────────────────────────────────────────

    def check_moq(self, product_id: str, quantity: int) -> Dict:
        """MOQ 체크 및 단가 구간 조회 (mock)."""
        moq = random.choice([10, 50, 100])
        meets_moq = quantity >= moq
        unit_price = round(random.uniform(3, 50), 2) if meets_moq else None
        return {
            'product_id': product_id,
            'requested_qty': quantity,
            'moq': moq,
            'meets_moq': meets_moq,
            'unit_price_cny': unit_price,
            'total_price_cny': round(unit_price * quantity, 2) if unit_price else None,
            'message': '주문 가능' if meets_moq else f'최소 주문 수량은 {moq}개입니다.',
        }

    # ── 공장 vs 도매상 구분 ─────────────────────────────────────────────────

    def get_supplier_detail(self, supplier_id: str) -> Dict:
        """공급업체 상세 정보 (mock)."""
        stype = random.choice(['factory', 'wholesaler'])
        return {
            'supplier_id': supplier_id,
            'supplier_type': stype,
            'name': '공장직공급업체' if stype == 'factory' else '도매상',
            'years_active': random.randint(2, 15),
            'rating': round(random.uniform(4.0, 5.0), 2),
            'transaction_level': random.choice(['gold', 'diamond', 'crown']),
            'response_rate': round(random.uniform(0.8, 1.0), 2),
            'is_factory': stype == 'factory',
            'certifications': random.sample(['ISO9001', 'CE', 'RoHS'], k=random.randint(0, 2)),
        }

    # ── 샘플 주문 ────────────────────────────────────────────────────────────

    def place_sample_order(self, product_id: str, supplier_id: str, sample_price_cny: float) -> Alibaba1688Order:
        """샘플 주문 생성 (mock)."""
        order = Alibaba1688Order(
            order_id=f'ALI_SAMPLE_{uuid.uuid4().hex[:10].upper()}',
            product_id=product_id,
            supplier_id=supplier_id,
            quantity=1,
            unit_price_cny=sample_price_cny,
            total_price_cny=sample_price_cny,
            is_sample=True,
        )
        self._orders[order.order_id] = order
        logger.info("1688 샘플 주문 생성: %s", order.order_id)
        return order

    # ── 대량 주문 ────────────────────────────────────────────────────────────

    def place_bulk_order(
        self,
        product_id: str,
        supplier_id: str,
        quantity: int,
        unit_price_cny: float,
        negotiate_discount: bool = True,
    ) -> Alibaba1688Order:
        """대량 주문 생성 (할인 협상 mock)."""
        discount_rate = 0.0
        if negotiate_discount and quantity >= 500:
            discount_rate = round(random.uniform(0.02, 0.10), 3)
        final_price = round(unit_price_cny * (1 - discount_rate), 2)
        total = round(final_price * quantity, 2)
        order = Alibaba1688Order(
            order_id=f'ALI_{uuid.uuid4().hex[:12].upper()}',
            product_id=product_id,
            supplier_id=supplier_id,
            quantity=quantity,
            unit_price_cny=final_price,
            total_price_cny=total,
            bulk_discount_rate=discount_rate,
        )
        self._orders[order.order_id] = order
        logger.info("1688 대량 주문 생성: %s (수량: %d, 할인: %.1f%%)", order.order_id, quantity, discount_rate * 100)
        return order

    # ── 품질 인증서 ──────────────────────────────────────────────────────────

    def check_certifications(self, supplier_id: str) -> Dict:
        """품질 인증서 확인 (mock)."""
        certs = random.sample(['ISO9001', 'CE', 'RoHS', 'SGS', 'BRC'], k=random.randint(0, 3))
        return {
            'supplier_id': supplier_id,
            'certifications': certs,
            'verified': len(certs) > 0,
            'last_audit': '2024-01-15',
            'next_audit': '2025-01-15',
        }

    # ── 할인 협상 ────────────────────────────────────────────────────────────

    def negotiate_bulk_discount(self, product_id: str, quantity: int, target_unit_price_cny: float) -> Dict:
        """대량 구매 할인 협상 시뮬레이션 (mock)."""
        accepted = random.random() > 0.3
        offered_price = target_unit_price_cny if accepted else round(target_unit_price_cny * 1.08, 2)
        return {
            'product_id': product_id,
            'quantity': quantity,
            'requested_price': target_unit_price_cny,
            'offered_price': offered_price,
            'accepted': accepted,
            'discount_rate': round(1 - offered_price / (offered_price / (1 - 0.05 if accepted else 0)), 4) if accepted else 0.0,
        }

    def get_order(self, order_id: str) -> Optional[Alibaba1688Order]:
        return self._orders.get(order_id)

    def list_orders(self) -> List[Alibaba1688Order]:
        return list(self._orders.values())
