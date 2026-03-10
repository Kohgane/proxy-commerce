import os
from decimal import Decimal

# 기본 환율 (모두 KRW 기준)
DEFAULT_FX_RATES = {
    'USDKRW': Decimal('1350'),
    'JPYKRW': Decimal('9.0'),
    'EURKRW': Decimal('1470'),
}

# FXCache를 최상위에서 임포트하여 테스트 시 패치 가능하게 함
# fx 패키지가 설치돼 있지 않은 환경(테스트 격리)에서도 안전하게 로드
try:
    from .fx.cache import FXCache
except Exception:  # ImportError / 순환 참조 방어
    FXCache = None


def _build_fx_rates(fx_usdkrw=None, fx_jpykrw=None, fx_eurkrw=None, use_live=None):
    """환율 딕셔너리를 생성한다.

    우선순위:
    1) 파라미터 직접 지정
    2) use_live=True이면 FXCache에서 실시간 환율 (FX_USE_LIVE 환경변수로도 제어)
    3) 환경변수 (FX_USDKRW 등)
    4) DEFAULT_FX_RATES 기본값
    """
    # use_live 기본값: FX_USE_LIVE 환경변수 확인
    if use_live is None:
        use_live = os.getenv('FX_USE_LIVE', '0') == '1'

    # 파라미터가 모두 지정된 경우 바로 반환 (최우선)
    if fx_usdkrw is not None and fx_jpykrw is not None and fx_eurkrw is not None:
        return {
            'USDKRW': Decimal(str(fx_usdkrw)),
            'JPYKRW': Decimal(str(fx_jpykrw)),
            'EURKRW': Decimal(str(fx_eurkrw)),
        }

    # use_live=True: FXCache에서 실시간 환율 시도
    if use_live:
        try:
            if FXCache is not None:
                cache = FXCache()
                cached = cache.get()
                if cached:
                    return {
                        'USDKRW': (
                            Decimal(str(fx_usdkrw)) if fx_usdkrw is not None
                            else Decimal(str(cached['USDKRW']))
                        ),
                        'JPYKRW': (
                            Decimal(str(fx_jpykrw)) if fx_jpykrw is not None
                            else Decimal(str(cached['JPYKRW']))
                        ),
                        'EURKRW': (
                            Decimal(str(fx_eurkrw)) if fx_eurkrw is not None
                            else Decimal(str(cached['EURKRW']))
                        ),
                    }
        except Exception:
            pass  # 캐시 실패 시 환경변수 폴백

    return {
        'USDKRW': (
            Decimal(str(fx_usdkrw)) if fx_usdkrw is not None
            else Decimal(os.getenv('FX_USDKRW', str(DEFAULT_FX_RATES['USDKRW'])))
        ),
        'JPYKRW': (
            Decimal(str(fx_jpykrw)) if fx_jpykrw is not None
            else Decimal(os.getenv('FX_JPYKRW', str(DEFAULT_FX_RATES['JPYKRW'])))
        ),
        'EURKRW': (
            Decimal(str(fx_eurkrw)) if fx_eurkrw is not None
            else Decimal(os.getenv('FX_EURKRW', str(DEFAULT_FX_RATES['EURKRW'])))
        ),
    }


def _to_krw(amount, currency, fx_rates):
    """임의 통화를 KRW로 환산한다."""
    if currency == 'KRW':
        return amount
    key = f'{currency}KRW'
    if key not in fx_rates:
        raise ValueError(f'지원하지 않는 통화: {currency}')
    return amount * fx_rates[key]


def _from_krw(amount_krw, currency, fx_rates):
    """KRW를 임의 통화로 환산한다."""
    if currency == 'KRW':
        return amount_krw
    key = f'{currency}KRW'
    if key not in fx_rates:
        raise ValueError(f'지원하지 않는 통화: {currency}')
    return amount_krw / fx_rates[key]


