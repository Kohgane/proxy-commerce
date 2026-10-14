import json

import pytest

from src.proxy_buy import draft_order as d

Q = {"status": "quoted", "title": "오버핏 후드", "price_krw": 75000, "total_usd": "100.00"}
ADDR = {"address1": "1 Main St", "city": "Austin", "provinceCode": "TX", "countryCode": "US", "zip": "78701"}


def test_build_input_shape_and_wording():
    i = d.build_input(Q, "a@b.com", "https://www.musinsa.com/p/1", ADDR, 1020.0)
    li = i["lineItems"][0]
    assert li["originalUnitPriceWithCurrency"] == {"amount": "100.00", "currencyCode": "USD"}
    assert li["taxable"] is False and i["billingAddress"] == i["shippingAddress"]
    assert not any(w in json.dumps(i, ensure_ascii=False).lower() for w in ("service fee", "수수료", "대행"))


def test_rejects_non_quoted_and_over_cap():
    with pytest.raises(ValueError):
        d.build_input({"status": "pending_shipping"}, "a@b.com", "u", ADDR, 1020.0)
    with pytest.raises(ValueError):
        d.build_input({**Q, "total_usd": "500.01"}, "a@b.com", "u", ADDR, 1020.0)


def test_create_surfaces_user_errors(monkeypatch):
    import src.vendors.shopify_client as sc
    monkeypatch.setattr(sc, "graphql_query", lambda q, v: {"draftOrderCreate": {"userErrors": [{"message": "bad"}]}})
    with pytest.raises(RuntimeError):
        d.create(Q, "a@b.com", "u", ADDR, 1020.0)
    monkeypatch.setattr(sc, "graphql_query", lambda q, v: {"draftOrderCreate": {"draftOrder": {"id": "gid://x", "invoiceUrl": "https://i"}, "userErrors": []}})
    assert d.create(Q, "a@b.com", "u", ADDR, 1020.0)["invoiceUrl"] == "https://i"
