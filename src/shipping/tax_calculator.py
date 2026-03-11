"""국가별 수입세/VAT/관세 계산기.

docs/PROGRESS.md의 국가별 통관 요건을 계산 로직으로 구현.
"""
from decimal import Decimal
from .country_config import get_country

# 이 국가들은 de_minimis 이하일 때 관세+VAT 모두 면제 (완전 면세)
_FULL_EXEMPTION_COUNTRIES = {'JP', 'PH'}


def _convert_currency(amount: Decimal, from_currency: str, to_currency: str, fx_rates: dict) -> Decimal:
    """KRW 피벗을 이용해 두 통화 사이를 환산한다.

    fx_rates 키 형식: '{FROM}KRW' (예: 'USDKRW', 'GBPKRW')
    """
    if from_currency == to_currency:
        return amount

    # from_currency → KRW
    if from_currency == 'KRW':
        amount_krw = amount
    else:
        key = f'{from_currency}KRW'
        if key not in fx_rates:
            raise ValueError(f'환율 정보 없음: {key}. fx_rates에 추가하세요.')
        amount_krw = amount * Decimal(str(fx_rates[key]))

    # KRW → to_currency
    if to_currency == 'KRW':
        return amount_krw

    key_out = f'{to_currency}KRW'
    if key_out not in fx_rates:
        raise ValueError(f'환율 정보 없음: {key_out}. fx_rates에 추가하세요.')
    return amount_krw / Decimal(str(fx_rates[key_out]))