def calc_price(buy_price, buy_currency, fx_usdkrw, margin_pct, target_currency,
               fx_rates=None):
    """구매가를 목표 통화로 환산하고 마진을 적용한 판매가를 반환한다.

    기존 호출 시그니처(buy_price, buy_currency, fx_usdkrw, margin_pct,
    target_currency)를 그대로 지원하며, 추가로 fx_rates 딕셔너리를
    키워드 인수로 받아 다중통화 환산에 사용한다.
    """
    buy = Decimal(str(buy_price))

    # fx_rates가 없으면 fx_usdkrw 값을 기준으로 생성 (하위호환)
    if fx_rates is None:
        fx_rates = _build_fx_rates(fx_usdkrw=fx_usdkrw)

    base = _from_krw(_to_krw(buy, buy_currency, fx_rates), target_currency, fx_rates)
    sell = base * (Decimal('1') + Decimal(str(margin_pct)) / Decimal('100'))
    return round(sell, 2)


def calc_landed_cost(buy_price, buy_currency, margin_pct, fx_rates=None,
                     forwarder_fee=None, shipping_fee=None, customs_rate=None,
                     customs_threshold_krw=None):
    """구매대행 최종 판매가(KRW)를 계산한다.

    최종 판매가 =
        (원가 KRW 환산 + 배대지 수수료 KRW 환산 + 국제배송비)
        × (1 + 관부가세율)
        × (1 + 마진율)

    Args:
        buy_price: 구매가
        buy_currency: 구매 통화 ('KRW', 'USD', 'JPY', 'EUR')
        margin_pct: 마진율 (%)
        fx_rates: 환율 딕셔너리. None이면 환경변수에서 읽음.
        forwarder_fee: 배대지(젠마켓 등) 수수료 (JPY). None이면 환경변수 FORWARDER_FEE_JPY 사용.
        shipping_fee: 국제배송비 (KRW). None이면 환경변수 SHIPPING_FEE_DEFAULT 사용.
        customs_rate: 관부가세율. None이면 원가 KRW 환산액이 customs_threshold_krw 초과 시 자동 적용.
        customs_threshold_krw: 관부가세 면세 기준액 (KRW). None이면 환경변수 CUSTOMS_THRESHOLD_KRW 사용.
    """
    if fx_rates is None:
        fx_rates = _build_fx_rates()

    buy = Decimal(str(buy_price))

    # 배대지 수수료 기본값 (JPY)
    if forwarder_fee is None:
        forwarder_fee = Decimal(os.getenv('FORWARDER_FEE_JPY', '300'))
    forwarder_fee = Decimal(str(forwarder_fee))

    # 국제배송비 기본값 (KRW)
    if shipping_fee is None:
        shipping_fee = Decimal(os.getenv('SHIPPING_FEE_DEFAULT', '12000'))
    shipping_fee = Decimal(str(shipping_fee))

    # 관부가세 면세 기준액
    if customs_threshold_krw is None:
        customs_threshold_krw = Decimal(os.getenv('CUSTOMS_THRESHOLD_KRW', '150000'))
    customs_threshold_krw = Decimal(str(customs_threshold_krw))

    # 원가 KRW 환산
    cost_krw = _to_krw(buy, buy_currency, fx_rates)

    # 배대지 수수료 KRW 환산 (JPY 기준)
    forwarder_fee_krw = _to_krw(forwarder_fee, 'JPY', fx_rates)

    total_before_customs = cost_krw + forwarder_fee_krw + shipping_fee

    # 관부가세율 결정
    if customs_rate is None:
        if cost_krw > customs_threshold_krw:
            customs_rate = Decimal(os.getenv('CUSTOMS_RATE_DEFAULT', '0.20'))
        else:
            customs_rate = Decimal('0')
    customs_rate = Decimal(str(customs_rate))

    total_after_customs = total_before_customs * (Decimal('1') + customs_rate)
    sell = total_after_customs * (Decimal('1') + Decimal(str(margin_pct)) / Decimal('100'))
    return round(sell, 2)
