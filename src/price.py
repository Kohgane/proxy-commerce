"""src/price.py — 판매가 산정.

## ★★ 목표 마진율은 **실수령 마진(net margin)**이다 (오너 결정 2026-09-20)

예전 식은 **markup**이었다 — 원가 위에 비율을 얹었다. 그래서 「마진 25%」로 올린 상품이
쿠팡 수수료 10.8%와 국내배송 ₩3,000을 빼고 나면 **한참 적게 남았고**, 어떤 건은 적자였다.
볼트 [[가격 정책 — 실마진 기준]]이 재 둔 그대로다: **명목만 보고 흑자로 집계된 건들이
실제로는 적자였다.**

오너 결정: **볼트 정책을 따른다(코드를 고친다).**

    판매가 = ((원가KRW + 배대지수수료 + 국제배송비) × (1 + 관부가세율) + 국내배송비)
             ÷ (1 − 마켓수수료율 − 목표마진율)

이 식의 뜻은 하나다 — **판매가에서 수수료와 배송을 빼면 정확히 목표마진이 남는다.**

    (판매가 − 판매가×마켓수수료율 − 랜딩코스트 − 국내배송비) ÷ 판매가 == 목표마진율

## ★ 마켓수수료율을 모르면 **등록하지 않는다**

마켓마다 다르고, **모르면 지어내지 않는다**(오너 지시). 지금 값이 있는 건 쿠팡뿐이다 —
볼트가 실측해 둔 10.8%. 나머지는 오너가 `MARKET_COMMISSION_PCT_<마켓>`으로 넣어야
그 마켓에 등록된다. 짐작한 수수료로 가격을 매기면 **틀린 값으로 파는 것**이고,
그건 빈칸보다 나쁘다.
"""
import os
from decimal import Decimal

# 기본 환율 (모두 KRW 기준)
DEFAULT_FX_RATES = {
    'USDKRW': Decimal('1350'),
    'JPYKRW': Decimal('9.0'),
    'EURKRW': Decimal('1470'),
    'CNYKRW': Decimal('185'),   # 위안화 (타오바오/1688)
}

# FXCache를 최상위에서 임포트하여 테스트 시 패치 가능하게 함
# fx 패키지가 설치돼 있지 않은 환경(테스트 격리)에서도 안전하게 로드
try:
    from .fx.cache import FXCache
except Exception:  # ImportError / 순환 참조 방어
    FXCache = None


