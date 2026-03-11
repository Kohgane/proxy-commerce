"""국제 주문 라우터.

기존 router.py의 벤더별 라우팅에 추가로, 배송 목적국별 처리 로직:
- 국가 감지 (Shopify 주문의 shipping_address.country_code)
- 세관 서류 자동 생성 (CustomsDocumentHelper)
- 국가별 배송 방법 자동 선택 (ShippingEstimator)
- DDP/DAP에 따른 세금 처리 분기
"""
import logging
from decimal import Decimal

from ..shipping import get_country, TaxCalculator, ShippingEstimator
from ..shipping.customs_document import CustomsDocumentHelper

logger = logging.getLogger(__name__)

# 발송인 기본 정보 (환경변수로 오버라이드 가능)
_DEFAULT_SENDER = {
    'name': 'Proxy Commerce',
    'address': 'Seoul, Korea',
    'phone': '',
    'email': '',
}


class InternationalRouter:
    """국제 주문 라우터."""

    def __init__(self):
        self.tax_calc = TaxCalculator()
        self.shipping_est = ShippingEstimator()
        self.customs_helper = CustomsDocumentHelper()

    # ── 공개 API ────────────────────────────────────────────────────────────

    def route_international_order(self, order: dict) -> dict:
        """Shopify 주문 → 국제 배송 라우팅 결과.

        Args:
            order: Shopify 주문 dict (shipping_address.country_code 필수)

        Returns:
            {
                'country_code': str,
                'country_config': CountryConfig,
                'shipping_method': dict,          # ShippingEstimate 상세
                'tax_detail': dict,               # calc_import_tax() 결과
                'customs_invoice': dict,          # generate_invoice_data() 결과
                'incoterms': str,                 # 'DDP' or 'DAP'
                'total_shipping_krw': Decimal,
                'total_tax_local': Decimal,
            }
        """
        country_code = self.detect_country(order)
        config = get_country(country_code)

        # 총 중량 계산 (라인아이템별 weight 합산, 기본값 0.5kg)
        total_weight_kg = self._calc_total_weight(order)

        # 배송 방법 선택
        shipping = self.select_shipping_method(country_code, total_weight_kg)

        # 세금 계산
        tax_detail = self.calc_order_taxes(order, country_code)

        # 세관 서류 생성
        customs_invoice = self.generate_customs_documents(order, country_code)

        total_tax_local = tax_detail.get('total_tax_local', Decimal('0'))

        return {
            'country_code': country_code,
            'country_config': config,
            'shipping_method': shipping,
            'tax_detail': tax_detail,
            'customs_invoice': customs_invoice,
            'incoterms': config.incoterms,
            'total_shipping_krw': shipping.get('cost_krw', Decimal('0')),
            'total_tax_local': total_tax_local,
        }

    def detect_country(self, order: dict) -> str:
        """주문에서 배송국가 코드 추출.

        Args:
            order: Shopify 주문 dict

        Returns:
            ISO alpha-2 국가 코드 (대문자)

        Raises:
            ValueError: 국가 코드가 없거나 지원하지 않는 국가
        """
        shipping_address = order.get('shipping_address') or {}
        country_code = (
            shipping_address.get('country_code')
            or shipping_address.get('country_iso')
            or order.get('country_code')
            or ''
        )
        if not country_code:
            raise ValueError('주문에 배송 국가 코드(shipping_address.country_code)가 없습니다.')
        # 유효성 검증 (지원 여부 확인)
        return get_country(country_code.upper().strip()).code

    def select_shipping_method(
        self,
        country_code: str,
        total_weight_kg: Decimal,
        prefer: str = 'cheapest',
    ) -> dict:
        """국가/중량/선호도에 따라 배송 방법 자동 선택.

        Args:
            country_code: ISO alpha-2 국가 코드
            total_weight_kg: 총 중량 (kg)
            prefer: 선택 기준 — 'cheapest' (최저가) 또는 'fastest' (최속)

        Returns:
            배송 방법 dict:
            {
                'method': str,
                'cost_krw': Decimal,
                'delivery_days_min': int,
                'delivery_days_max': int,
                'tracking': bool,
            }
        """
        weight = Decimal(str(total_weight_kg)) if total_weight_kg else Decimal('0.5')
        if weight <= Decimal('0'):
            weight = Decimal('0.5')

        if prefer == 'fastest':
            est = self.shipping_est.fastest(country_code, weight)
        else:
            est = self.shipping_est.cheapest(country_code, weight)

        return {
            'method': est.method,
            'cost_krw': est.cost_krw,
            'delivery_days_min': est.delivery_days_min,
            'delivery_days_max': est.delivery_days_max,
            'tracking': est.tracking,
        }

    def generate_customs_documents(self, order: dict, country_code: str) -> dict:
        """주문 기반 세관 서류 데이터 자동 생성.

        Args:
            order: Shopify 주문 dict
            country_code: 목적국 ISO alpha-2 코드

        Returns:
            CustomsDocumentHelper.generate_invoice_data() 결과 dict
        """
        line_items = order.get('line_items', [])
        shipping_address = order.get('shipping_address') or {}
        customer_info = order.get('customer') or {}
        billing = order.get('billing_address') or {}

        # 발송인 정보
        sender_info = dict(_DEFAULT_SENDER)

        # 수하인 정보 (배송지 기준)
        receiver_name = (
            shipping_address.get('name')
            or (
                (customer_info.get('first_name', '') + ' ' + customer_info.get('last_name', '')).strip()
            )
            or billing.get('name', '')
        )
        receiver_info = {
            'name': receiver_name,
            'address': self._format_address(shipping_address),
            'phone': shipping_address.get('phone', ''),
            'email': customer_info.get('email', '') or order.get('email', ''),
        }

        # 주문 라인아이템 → 세관 서류 품목
        order_items = []
        for item in line_items:
            order_items.append({
                'description': str(item.get('title', item.get('name', ''))),
                'category': str(item.get('product_type', '') or item.get('category', '')),
                'hs_code': str(item.get('hs_code', '')),
                'quantity': int(item.get('quantity', 1) or 1),
                'unit_value': Decimal(str(item.get('price', '0') or '0')),
                'currency': str(item.get('currency', 'USD')),
                'origin_country': str(item.get('origin_country', 'KR')),
                'weight_kg': Decimal(str(item.get('grams', 500) or 500)) / Decimal('1000'),
            })

        if not order_items:
            # 빈 주문이더라도 최소 구조 반환
            order_items = [{
                'description': 'Goods',
                'category': '',
                'hs_code': '',
                'quantity': 1,
                'unit_value': Decimal('0'),
                'currency': 'USD',
                'origin_country': 'KR',
                'weight_kg': Decimal('0.5'),
            }]

        return self.customs_helper.generate_invoice_data(
            order_items=order_items,
            destination_country=country_code,
            sender_info=sender_info,
            receiver_info=receiver_info,
        )

    def calc_order_taxes(self, order: dict, country_code: str) -> dict:
        """주문의 모든 라인아이템에 대해 세금 일괄 계산.

        Args:
            order: Shopify 주문 dict
            country_code: 목적국 ISO alpha-2 코드

        Returns:
            {
                'country_code': str,
                'items': [per-item tax detail],
                'total_goods_local': Decimal,
                'total_tax_local': Decimal,
                'incoterms': str,
                'de_minimis_exempt': bool,     # 모든 아이템이 면세 여부
            }
        """
        line_items = order.get('line_items', [])
        config = get_country(country_code)
        items_detail = []
        total_goods_local = Decimal('0')
        total_tax_local = Decimal('0')

        for item in line_items:
            price = Decimal(str(item.get('price', '0') or '0'))
            quantity = int(item.get('quantity', 1) or 1)
            goods_value = price * quantity
            currency = str(item.get('currency', 'USD'))

            try:
                tax = self.tax_calc.calc_import_tax(
                    country_code=country_code,
                    goods_value=goods_value,
                    goods_currency=currency,
                )
                items_detail.append({
                    'sku': item.get('sku', ''),
                    'title': item.get('title', ''),
                    'goods_value': goods_value,
                    'currency': currency,
                    'tax_detail': tax,
                })
                total_goods_local += tax['goods_value_local']
                total_tax_local += tax['total_tax']
            except Exception as exc:
                logger.warning('라인아이템 세금 계산 실패 SKU=%s: %s', item.get('sku', '?'), exc)

        all_exempt = all(
            d['tax_detail'].get('de_minimis_exempt', False)
            for d in items_detail
        ) if items_detail else False

        return {
            'country_code': country_code,
            'items': items_detail,
            'total_goods_local': total_goods_local,
            'total_tax_local': total_tax_local,
            'incoterms': config.incoterms,
            'de_minimis_exempt': all_exempt,
        }

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────────

    def _calc_total_weight(self, order: dict) -> Decimal:
        """주문 라인아이템의 총 중량 계산 (grams → kg)."""
        line_items = order.get('line_items', [])
        total_grams = Decimal('0')
        for item in line_items:
            grams = Decimal(str(item.get('grams', 500) or 500))
            qty = Decimal(str(item.get('quantity', 1) or 1))
            total_grams += grams * qty
        kg = total_grams / Decimal('1000')
        return kg if kg > Decimal('0') else Decimal('0.5')

    def _format_address(self, address: dict) -> str:
        """주소 dict → 한 줄 문자열."""
        parts = [
            address.get('address1', ''),
            address.get('address2', ''),
            address.get('city', ''),
            address.get('province', ''),
            address.get('zip', ''),
            address.get('country', ''),
        ]
        return ', '.join(p for p in parts if p)
