"""F42a·c 계약 — 원가로 팔지 않는다 · 등록 직후 살 수 있다.

## 실측 (오너 2026-09-20, 카나리 1호 — Shopify 9372623241270 · WC 40210)

| # | 증상 |
|---|---|
| a | Shopify 가격 **$4.10 = 원가 환산.** 마진·배송비 미적용 |
| c | WC 상품이 **Out of stock** — 등록은 됐는데 **못 산다** |

둘 다 **판매 불가**라 F40·F41과 같은 급이다.

## a) 산정식이 마켓마다 따로였다

`_ensure_sell_price_krw`의 docstring이 그대로 적어 두고 있었다:
**「Shopify는 원문가/통화를 직접 사용하므로 영향받지 않는다」**.
원화 마켓만 산정하고 **외화 마켓은 원가를 그대로 냈다.**

> ★★★ **판매가 산정식이 마켓마다 따로면, 안 고친 마켓이 원가로 나간다.**
> 식은 하나여야 한다 — KRW로 한 번 내고 **통화만 환산**한다.

### 마진 정의 — **실수령 마진**(오너 결정 2026-09-20, 갱신)

처음 이 계약은 식이 **markup**이라고 적었다. 오너가 그걸 읽고 **정책을 따르라**고 했다
(볼트 [[가격 정책 — 실마진 기준]]). 그래서 코드를 고쳤고, 이 계약도 같이 고친다:

    판매가 = (랜딩코스트 + 국내배송비) ÷ (1 − 마켓수수료율 − 목표마진율)
    랜딩코스트 = (원가KRW + 배대지수수료 + 국제배송비) × (1 + 관부가세율)

- **포함**: 배대지 수수료 · 국제배송비 · 관부가세 · **마켓 판매수수료** · **국내배송비**
- `target_margin_pct` = **남는 비율.** 판매가에서 수수료·배송을 빼면 정확히 그 비율이다.

> ★★★ **왜 고쳤나 — 이 카나리가 근거다.**
> WC 실측 ₩24,682는 옛 markup 22%가 낸 값이다. 거기서 수수료 10.8%와 국내배송 ₩3,000을
> 빼면 **실마진 −4.9%**다. **팔릴수록 손해인 가격이 이미 올라가 있었다.**

> ★ **마켓수수료율을 모르면 등록하지 않는다.** 실측된 건 쿠팡 10.8%뿐이다.
> 짐작한 수수료로 매긴 값은 빈칸보다 나쁘다 — 틀린 값으로 **실제로 팔린다.**

## c) 우리 재고 0을 「품절」로 번역했다

무재고 구매대행이라 우리 창고 재고는 **0이 정상**이다. 그런데 `stock`이 없으면 0으로 나가고
`woocommerce_client`가 `0 → outofstock`으로 바꾼다. 파일럿 경로는 이미
`manage_stock=False · instock`을 보내고 있었고(`views.py:8108`), **수동 업로드 경로만** 안 보냈다.

> ★★ **같은 판매 모델이면 경로가 달라도 같은 값이어야 한다.**

라이브 호출 0.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

# 실제 `_build_fx_rates()`는 **Decimal**을 낸다 — float를 주면 계산이 TypeError로 죽는다.
FX = {"USDKRW": Decimal("1350"), "CNYKRW": Decimal("190"), "JPYKRW": Decimal("9")}
USDKRW, CNYKRW = 1350.0, 190.0


@pytest.fixture
def dispatcher():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    return UploadDispatcher()


@pytest.fixture(autouse=True)
def _fixed_fx(monkeypatch):
    monkeypatch.setattr("src.price._build_fx_rates", lambda *a, **k: dict(FX))
    for k, v in (("FORWARDER_FEE_JPY", "300"), ("SHIPPING_FEE_DEFAULT", "12000"),
                 ("CUSTOMS_THRESHOLD_KRW", "150000"), ("IMPORT_MARGIN_PCT", "25"),
                 ("DOMESTIC_SHIPPING_FEE_KRW", "3000"),
                 # 카나리 마켓들의 **실측 수수료는 아직 없다.** 계약이 값을 내려면 줘야 한다 —
                 #   그 사실 자체를 아래 `test_a_market_without_a_measured_commission_holds`가 잰다.
                 ("MARKET_COMMISSION_PCT_SHOPIFY", "2.9"),
                 ("MARKET_COMMISSION_PCT_WOOCOMMERCE", "3.0")):
        monkeypatch.setenv(k, v)


# ---------------------------------------------------------------------------
# a) 원가로 팔지 않는다
# ---------------------------------------------------------------------------

def test_the_price_is_never_the_raw_cost(dispatcher):
    """★★ **F42a의 판정 지점** — 판매가가 원가보다 **확실히 크다**."""
    pd = {"price_original": 29.9, "currency": "CNY", "target_margin_pct": 25.0}
    usd, why = dispatcher.sell_price_in(pd, "USD", market="shopify")
    assert usd is not None, why
    cost_usd = 29.9 * CNYKRW / USDKRW
    assert usd > cost_usd * 1.2, (usd, cost_usd)


def test_the_target_margin_is_what_actually_remains(dispatcher):
    """★★★ **이 계약이 식의 뜻이다**(오너 지시, 2026-09-20 갱신).

    「판매가에서 수수료·배송을 빼면 정확히 목표마진.」
    """
    from src.price import landed_cost_krw, net_margin_pct

    pd = {"price_original": 100.0, "currency": "USD", "target_margin_pct": 22.0}
    krw, why = dispatcher.sell_price_in(pd, "KRW", market="coupang")
    assert krw, why
    landed = landed_cost_krw(100.0, "USD", fx_rates=dict(FX))
    got = float(net_margin_pct(krw, landed, "coupang"))
    assert abs(got - 22.0) < 0.05, got


def test_the_old_markup_price_was_actually_a_loss():
    """★★★ **왜 식을 바꿨나** — 카나리 1호 WC 실측 ₩24,682의 실마진은 **음수**다.

    옛 식(markup 22%)이 낸 그 값에서 쿠팡 수수료 10.8%와 국내배송 ₩3,000을 빼면
    남는 게 **마이너스**다. 팔릴수록 손해인 가격이 이미 올라가 있었다.
    """
    from decimal import Decimal as D

    from src.price import net_margin_pct

    listed = D("24682")                    # 오너 실측
    landed = listed / D("1.22")            # 옛 markup 22%를 역산한 랜딩코스트
    got = net_margin_pct(listed, landed, "coupang")
    assert got < 0, got


def test_the_formula_is_stated_in_the_docstring(dispatcher):
    """★ 식이 **무엇을 포함하는지** 코드가 말한다 — 모르면 사람이 잘못 판단한다."""
    import inspect
    doc = inspect.getdoc(dispatcher.sell_price_in) or ""
    assert "마켓 판매수수료" in doc and "국내배송비" in doc
    assert "남는 비율" in doc


def test_one_formula_for_every_currency(dispatcher):
    """★ KRW로 한 번 내고 통화만 환산한다 — 식이 두 벌이면 마켓마다 값이 갈린다."""
    pd = {"price_original": 100.0, "currency": "USD", "target_margin_pct": 25.0}
    krw, _ = dispatcher.sell_price_in(pd, "KRW", market="shopify")
    usd, _ = dispatcher.sell_price_in(pd, "USD", market="shopify")
    assert abs(usd - krw / USDKRW) < 0.02


def test_the_same_product_costs_more_where_the_commission_is_higher(dispatcher):
    """★★ **마켓마다 값이 달라야 한다** — 수수료가 식에 들어왔기 때문.

    루프 밖에서 한 번만 산정하면 수수료 높은 마켓에서 그만큼 손해다.
    """
    pd = {"price_original": 100.0, "currency": "USD", "target_margin_pct": 22.0}
    coupang, _ = dispatcher.sell_price_in(pd, "KRW", market="coupang")     # 10.8%
    shopify, _ = dispatcher.sell_price_in(pd, "KRW", market="shopify")     # 2.9%
    assert coupang > shopify, (coupang, shopify)


def test_a_krw_cost_still_gets_a_sell_price(dispatcher):
    """★ 원가가 KRW여도 외화 마켓 판매가가 나온다 — 예전엔 일찍 돌아가 빈값이었다."""
    usd, why = dispatcher.sell_price_in({"price": 29900, "currency": "KRW"}, "USD",
                                        market="shopify")
    assert usd is not None and usd > 29900 / USDKRW, (usd, why)


def test_an_unresolvable_price_is_refused_not_guessed(dispatcher):
    """★★ 환율·통화가 없으면 **원가로 폴백하지 않는다** — 조용한 손해가 가짜 성공보다 나쁘다."""
    val, why = dispatcher.sell_price_in({"price": 100}, "USD", market="shopify")
    assert val is None and why


def test_a_market_without_a_measured_commission_holds(dispatcher, monkeypatch):
    """★★★ **모르면 등록하지 않는다**(오너 지시).

    11번가 수수료율은 아직 실측이 없다. 짐작해서 매긴 값으로 파느니 **보류**다.
    """
    monkeypatch.delenv("MARKET_COMMISSION_PCT_ELEVENST", raising=False)
    val, why = dispatcher.sell_price_in(
        {"price_original": 100.0, "currency": "USD"}, "KRW", market="elevenst")
    assert val is None
    assert "판매수수료율" in why and "MARKET_COMMISSION_PCT_ELEVENST" in why


def test_the_price_gate_is_one_place_for_every_market(dispatcher, monkeypatch):
    """★★ 마켓별 업로더마다 따로 막으면 **한 곳을 빠뜨리고, 그 마켓이 원가로 나간다.**"""
    monkeypatch.delenv("MARKET_COMMISSION_PCT_ELEVENST", raising=False)
    for mkt in ("coupang", "smartstore", "elevenst", "woocommerce", "shopify"):
        res = dispatcher._price_gate({"price_original": 100.0, "currency": "USD"}, mkt)
        from src.price import commission_pct
        rate, _ = commission_pct(mkt)
        assert (res is None) is (rate is not None), (mkt, res)


def test_a_price_the_seller_typed_still_wins(dispatcher):
    """★ 셀러가 직접 적은 판매가는 셀러의 결정이다 — 수수료를 몰라도 막지 않는다."""
    assert dispatcher._price_gate({"sell_price_krw": 39000}, "elevenst") is None


def test_shopify_holds_instead_of_listing_the_cost(dispatcher, monkeypatch):
    """★★ 판매가를 못 내면 **등록하지 않는다**(원가 등록 금지)."""
    res = dispatcher._upload_shopify({"title": "수행방패", "title_en": "Umbrella", "price": 100})
    assert res.success is False
    assert res.error_code == "price_unresolved"
    assert "원가 그대로" in (res.hint or ""), res.hint


def test_shopify_sends_the_store_currency(dispatcher, monkeypatch):
    """★ 공급사 통화를 그대로 내면 스토어가 제 통화로 읽어 **값이 통째로 달라진다**."""
    sent = {}

    class _Adapter:
        def validate_listing(self, payload):
            from src.markets.adapters.base import ListingResult
            sent["price"], sent["currency"] = payload.price, payload.currency
            return ListingResult(ok=True, market="shopify", message="ok", raw={})

        def upload_product(self, payload):
            from src.markets.adapters.base import ListingResult
            return ListingResult(ok=True, market="shopify", external_id="X", message="ok", raw={})

    monkeypatch.setattr("src.markets.adapters.shopify.ShopifyAdapter", _Adapter)
    monkeypatch.setenv("SHOPIFY_STORE_CURRENCY", "USD")
    dispatcher._upload_shopify({"title": "수행방패", "title_en": "Umbrella", "price_original": 29.9, "currency": "CNY"})
    assert sent["currency"] == "USD", sent
    assert sent["price"] > 29.9 * CNYKRW / USDKRW, sent


# ---------------------------------------------------------------------------
# c) 등록 직후 살 수 있다
# ---------------------------------------------------------------------------

def _wc_row(dispatcher, product_data):
    sent = {}

    class _WC:
        @staticmethod
        def prepare_product_data(row, price):
            sent.update(row)
            return {"id": 1}

        @staticmethod
        def upsert_product(prod):
            return {"id": 40210, "permalink": "https://shop.example/p/40210"}

    import src.vendors as _pkg
    with patch.object(_pkg, "woocommerce_client", _WC, create=True):
        dispatcher._upload_woocommerce(product_data)
    return sent


def test_a_zero_stock_item_is_still_purchasable(dispatcher):
    """★★ **F42c의 판정 지점** — 무재고 구매대행은 `manage_stock=False · instock`."""
    row = _wc_row(dispatcher, {"title_ko": "수행방패", "sell_price_krw": 19900})
    assert row["manage_stock"] is False
    assert row["stock_status"] == "instock"


def test_an_explicit_choice_still_wins(dispatcher):
    """★ 재고 관리형 셀러를 막지 않는다 — 호출부가 명시하면 그게 이긴다."""
    row = _wc_row(dispatcher, {"title_ko": "t", "sell_price_krw": 1,
                               "manage_stock": True, "stock_status": "outofstock",
                               "stock": 3})
    assert row["manage_stock"] is True and row["stock_status"] == "outofstock"


def test_the_pilot_path_and_the_manual_path_agree():
    """★ 같은 판매 모델인데 경로마다 값이 다르면 **한쪽이 못 판다**."""
    import inspect
    from src.seller_console import upload_dispatcher as UD
    from src.seller_console import views

    pilot = inspect.getsource(views._woocommerce_dispatch)
    manual = inspect.getsource(UD.UploadDispatcher._upload_woocommerce)
    assert "manage_stock" in pilot and "manage_stock" in manual
    assert '"instock"' in manual, "수동 경로가 판매 가능 상태를 안 보낸다"