class TaxCalculator:
    """국가별 세금/관세 계산기."""

    def calc_import_tax(
        self,
        country_code: str,
        goods_value: Decimal,
        goods_currency: str,
        shipping_cost: Decimal = Decimal('0'),
        fx_rates: dict = None,
    ) -> dict:
        """수입세/관세/VAT 계산.

        Args:
            country_code: 목적국 ISO alpha-2 코드
            goods_value: 상품가액 (goods_currency 기준)
            goods_currency: 상품 가액 통화
            shipping_cost: 배송비 (goods_currency 기준)
            fx_rates: 환율 딕셔너리 (USDKRW, GBPKRW 등). None이면 기본값.

        Returns:
            {
                'country': str,
                'goods_value_local': Decimal,    # 현지통화 환산 상품가액
                'shipping_cost_local': Decimal,  # 현지통화 환산 배송비
                'de_minimis_exempt': bool,       # 면세 해당 여부
                'duty': Decimal,                 # 관세 (현지통화)
                'vat': Decimal,                  # VAT/GST (현지통화)
                'total_tax': Decimal,            # duty + vat
                'total_landed': Decimal,         # 상품 + 배송 + 세금
                'incoterms': str,                # 추천 Incoterms
                'notes': str,
                'breakdown': dict,               # 상세 내역
            }
        """
        if fx_rates is None:
            fx_rates = {}

        goods_value = Decimal(str(goods_value))
        shipping_cost = Decimal(str(shipping_cost))

        config = get_country(country_code)

        # 현지통화 환산
        goods_value_local = _convert_currency(goods_value, goods_currency, config.currency, fx_rates)
        shipping_cost_local = _convert_currency(shipping_cost, goods_currency, config.currency, fx_rates)

        # de minimis 판정: de_minimis > 0 이고 상품가액이 기준 이하이면 면세
        de_minimis_exempt = False
        if config.de_minimis > Decimal('0'):
            goods_in_dm_currency = _convert_currency(
                goods_value, goods_currency, config.de_minimis_currency, fx_rates
            )
            if goods_in_dm_currency <= config.de_minimis:
                de_minimis_exempt = True

        duty = Decimal('0')
        vat = Decimal('0')

        if de_minimis_exempt:
            # 완전 면세 국가(JP, PH): 관세+VAT 모두 0
            # 그 외 국가(GB, ID, SG, MY): 관세만 면제, VAT는 부과
            if country_code not in _FULL_EXEMPTION_COUNTRIES and config.vat_rate > Decimal('0'):
                vat = goods_value_local * config.vat_rate
        else:
            # CIF 기준 관세 계산 (상품가 + 배송비 포함)
            cif_value = goods_value_local + shipping_cost_local
            duty = cif_value * config.duty_rate

            # VAT 과세표준: vat_on_shipping 여부에 따라 배송비 포함/미포함
            if config.vat_on_shipping:
                vat_base = goods_value_local + shipping_cost_local + duty
            else:
                vat_base = goods_value_local + duty
            vat = vat_base * config.vat_rate

        total_tax = duty + vat
        total_landed = goods_value_local + shipping_cost_local + total_tax

        return {
            'country': country_code,
            'goods_value_local': goods_value_local,
            'shipping_cost_local': shipping_cost_local,
            'de_minimis_exempt': de_minimis_exempt,
            'duty': duty,
            'vat': vat,
            'total_tax': total_tax,
            'total_landed': total_landed,
            'incoterms': config.incoterms,
            'notes': config.notes,
            'breakdown': {
                'duty_rate': config.duty_rate,
                'vat_rate': config.vat_rate,
                'de_minimis': config.de_minimis,
                'de_minimis_currency': config.de_minimis_currency,
                'currency': config.currency,
                'vat_on_shipping': config.vat_on_shipping,
                'ioss_eligible': config.ioss_eligible,
            },
        }

    def calc_landed_price(
        self,
        country_code: str,
        buy_price: Decimal,
        buy_currency: str,
        margin_pct: Decimal,
        shipping_cost: Decimal = Decimal('0'),
        fx_rates: dict = None,
        target_currency: str = None,
    ) -> dict:
        """수출 판매가 계산 (구매가 → 세금 포함 → 마진 적용 → 목적국 통화).

        기존 price.py의 calc_landed_cost()는 KRW 수입 전용.
        이 함수는 해외 판매(수출) 시 목적국 소비자가 내야 할 총 비용 계산.

        Args:
            country_code: 목적국 ISO alpha-2 코드
            buy_price: 구매가 (buy_currency 기준)
            buy_currency: 구매 통화
            margin_pct: 마진율 (%, 예: 30 = 30%)
            shipping_cost: 배송비 (buy_currency 기준)
            fx_rates: 환율 딕셔너리. None이면 빈 딕셔너리.
            target_currency: 목표 통화. None이면 목적국 통화 사용.

        Returns:
            {
                'sell_price': Decimal,           # 마진 적용 판매가 (target_currency)
                'tax_inclusive_price': Decimal,  # 세금 포함가 (DDP 시)
                'tax_detail': dict,              # calc_import_tax() 결과
                'margin_amount': Decimal,
                'fx_rate_used': dict,
            }
        """
        if fx_rates is None:
            fx_rates = {}

        buy_price = Decimal(str(buy_price))
        shipping_cost = Decimal(str(shipping_cost))
        margin_pct = Decimal(str(margin_pct))

        config = get_country(country_code)
        if target_currency is None:
            target_currency = config.currency

        # 세금 계산 (buy_currency 기준 상품가/배송비 → 현지 통화 환산 포함)
        tax_detail = self.calc_import_tax(
            country_code=country_code,
            goods_value=buy_price,
            goods_currency=buy_currency,
            shipping_cost=shipping_cost,
            fx_rates=fx_rates,
        )

        # 세금 포함 가격 (현지 통화)
        tax_inclusive_local = tax_detail['total_landed']

        # 목표 통화로 환산
        tax_inclusive_price = _convert_currency(
            tax_inclusive_local, config.currency, target_currency, fx_rates
        )

        # 마진 적용
        margin_multiplier = Decimal('1') + margin_pct / Decimal('100')
        sell_price = tax_inclusive_price * margin_multiplier
        margin_amount = sell_price - tax_inclusive_price

        return {
            'sell_price': round(sell_price, 2),
            'tax_inclusive_price': round(tax_inclusive_price, 2),
            'tax_detail': tax_detail,
            'margin_amount': round(margin_amount, 2),
            'fx_rate_used': {k: v for k, v in fx_rates.items()},
        }
