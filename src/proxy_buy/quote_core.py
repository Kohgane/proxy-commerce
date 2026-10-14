"""견적 계산 코어 — 순수 함수, 네트워크 없음.

가격 = (상품가 + 국내배송비) x 1.12, 마진 최소 $6, + 국제배송비.
PG 적립 = (소계 + 0.30) / (1 - 0.044)  (PayPal 4.4% + $0.30).
관세는 합계에 넣지 않고 '예상치' 별도 줄로만 보여준다.
출력 문구에는 '수수료/대행/service fee'를 쓰지 않는다 (판매 + 수출 구조).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

MARGIN_RATE = Decimal("0.12")
MIN_MARGIN_USD = Decimal("6")
PG_RATE = Decimal("0.044")
PG_FIXED = Decimal("0.30")
FIRST_ORDER_CAP_USD = Decimal("500")

# 배송 불가 7개 범주 (키워드, 소문자/한글 부분일치)
PROHIBITED = {
    "식품·건기식": ["식품", "건강기능", "영양제", "비타민", "supplement", "food"],
    "의약품": ["의약", "처방", "medicine", "drug"],
    "화장품(액체·분무)": ["스프레이", "향수", "perfume", "aerosol"],
    "전자담배·담배": ["담배", "vape", "tobacco"],
    "주류": ["주류", "소주", "와인", "alcohol", "liquor"],
    "가스·연료·배터리류": ["가스", "부탄", "연료", "fuel", "gas canister", "보조배터리"],
    "무기·위조품": ["총기", "비비탄", "칼날", "replica", "fake", "짝퉁", "레플리카"],
}

_BANNED_WORDS = ("service fee", "수수료", "대행")


def _d(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _q(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def find_prohibited(text: str) -> List[str]:
    t = (text or "").lower()
    return [cat for cat, kws in PROHIBITED.items() if any(k in t for k in kws)]


@dataclass
class Quote:
    item_usd: Decimal
    kr_ship_usd: Decimal
    margin_usd: Decimal
    intl_ship_usd: Decimal
    payment_cost_usd: Decimal
    total_usd: Decimal
    duty_estimate_usd: Optional[Decimal]
    fx_krw_per_usd: Decimal
    blocked: List[str] = field(default_factory=list)
    over_cap: bool = False

    @property
    def ok(self) -> bool:
        return not self.blocked and not self.over_cap

    def lines(self) -> List[str]:
        """구매자 노출용 문구 (금지어 없음)."""
        out = [
            f"Item (Korean retail price): ${self.item_usd}",
            f"Korea domestic delivery: ${self.kr_ship_usd}",
            f"Sourcing & handling: ${self.margin_usd}",
            f"International shipping: ${self.intl_ship_usd}",
            f"Payment processing: ${self.payment_cost_usd}",
            f"Total: ${self.total_usd}",
        ]
        if self.duty_estimate_usd is not None:
            out.append(f"Estimated import duty/tax (not included, set by your customs): ~${self.duty_estimate_usd}")
        assert not any(b in " ".join(out).lower() for b in _BANNED_WORDS)
        return out


def build_quote(
    item_krw,
    kr_ship_krw,
    intl_ship_usd,
    fx_krw_per_usd,
    title: str = "",
    duty_rate=None,
) -> Quote:
    fx = _d(fx_krw_per_usd)
    if fx <= 0:
        raise ValueError("fx must be positive")
    item = _d(item_krw) / fx
    kr = _d(kr_ship_krw) / fx
    base = item + kr
    margin = max(base * MARGIN_RATE, MIN_MARGIN_USD)
    intl = _d(intl_ship_usd)
    subtotal = base + margin + intl
    total = (subtotal + PG_FIXED) / (1 - PG_RATE)
    pg = total - subtotal
    duty = _q((item + intl) * _d(duty_rate)) if duty_rate is not None else None
    q = Quote(
        item_usd=_q(item), kr_ship_usd=_q(kr), margin_usd=_q(margin),
        intl_ship_usd=_q(intl), payment_cost_usd=_q(pg), total_usd=_q(total),
        duty_estimate_usd=duty, fx_krw_per_usd=fx,
        blocked=find_prohibited(title), over_cap=total > FIRST_ORDER_CAP_USD,
    )
    return q
