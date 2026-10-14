"""견적 → Shopify 임시 주문(draftOrderCreate). 판매자는 KOHGANE, 문구에 수수료/대행 없음.

합계 한 줄(맞춤 라인아이템) + 증빙용 customAttributes(원본 URL·원화가·환율). 결제 링크는 invoiceUrl.
"""
from __future__ import annotations

from typing import Any, Dict

from .quote_core import FIRST_ORDER_CAP_USD

MUTATION = """
mutation($input: DraftOrderInput!) {
  draftOrderCreate(input: $input) {
    draftOrder { id name invoiceUrl totalPriceSet { shopMoney { amount currencyCode } } }
    userErrors { field message }
  }
}
"""

_BANNED = ("service fee", "수수료", "대행")


def build_input(quote: Dict[str, Any], email: str, src_url: str, shipping_address: Dict[str, str],
                fx: float) -> Dict[str, Any]:
    if quote.get("status") != "quoted":
        raise ValueError("quoted 상태의 견적만 주문으로 만들 수 있다")
    total = str(quote["total_usd"])
    if float(total) > float(FIRST_ORDER_CAP_USD):
        raise ValueError("첫 주문 상한 초과")
    title = f"Korean retail item: {quote['title']}"[:250]
    assert not any(b in title.lower() for b in _BANNED)
    return {
        "email": email,
        "lineItems": [{
            "title": title,
            "quantity": 1,
            "requiresShipping": True,
            "taxable": False,  # 수출 영세율
            "originalUnitPriceWithCurrency": {"amount": total, "currencyCode": "USD"},
            "customAttributes": [{"key": "source_url", "value": src_url}],
        }],
        "shippingLine": {"title": "Included in price", "priceWithCurrency": {"amount": "0.00", "currencyCode": "USD"}},
        "shippingAddress": shipping_address,
        "billingAddress": shipping_address,  # 결제지 = 배송지 원칙
        "tags": ["buy-from-korea", "proxy-order"],
        "note": f"Quote valid 48h. KRW {quote['price_krw']} @ {fx}/USD",
        "customAttributes": [
            {"key": "source_url", "value": src_url},
            {"key": "price_krw", "value": str(quote["price_krw"])},
            {"key": "fx_krw_per_usd", "value": str(fx)},
        ],
    }


def create(quote, email, src_url, shipping_address, fx) -> Dict[str, Any]:
    from src.vendors.shopify_client import graphql_query
    data = graphql_query(MUTATION, {"input": build_input(quote, email, src_url, shipping_address, fx)})
    res = data.get("draftOrderCreate") or {}
    if res.get("userErrors"):
        raise RuntimeError(f"draftOrderCreate 실패: {res['userErrors']}")
    return res["draftOrder"]