def _build_fx_rates(fx_usdkrw=None, fx_jpykrw=None, fx_eurkrw=None, fx_cnykrw=None, use_live=None):
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
        rates = {
            'USDKRW': Decimal(str(fx_usdkrw)),
            'JPYKRW': Decimal(str(fx_jpykrw)),
            'EURKRW': Decimal(str(fx_eurkrw)),
        }
        if fx_cnykrw is not None:
            rates['CNYKRW'] = Decimal(str(fx_cnykrw))
        else:
            rates['CNYKRW'] = Decimal(os.getenv('FX_CNYKRW', str(DEFAULT_FX_RATES['CNYKRW'])))
        return rates

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
                        'CNYKRW': (
                            Decimal(str(fx_cnykrw)) if fx_cnykrw is not None
                            else Decimal(str(cached.get('CNYKRW', DEFAULT_FX_RATES['CNYKRW'])))
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
        'CNYKRW': (
            Decimal(str(fx_cnykrw)) if fx_cnykrw is not None
            else Decimal(os.getenv('FX_CNYKRW', str(DEFAULT_FX_RATES['CNYKRW'])))
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


class PricingError(ValueError):
    """판매가를 **정할 수 없다**. 호출부는 등록을 보류한다(원가 폴백 금지)."""


# ── 마켓 판매수수료 (%) ──────────────────────────────────────────────────────
#
# ★ **실측값만 적는다.** 짐작한 수수료로 가격을 매기면 틀린 값으로 파는 것이다.
#   쿠팡 10.8% = 볼트 [[가격 정책 — 실마진 기준]] 실측(2026-09-04).
#   나머지 마켓은 **비어 있는 게 맞다** — 오너가 실측해 env로 넣으면 그때 등록된다.
#
#   ※ `src/channels/percenty.py`의 `MARKET_PRICE_POLICY`에도 수수료 숫자가 있지만
#     (smartstore 5.0·11st 12.0) **출처가 적혀 있지 않다.** 실측이라는 근거가 없는 값을
#     판매가 산정에 끌어다 쓰지 않는다 — 그게 「숫자가 있으니 맞겠지」의 시작이다.
MEASURED_COMMISSION_PCT = {
    "coupang": Decimal("10.8"),
}

# 마켓별 코드 별칭 — 한 마켓이 두 이름으로 불리면 한쪽만 고쳐진다.
_MARKET_ALIASES = {
    "11st": "elevenst",
    "naver": "smartstore",
    "naver_commerce": "smartstore",
    "kohganemultishop": "woocommerce",
    "woo": "woocommerce",
}


def _market_key(market) -> str:
    key = str(market or "").strip().lower()
    return _MARKET_ALIASES.get(key, key)


def commission_pct(market):
    """`(수수료율 %, 사유)` — 모르면 `(None, 사유)`.

    우선순위: `MARKET_COMMISSION_PCT_<마켓>` 환경변수 → 실측 상수.
    **기본값은 없다.** 모르는 채로 0%를 쓰면 수수료만큼 그대로 손해다.
    """
    key = _market_key(market)
    if not key:
        return None, "마켓을 알 수 없어 판매수수료를 적용하지 못했습니다"
    env = os.getenv(f"MARKET_COMMISSION_PCT_{key.upper()}")
    if env is not None and str(env).strip() != "":
        try:
            return Decimal(str(env).strip()), ""
        except Exception:
            return None, f"MARKET_COMMISSION_PCT_{key.upper()} 값을 숫자로 읽지 못했습니다: {env!r}"
    if key in MEASURED_COMMISSION_PCT:
        return MEASURED_COMMISSION_PCT[key], ""
    return None, (f"{key} 판매수수료율이 없습니다 — 실측값을 "
                  f"MARKET_COMMISSION_PCT_{key.upper()}에 넣어 주세요"
                  " (짐작한 수수료로 가격을 매기지 않습니다)")


def domestic_shipping_krw(market=None) -> Decimal:
    """국내배송비(KRW). 마켓별로 다르면 `DOMESTIC_SHIPPING_FEE_KRW_<마켓>`."""
    key = _market_key(market)
    if key:
        per = os.getenv(f"DOMESTIC_SHIPPING_FEE_KRW_{key.upper()}")
        if per is not None and str(per).strip() != "":
            return Decimal(str(per).strip())
    return Decimal(os.getenv("DOMESTIC_SHIPPING_FEE_KRW", "3000"))


def landed_cost_krw(buy_price, buy_currency, fx_rates=None, forwarder_fee=None,
                    shipping_fee=None, customs_rate=None, customs_threshold_krw=None):
    """**우리가 치르는 돈**(KRW) — 마진도 마켓수수료도 없다.

        (원가KRW + 배대지수수료KRW + 국제배송비) × (1 + 관부가세율)

    판매가 산정(`calc_sell_price`)과 마진 판정이 **같은 이 값**을 본다 —
    원가가 두 벌이면 한쪽 기준으로만 흑자다.
    """
    if fx_rates is None:
        fx_rates = _build_fx_rates()

    buy = Decimal(str(buy_price))

    if forwarder_fee is None:
        forwarder_fee = Decimal(os.getenv('FORWARDER_FEE_JPY', '300'))
    forwarder_fee = Decimal(str(forwarder_fee))

    if shipping_fee is None:
        shipping_fee = Decimal(os.getenv('SHIPPING_FEE_DEFAULT', '12000'))
    shipping_fee = Decimal(str(shipping_fee))

    if customs_threshold_krw is None:
        customs_threshold_krw = Decimal(os.getenv('CUSTOMS_THRESHOLD_KRW', '150000'))
    customs_threshold_krw = Decimal(str(customs_threshold_krw))

    cost_krw = _to_krw(buy, buy_currency, fx_rates)
    forwarder_fee_krw = _to_krw(forwarder_fee, 'JPY', fx_rates)

    if customs_rate is None:
        if cost_krw > customs_threshold_krw:
            customs_rate = Decimal(os.getenv('CUSTOMS_RATE_DEFAULT', '0.20'))
        else:
            customs_rate = Decimal('0')
    customs_rate = Decimal(str(customs_rate))

    return (cost_krw + forwarder_fee_krw + shipping_fee) * (Decimal('1') + customs_rate)


def net_margin_pct(sell_price_krw, landed_krw, market, domestic_shipping=None,
                   commission=None):
    """그 판매가로 팔면 **실제로 남는 비율**(%). 수수료율을 모르면 `None`.

    판정과 산정이 **같은 식**을 본다 — 이 함수가 `calc_sell_price`의 역이다.
    """
    sell = Decimal(str(sell_price_krw))
    if sell <= 0:
        return None
    if commission is None:
        commission, _why = commission_pct(market)
        if commission is None:
            return None
    commission = Decimal(str(commission))
    ship = (domestic_shipping_krw(market) if domestic_shipping is None
            else Decimal(str(domestic_shipping)))
    net = sell - (sell * commission / Decimal('100')) - Decimal(str(landed_krw)) - ship
    return net / sell * Decimal('100')


def calc_sell_price(buy_price, buy_currency, market, margin_pct, fx_rates=None,
                    forwarder_fee=None, shipping_fee=None, customs_rate=None,
                    customs_threshold_krw=None, domestic_shipping=None,
                    commission=None):
    """**실수령 마진 기준** 판매가(KRW). 오너 결정 2026-09-20 · 볼트 정책.

        판매가 = (랜딩코스트 + 국내배송비) ÷ (1 − 마켓수수료율 − 목표마진율)

    `margin_pct`는 **남는 비율**이다(원가 위에 얹는 비율이 아니다).
    판매가에서 수수료·배송을 빼면 **정확히 그 비율**이 남는다.

    수수료율을 모르면 `PricingError`다 — **짐작해서 팔지 않는다.**
    분모가 0 이하(마진+수수료 ≥ 100%)여도 `PricingError`다 — 그 목표는 불가능하다.
    """
    landed = landed_cost_krw(buy_price, buy_currency, fx_rates=fx_rates,
                             forwarder_fee=forwarder_fee, shipping_fee=shipping_fee,
                             customs_rate=customs_rate,
                             customs_threshold_krw=customs_threshold_krw)
    if commission is None:
        commission, why = commission_pct(market)
        if commission is None:
            raise PricingError(why)
    commission = Decimal(str(commission))
    margin = Decimal(str(margin_pct))
    denom = (Decimal('100') - commission - margin) / Decimal('100')
    if denom <= 0:
        raise PricingError(
            f"목표 마진율({margin}%)과 판매수수료율({commission}%)의 합이 100% 이상입니다 — "
            "이 목표로는 판매가가 나오지 않습니다")
    ship = (domestic_shipping_krw(market) if domestic_shipping is None
            else Decimal(str(domestic_shipping)))
    return round((landed + ship) / denom, 2)


def reference_market() -> str:
    """마켓이 정해지기 **전에** 값을 보여 줘야 하는 자리(수집 초안·카탈로그 내보내기)가
    쓰는 기준 마켓.

    기본은 쿠팡 — **수수료가 실측된 유일한 마켓**이고 우리 주력이다. 이건 짐작이 아니라
    「어느 마켓 기준으로 보여 주는지」를 고른 것이고, 실제 등록가는 **등록 시점에 그 마켓
    수수료로 다시 난다.** 바꾸려면 `PRICING_REFERENCE_MARKET`.
    """
    return os.getenv("PRICING_REFERENCE_MARKET", "coupang")


def calc_landed_cost(buy_price, buy_currency, margin_pct, fx_rates=None,
                     forwarder_fee=None, shipping_fee=None, customs_rate=None,
                     customs_threshold_krw=None, market=None):
    """(옛 이름) 판매가 — 이제 **실수령 마진 기준**이다.

    ⚠️ 2026-09-20 전까지 이 함수는 **markup**이었다:
    `(랜딩코스트) × (1 + 마진율)`. 마켓수수료도 국내배송비도 없었다.
    오너 결정으로 식이 바뀌었다 — `calc_sell_price`를 그대로 부른다.
    **이름은 남겨 둔다**(호출부가 여럿) 지만 새 코드는 `calc_sell_price`를 쓴다.

    `market`을 안 주면 `reference_market()`(쿠팡) 기준이다.
    """
    return calc_sell_price(
        buy_price, buy_currency, market or reference_market(), margin_pct,
        fx_rates=fx_rates, forwarder_fee=forwarder_fee, shipping_fee=shipping_fee,
        customs_rate=customs_rate, customs_threshold_krw=customs_threshold_krw)
