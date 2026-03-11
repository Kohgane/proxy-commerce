"""통관 서류 생성 헬퍼."""
import uuid
from datetime import date
from decimal import Decimal


# 우리 취급 카테고리별 기본 HS 코드
HS_CODE_MAP = {
    'bag': '4202.21',         # 핸드백 (가죽)
    'wallet': '4202.31',      # 지갑 (가죽)
    'pouch': '4202.92',       # 파우치/케이스
    'perfume': '3303.00',     # 향수
    'cosmetics': '3304.99',   # 화장품 기타
    'clothing': '6109.10',    # 티셔츠 (면)
    'accessories': '7117.19',  # 모조 액세서리
}


class CustomsDocumentHelper:
    """통관 서류 데이터 생성."""

    def generate_invoice_data(
        self,
        order_items: list,
        destination_country: str,
        sender_info: dict,
        receiver_info: dict,
    ) -> dict:
        """상업 인보이스 데이터 생성.

        Args:
            order_items: 주문 상품 리스트. 각 항목은 dict:
                {
                    'description': str,
                    'category': str,       # HS 코드 자동 매핑에 사용
                    'hs_code': str,        # 직접 지정 시 우선 사용
                    'quantity': int,
                    'unit_value': Decimal,
                    'currency': str,
                    'origin_country': str, # 원산지 (기본 'KR')
                    'weight_kg': Decimal,
                }
            destination_country: ISO alpha-2 목적국 코드
            sender_info: 송하인 정보 dict (name, address, phone, email)
            receiver_info: 수하인 정보 dict (name, address, phone, email)

        Returns:
            상업 인보이스 데이터 dict
        """
        from .country_config import get_country
        config = get_country(destination_country)

        items = []
        total_value = Decimal('0')
        currency = None

        for item in order_items:
            hs_code = item.get('hs_code') or self.get_hs_code(item.get('category', ''))
            unit_value = Decimal(str(item.get('unit_value', '0')))
            qty = int(item.get('quantity', 1))
            item_currency = item.get('currency', 'USD')
            if currency is None:
                currency = item_currency
            total_value += unit_value * qty
            items.append({
                'description': item.get('description', ''),
                'hs_code': hs_code,
                'quantity': qty,
                'unit_value': unit_value,
                'currency': item_currency,
                'origin_country': item.get('origin_country', 'KR'),
                'weight_kg': Decimal(str(item.get('weight_kg', '0'))),
            })

        return {
            'invoice_number': f'INV-{uuid.uuid4().hex[:8].upper()}',
            'date': date.today().isoformat(),
            'sender': sender_info,
            'receiver': receiver_info,
            'items': items,
            'total_value': total_value,
            'currency': currency or 'USD',
            'incoterms': config.incoterms,
        }

    def get_hs_code(self, category: str) -> str:
        """카테고리 → HS 코드 매핑."""
        return HS_CODE_MAP.get(category.lower(), '9999.99')
