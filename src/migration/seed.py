"""src/migration/seed.py — Phase 42: 개발/테스트용 시드 데이터 생성기."""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List

logger = logging.getLogger(__name__)

# 한국어 샘플 데이터
_PRODUCT_NAMES = [
    '프리미엄 노트북 가방', '무선 블루투스 이어폰', '스마트워치 밴드', '노트북 스탠드', '기계식 키보드',
    '울트라 슬림 마우스', '4K 모니터', 'USB-C 허브', '웹캠 Full HD', '게이밍 헤드셋',
    '에코백 캔버스', '보온 텀블러', '가죽 지갑', '스포츠 운동화', '방수 트레킹화',
    '아로마 디퓨저', '공기청정기 미니', '전동 칫솔', '마사지 쿠션', '넥 필로우',
    '조리개 에어프라이어', '전기 주전자', '핸드 블렌더', '주방 저울', '다기능 냄비',
    '캐시미어 스카프', '양모 담요', '침대 메모리폼 베개', '모션 감지 야간 조명', '무선 충전 패드',
    '독서대 접이식', '화이트보드 미니', '수채화 물감 세트', '스케치북 A4', '캘리그래피 펜',
    '요가 매트', '덤벨 세트', '폼롤러', '줄넘기 전문가용', '스트레칭 밴드 세트',
    '식물성 단백질 파우더', '비타민C 1000mg', '오메가3 영양제', '유산균 프로바이오틱스', '마그네슘 수면 보조',
    '향균 마스크', '손 소독제 프리미엄', '자외선 차단 선크림', '천연 세면 비누', '비건 샴푸',
]

_CATEGORIES = ['전자제품', '패션/의류', '생활용품', '주방/식품', '스포츠/레저', '건강/뷰티']

_CUSTOMER_NAMES = [
    '김민준', '이서연', '박도현', '최유진', '정수빈',
    '강태양', '윤지호', '임수아', '한예린', '오지훈',
    '신민서', '황준혁', '류소연', '조현우', '백채원',
    '서동현', '문지현', '양준서', '배수진', '안태양',
]


class SeedGenerator:
    """개발/테스트용 시드 데이터 생성기."""

    def generate_products(self, count: int = 50) -> List[dict]:
        """상품 시드 데이터 생성."""
        products = []
        for i in range(count):
            product_id = str(uuid.uuid4())[:8]
            name = _PRODUCT_NAMES[i % len(_PRODUCT_NAMES)]
            category = _CATEGORIES[i % len(_CATEGORIES)]
            price = int(10000 + (i * 3700) % 990000)
            products.append({
                'id': product_id,
                'name': name,
                'sku': f'SKU-{i + 1:04d}',
                'category': category,
                'price': price,
                'stock': (i * 7 + 5) % 100,
                'status': 'active' if i % 10 != 0 else 'inactive',
                'created_at': _iso_ago(days=i % 365),
            })
        logger.info("상품 시드 %d개 생성", len(products))
        return products

    def generate_customers(self, count: int = 20) -> List[dict]:
        """고객 시드 데이터 생성."""
        customers = []
        for i in range(count):
            cust_id = str(uuid.uuid4())[:8]
            name = _CUSTOMER_NAMES[i % len(_CUSTOMER_NAMES)]
            customers.append({
                'id': cust_id,
                'name': name,
                'email': f'user{i + 1}@example.com',
                'phone': f'010-{1000 + i:04d}-{5000 + i:04d}',
                'grade': ['일반', '실버', '골드', 'VIP'][i % 4],
                'total_orders': (i * 3 + 1) % 50,
                'total_spent': int((i * 45000 + 10000) % 5000000),
                'created_at': _iso_ago(days=i * 15 % 365),
            })
        logger.info("고객 시드 %d개 생성", len(customers))
        return customers

    def generate_orders(self, count: int = 30, products: List[dict] = None,
                        customers: List[dict] = None) -> List[dict]:
        """주문 시드 데이터 생성."""
        if not products:
            products = self.generate_products(10)
        if not customers:
            customers = self.generate_customers(10)
        statuses = ['new', 'ordered', 'shipped_domestic', 'delivered', 'cancelled']
        orders = []
        for i in range(count):
            order_id = str(uuid.uuid4())[:8]
            customer = customers[i % len(customers)]
            product = products[i % len(products)]
            qty = (i % 3) + 1
            total = product['price'] * qty
            orders.append({
                'id': order_id,
                'customer_id': customer['id'],
                'customer_name': customer['name'],
                'items': [{'product_id': product['id'], 'name': product['name'],
                           'qty': qty, 'price': product['price']}],
                'total_amount': total,
                'status': statuses[i % len(statuses)],
                'created_at': _iso_ago(days=i % 90),
            })
        logger.info("주문 시드 %d개 생성", len(orders))
        return orders

    def generate_all(self) -> dict:
        """전체 시드 데이터 생성."""
        products = self.generate_products(50)
        customers = self.generate_customers(20)
        orders = self.generate_orders(30, products=products, customers=customers)
        return {
            'products': products,
            'customers': customers,
            'orders': orders,
        }


def _iso_ago(days: int = 0) -> str:
    """현재 시각 기준으로 N일 전 ISO 문자열."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
