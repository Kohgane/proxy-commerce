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

### 마진 정의 (오너 지시로 계약에 명기)

`src/price.calc_landed_cost`가 정본이고 **markup**이다(gross margin 아님):

    판매가KRW = (원가KRW + 배대지수수료KRW + 국제배송비KRW) × (1 + 관부가세율) × (1 + 마진율)

- **포함**: 배대지 수수료(`FORWARDER_FEE_JPY`) · 국제배송비(`SHIPPING_FEE_DEFAULT`) ·
  관부가세(`CUSTOMS_THRESHOLD_KRW` 초과 시)
- **미포함**: **마켓 판매수수료**(쿠팡·11번가·Shopify 결제수수료 등).
  `target_margin_pct`는 그 수수료를 덮지 않으므로 **실수령 마진은 이보다 낮다.**

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
                 ("CUSTOMS_THRESHOLD_KRW", "150000"), ("IMPORT_MARGIN_PCT", "25")):
        monkeypatch.setenv(k, v)


# ---------------------------------------------------------------------------
# a) 원가로 팔지 않는다
# ---------------------------------------------------------------------------

def test_the_price_is_never_the_raw_cost(dispatcher):
    """★★ **F42a의 판정 지점** — 판매가가 원가보다 **확실히 크다**."""
    pd = {"price_original": 29.9, "currency": "CNY", "target_margin_pct": 25.0}
    usd, why = dispatcher.sell_price_in(pd, "USD")
    assert usd is not None, why
    cost_usd = 29.9 * CNYKRW / USDKRW
    assert usd > cost_usd * 1.2, (usd, cost_usd)


def test_the_margin_definition_is_markup_on_landed_cost(dispatcher):
    """★★ 오너 지시 — **식을 계약에 박는다**(markup · 배송·수수료 포함 범위).

    판매가KRW = (원가KRW + 배대지수수료KRW + 국제배송비) × (1+관부가세율) × (1+마진율)
    """
    from src.price import calc_landed_cost

    pd = {"price_original": 100.0, "currency": "USD", "target_margin_pct": 25.0}
    krw, _ = dispatcher.sell_price_in(pd, "KRW")
    expected = float(calc_landed_cost(buy_price=100.0, buy_currency="USD",
                                      margin_pct=25.0, fx_rates=dict(FX)))
    assert abs(krw - round(expected)) <= 1, (krw, expected)

    # 배송비가 실제로 들어간다 — 0원이면 이 값이 달라진다.
    cost_only = 100.0 * USDKRW
    assert krw > cost_only * 1.25, "배송비·배대지 수수료가 빠졌다"


def test_market_commission_is_not_included_and_we_say_so(dispatcher):
    """★ **미포함을 명시한다.** 실수령 마진은 이보다 낮다 — 모르면 사람이 잘못 판단한다."""
    import inspect
    doc = inspect.getdoc(dispatcher.sell_price_in) or ""
    assert "미포함" in doc and "마켓 판매수수료" in doc
    assert "markup" in doc


def test_one_formula_for_every_currency(dispatcher):
    """★ KRW로 한 번 내고 통화만 환산한다 — 식이 두 벌이면 마켓마다 값이 갈린다."""
    pd = {"price_original": 100.0, "currency": "USD", "target_margin_pct": 25.0}
    krw, _ = dispatcher.sell_price_in(pd, "KRW")
    usd, _ = dispatcher.sell_price_in(pd, "USD")
    assert abs(usd - krw / USDKRW) < 0.02


def test_a_krw_cost_still_gets_a_sell_price(dispatcher):
    """★ 원가가 KRW여도 외화 마켓 판매가가 나온다 — 예전엔 일찍 돌아가 빈값이었다."""
    usd, why = dispatcher.sell_price_in({"price": 29900, "currency": "KRW"}, "USD")
    assert usd is not None and usd > 29900 / USDKRW, (usd, why)


def test_an_unresolvable_price_is_refused_not_guessed(dispatcher):
    """★★ 환율·통화가 없으면 **원가로 폴백하지 않는다** — 조용한 손해가 가짜 성공보다 나쁘다."""
    val, why = dispatcher.sell_price_in({"price": 100}, "USD")   # 통화 없음
    assert val is None and why


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
