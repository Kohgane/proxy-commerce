"""src/seller_console/margin_calculator.py

셀러용 실시간 마진 계산기 (Phase 125).
- 매입가 → 환산 → 운송/관세/마켓수수료/PG수수료 → 판매가 → 실 마진
- 시나리오 비교 (쿠팡 vs 스마트스토어 vs 11번가 vs 코가네멀티샵 vs Shopify)
- 환율 실시간 또는 수동
- 목표 마진 역산 → 권장 판매가
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

Currency = Literal["KRW", "USD", "JPY", "EUR", "CNY"]
Marketplace = Literal["coupang", "smartstore", "11st", "kohganemultishop", "shopify"]

# ──────────────────────────────────────────────────────────
# 기본 환율 폴백 (환경변수 → 하드코딩 기본값)
# ──────────────────────────────────────────────────────────

_DEFAULT_FX: Dict[str, Decimal] = {
    "USD": Decimal(os.getenv("FX_USDKRW", "1370")),
    "JPY": Decimal(os.getenv("FX_JPYKRW", "9.12")),
    "EUR": Decimal(os.getenv("FX_EURKRW", "1485")),
    "CNY": Decimal(os.getenv("FX_CNYKRW", "188")),
    "KRW": Decimal("1"),
}

# 자체몰/Shopify 기본 수수료 (MARKET_PRICE_POLICY 미포함 마켓)
_DEFAULT_COMMISSION: Dict[str, Decimal] = {
    "kohganemultishop": Decimal("3"),   # 자체몰 결제 수수료 수준
    "shopify": Decimal("2"),            # Shopify Payments 기본
}

# 자체몰/Shopify 기본 PG 수수료율 (외부 결제 게이트웨이 사용 시 적용)
_DEFAULT_PG_FEE: Decimal = Decimal("3.3")

# ──────────────────────────────────────────────────────────
# Graceful imports
# ──────────────────────────────────────────────────────────

try:
    from src.price import calc_landed_cost as _calc_landed_cost  # type: ignore
except ImportError:
    _calc_landed_cost = None  # 폴백 사용

try:
    from src.fx.provider import FXProvider as _FXProvider  # type: ignore
    _HAS_FX_PROVIDER = True
except ImportError:
    _FXProvider = None  # type: ignore
    _HAS_FX_PROVIDER = False

_FX_DISABLE_NETWORK = os.getenv("FX_DISABLE_NETWORK", "0") == "1"


def _load_fx_rates() -> Dict[str, Decimal]:
    """실시간 또는 환경변수 폴백 환율 조회.

    FXProvider 사용 가능 + 네트워크 활성화 시 실시간.
    그 외엔 환경변수 → 기본값.
    """
    if _HAS_FX_PROVIDER and not _FX_DISABLE_NETWORK:
        try:
            provider = _FXProvider()  # type: ignore[misc]
            rates = provider.get_rates()
            result = dict(_DEFAULT_FX)
            for pair, val in rates.items():
                if pair == "USDKRW":
                    result["USD"] = Decimal(str(val))
                elif pair == "JPYKRW":
                    result["JPY"] = Decimal(str(val))
                elif pair == "EURKRW":
                    result["EUR"] = Decimal(str(val))
                elif pair == "CNYKRW":
                    result["CNY"] = Decimal(str(val))
            result["_source"] = "realtime"
            return result
        except Exception as exc:
            logger.warning("FXProvider 오류, 환경변수 폴백 사용: %s", exc)

    result = dict(_DEFAULT_FX)
    result["_source"] = "env" if any(
        os.getenv(k) for k in ("FX_USDKRW", "FX_JPYKRW", "FX_EURKRW", "FX_CNYKRW")
    ) else "default"
    return result


def default_commission_rate(marketplace: Marketplace) -> Decimal:
    """마켓별 기본 수수료율 반환.

    src.channels.percenty.MARKET_PRICE_POLICY 우선,
    미정의 마켓(자체몰/Shopify)은 _DEFAULT_COMMISSION 사용.
    """
    try:
        from src.channels.percenty import MARKET_PRICE_POLICY  # type: ignore
        if marketplace in MARKET_PRICE_POLICY:
            return Decimal(str(MARKET_PRICE_POLICY[marketplace]["commission_rate"]))
    except ImportError:
        pass

    return _DEFAULT_COMMISSION.get(marketplace, Decimal("10"))


# ──────────────────────────────────────────────────────────
# 데이터 클래스
# ──────────────────────────────────────────────────────────

@dataclass
class CostInput:
    """매입가 + 부대비용 입력."""

    buy_price: Decimal
    buy_currency: Currency
    qty: int = 1
    forwarder_fee: Decimal = Decimal("0")           # 배대지 수수료 (KRW)
    international_shipping: Decimal = Decimal("0")  # 국제 배송비 (KRW)
    domestic_shipping: Decimal = Decimal("0")       # 국내 배송비 (KRW)
    customs_rate: Decimal = Decimal("0.20")         # 관세율 (소수: 0.20 = 20%)
    customs_threshold_krw: Decimal = Decimal("150000")  # 면세 임계 (KRW)
    fx_override: Optional[Decimal] = None           # None = 실시간 환율


@dataclass
class MarketInput:
    """마켓별 수수료 입력."""

    marketplace: Marketplace
    commission_rate: Decimal                        # 마켓 수수료율 (%)
    pg_fee_rate: Decimal = Decimal("0")             # PG 수수료율 (%, 자체몰/Shopify 등)
    extra_fees: Decimal = Decimal("0")              # 기타 추가 수수료 (KRW)
    target_margin_pct: Decimal = Decimal("22")      # 목표 마진율 (%)


@dataclass
class MarginResult:
    """마진 계산 결과."""

    marketplace: Marketplace
    cost_in_krw: Decimal            # 매입가 KRW 환산
    customs_in_krw: Decimal         # 관부가세 (KRW)
    total_landed_cost: Decimal      # 총 랜딩 코스트 (매입 + 관세 + 배송)
    recommended_price: Decimal      # 목표 마진 만족하는 권장 판매가
    given_price: Optional[Decimal]  # 사용자 직접 입력 가격 (있을 때)
    actual_margin_krw: Decimal      # 실 마진 (KRW)
    actual_margin_pct: Decimal      # 실 마진율 (%)
    breakeven_price: Decimal        # 손익분기점 판매가
    fx_used: Dict[str, str]         # {"source": "realtime", "USD": "1370"}
    warnings: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────
# 계산기 코어
# ──────────────────────────────────────────────────────────

class MarginCalculator:
    """셀러용 마진 계산기."""

    # 마켓별 레이블
    MARKETPLACE_LABELS: Dict[str, str] = {
        "coupang": "쿠팡",
        "smartstore": "스마트스토어",
        "11st": "11번가",
        "kohganemultishop": "코가네멀티샵",
        "shopify": "Shopify",
    }

    def __init__(self, fx_provider=None):
        """fx_provider: FXProvider 인스턴스(의존성 주입). None이면 lazy init."""
        self._fx_provider = fx_provider

    # ── 공개 API ──────────────────────────────────────────

    def calculate(
        self,
        cost: CostInput,
        market: MarketInput,
        sell_price: Optional[Decimal] = None,
    ) -> MarginResult:
        """단일 마켓 마진 계산.

        sell_price=None: 목표 마진 역산으로 권장 판매가 계산.
        sell_price 지정: 해당 가격에서의 실 마진 계산.
        """
        fx_rates = self._fetch_fx(cost.buy_currency, cost.fx_override)
        fx_rate = fx_rates["rate"]

        # 1. 매입가 KRW 환산
        cost_in_krw = (cost.buy_price * Decimal(str(cost.qty)) * fx_rate).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )

        # 2. 관부가세 계산 (면세 임계 초과 시)
        customs_in_krw = Decimal("0")
        warnings: List[str] = []
        if cost_in_krw > cost.customs_threshold_krw:
            customs_in_krw = (cost_in_krw * cost.customs_rate).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        else:
            if cost.customs_rate > Decimal("0"):
                warnings.append(
                    f"매입가(₩{cost_in_krw:,})가 면세 임계(₩{cost.customs_threshold_krw:,}) 이하 → 관세 면제"
                )

        # 3. 총 랜딩 코스트
        total_landed_cost = (
            cost_in_krw
            + customs_in_krw
            + cost.forwarder_fee
            + cost.international_shipping
            + cost.domestic_shipping
            + market.extra_fees
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        # 4. 수수료율 합계 (소수로 변환)
        total_fee_rate = (market.commission_rate + market.pg_fee_rate) / Decimal("100")

        if total_fee_rate >= Decimal("1"):
            warnings.append("수수료 합계가 100% 이상입니다. 수수료율을 확인하세요.")
            total_fee_rate = Decimal("0.99")

        # 5. 판매가 및 마진 계산
        if sell_price is not None:
            # 직접 지정된 판매가로 실 마진 계산
            given_price = sell_price.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            recommended_price = self._reverse_price(total_landed_cost, total_fee_rate, market.target_margin_pct)
            actual_margin_krw, actual_margin_pct = self._calc_margin(
                given_price, total_landed_cost, total_fee_rate
            )
            breakeven_price = self._calc_breakeven(total_landed_cost, total_fee_rate)
        else:
            # 목표 마진 역산
            recommended_price = self._reverse_price(total_landed_cost, total_fee_rate, market.target_margin_pct)
            given_price = None
            actual_margin_krw, actual_margin_pct = self._calc_margin(
                recommended_price, total_landed_cost, total_fee_rate
            )
            breakeven_price = self._calc_breakeven(total_landed_cost, total_fee_rate)

        # 낮은 마진 경고
        if actual_margin_pct < Decimal("5"):
            warnings.append(f"실 마진율({actual_margin_pct:.1f}%)이 5% 미만입니다.")

        return MarginResult(
            marketplace=market.marketplace,
            cost_in_krw=cost_in_krw,
            customs_in_krw=customs_in_krw,
            total_landed_cost=total_landed_cost,
            recommended_price=recommended_price,
            given_price=given_price,
            actual_margin_krw=actual_margin_krw,
            actual_margin_pct=actual_margin_pct,
            breakeven_price=breakeven_price,
            fx_used=fx_rates["info"],
            warnings=warnings,
        )

    def compare_marketplaces(
        self,
        cost: CostInput,
        marketplaces: List[Marketplace],
        sell_price: Optional[Decimal] = None,
    ) -> List[MarginResult]:
        """여러 마켓 동시 비교."""
        results = []
        for mp in marketplaces:
            market = MarketInput(
                marketplace=mp,
                commission_rate=default_commission_rate(mp),
                pg_fee_rate=_DEFAULT_PG_FEE if mp in ("kohganemultishop", "shopify") else Decimal("0"),
            )
            results.append(self.calculate(cost, market, sell_price=sell_price))
        return results

    def reverse_target_price(
        self,
        cost: CostInput,
        market: MarketInput,
    ) -> Decimal:
        """목표 마진을 만족하는 최저 판매가."""
        fx_rates = self._fetch_fx(cost.buy_currency, cost.fx_override)
        fx_rate = fx_rates["rate"]

        cost_in_krw = (cost.buy_price * Decimal(str(cost.qty)) * fx_rate).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        customs_in_krw = Decimal("0")
        if cost_in_krw > cost.customs_threshold_krw:
            customs_in_krw = (cost_in_krw * cost.customs_rate).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )

        total_landed_cost = (
            cost_in_krw
            + customs_in_krw
            + cost.forwarder_fee
            + cost.international_shipping
            + cost.domestic_shipping
            + market.extra_fees
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        total_fee_rate = (market.commission_rate + market.pg_fee_rate) / Decimal("100")
        if total_fee_rate >= Decimal("1"):
            total_fee_rate = Decimal("0.99")

        return self._reverse_price(total_landed_cost, total_fee_rate, market.target_margin_pct)

    # ── 내부 헬퍼 ─────────────────────────────────────────

    def _fetch_fx(
        self,
        currency: Currency,
        fx_override: Optional[Decimal],
    ) -> Dict:
        """환율 조회. fx_override 지정 시 수동 환율 사용."""
        if currency == "KRW":
            return {
                "rate": Decimal("1"),
                "info": {"source": "n/a", "KRW": "1"},
            }

        if fx_override is not None:
            return {
                "rate": fx_override,
                "info": {"source": "manual", currency: str(fx_override)},
            }

        if self._fx_provider is not None:
            try:
                rates = self._fx_provider.get_rates()
                pair = f"{currency}KRW"
                if pair in rates:
                    rate = Decimal(str(rates[pair]))
                    return {
                        "rate": rate,
                        "info": {
                            "source": rates.get("provider", "injected"),
                            currency: str(rate),
                        },
                    }
            except Exception as exc:
                logger.warning("주입된 FXProvider 오류: %s", exc)

        fx_rates = _load_fx_rates()
        rate = fx_rates.get(currency, Decimal("1"))
        return {
            "rate": rate,
            "info": {
                "source": fx_rates.get("_source", "default"),
                currency: str(rate),
            },
        }

    @staticmethod
    def _reverse_price(
        total_landed_cost: Decimal,
        total_fee_rate: Decimal,
        target_margin_pct: Decimal,
    ) -> Decimal:
        """목표 마진율 기준 역산 판매가.

        공식:
          sell = landed_cost / ((1 - fee_rate) * (1 - margin_rate))
        """
        margin_rate = target_margin_pct / Decimal("100")
        denom = (Decimal("1") - total_fee_rate) * (Decimal("1") - margin_rate)
        if denom <= Decimal("0"):
            denom = Decimal("0.01")
        price = total_landed_cost / denom
        # 10원 단위 올림
        return (price / Decimal("10")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal("10")

    @staticmethod
    def _calc_margin(
        sell_price: Decimal,
        total_landed_cost: Decimal,
        total_fee_rate: Decimal,
    ):
        """실 마진(KRW, %) 계산."""
        if sell_price <= Decimal("0"):
            return Decimal("0"), Decimal("0")
        net_revenue = sell_price * (Decimal("1") - total_fee_rate)
        margin_krw = (net_revenue - total_landed_cost).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        margin_pct = (margin_krw / sell_price * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return margin_krw, margin_pct

    @staticmethod
    def _calc_breakeven(
        total_landed_cost: Decimal,
        total_fee_rate: Decimal,
    ) -> Decimal:
        """손익분기점 판매가 (마진 0일 때)."""
        denom = Decimal("1") - total_fee_rate
        if denom <= Decimal("0"):
            denom = Decimal("0.01")
        price = total_landed_cost / denom
        return price.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
