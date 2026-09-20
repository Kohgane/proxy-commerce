"""F42b·d·e·f 계약 — 남의 가게 광고·같은 사진 세 번·못 읽는 제목.

## 실측 (오너 2026-09-20, 카나리 1호)

| # | 증상 | 이 판 |
|---|---|---|
| b | 설명란에 **티몰 셀러 카드**(旗舰店·88VIP·发货·回复) | 줄 단위로 덜어낸다 |
| d | Shopify(US 스토어) 제목이 **한국어** | 영문 제목 없으면 **보류** |
| e | **상세 1·2가 갤러리 1과 같은 파일** | 나가는 주소로 중복 제거 |
| f | WC **원산지·브랜드 빈칸** | **실측: 초안에 값이 없다**(아래) |

## f) 실측 결과 — 안 보낸 게 아니라 **없다**

텔레그램/공유 수집이 `extra`에 담는 키(코드 실측):

    title · title_ko · images · price · currency · price_source ·
    price_captured_at_share · mode · share_tk · share_code · site_item_id ·
    short_name · final_url · uncollected · gate_ready · enrich_state · share_raw

**`brand`도 `source_country`도 없다.** 공유 글에는 그 정보가 안 들어 있다.
배선은 멀쩡하다 — `to_collected`가 `brand`를 그대로 넘기고, WC 행도 그걸 읽는다.

> ★ **「안 보냈다」와 「없다」는 다른 사건이다.** 없는 값을 채우는 코드는 발명이다.
> 이 계약은 **배선이 멀쩡함**을 고정하고, 값을 지어내지 않는다.

라이브 호출 0.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

SELLER_CARD = "\n".join([
    "旗舰店 官方授权",
    "이 제품은 원목 프레임입니다.",
    "88VIP 专享价",
    "24小时内发货",
    "组装方法는 설명서를 확인하세요.",
    "回复率 99%",
])


# ---------------------------------------------------------------------------
# b) 남의 가게 광고를 우리 상세로 내보내지 않는다
# ---------------------------------------------------------------------------

def test_the_seller_card_lines_are_removed():
    """★★ **F42b의 판정 지점** — 4개 토큰이 든 줄만 덜어낸다."""
    from src.collectors.universal_scraper import strip_seller_card
    out = strip_seller_card(SELLER_CARD)
    for tok in ("旗舰店", "88VIP", "发货", "回复"):
        assert tok not in out, tok


def test_the_real_description_survives():
    """★★ 통째로 버리면 **같은 블록에 붙어 온 진짜 상세**까지 잃는다."""
    from src.collectors.universal_scraper import strip_seller_card
    out = strip_seller_card(SELLER_CARD)
    assert "원목 프레임" in out
    assert "설명서를 확인하세요" in out


def test_an_all_card_description_becomes_empty():
    """★ 남는 게 부스러기뿐이면 **빈 설명**이다(오너: 상세 없으면 빈 설명이 낫다)."""
    from src.collectors.universal_scraper import strip_seller_card
    assert strip_seller_card("旗舰店\n88VIP\n · \n回复率 99%") == ""


def test_a_clean_description_is_untouched():
    """무회귀 — 멀쩡한 상세는 한 글자도 안 바뀐다."""
    from src.collectors.universal_scraper import strip_seller_card
    txt = "원목 프레임\n조립 방법을 확인하세요"
    assert strip_seller_card(txt) == txt


def test_every_market_goes_through_the_filter():
    """★★ 마켓마다 걸면 언젠가 한 마켓이 빠진다(F42a에서 Shopify가 그랬다)."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    for market in ("coupang", "smartstore", "elevenst", "woocommerce", "shopify"):
        payload, _ = UploadDispatcher._payload_for_market(
            {"title": "t", "description": SELLER_CARD}, market)
        assert "旗舰店" not in payload["description"], market
        assert "원목 프레임" in payload["description"], market


def test_a_seller_written_block_is_never_filtered():
    """★ 셀러가 직접 꾸민 블록은 **사람이 만든 것**이다 — 건드리지 않는다."""
    from src.seller_console.upload_dispatcher import UploadDispatcher
    payload, _ = UploadDispatcher._payload_for_market(
        {"title": "t",
         "detail_blocks": {"common": [{"type": "text", "content": "88VIP 전용가 안내"}]}},
        "coupang")
    assert "88VIP" in payload["description_html"]


# ---------------------------------------------------------------------------
# d) 못 읽는 제목으로 등록하지 않는다
# ---------------------------------------------------------------------------

@pytest.fixture
def dispatcher():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    return UploadDispatcher()


def test_a_korean_title_holds_instead_of_listing(dispatcher):
    """★★ **F42d의 판정 지점** — 「원문 사용」이 아니라 **보류**다(오너)."""
    res = dispatcher._upload_shopify({"title": "수행방패", "price": 100, "currency": "KRW"})
    assert res.success is False
    assert res.error_code == "title_not_english"
    assert "영문" in (res.hint or "")


def test_an_english_title_passes(dispatcher, monkeypatch):
    sent = {}

    class _A:
        def validate_listing(self, p):
            from src.markets.adapters.base import ListingResult
            sent["title"] = p.title
            return ListingResult(ok=True, market="shopify", message="ok", raw={})

        def upload_product(self, p):
            from src.markets.adapters.base import ListingResult
            return ListingResult(ok=True, market="shopify", external_id="X", message="ok", raw={})

    monkeypatch.setattr("src.markets.adapters.shopify.ShopifyAdapter", _A)
    dispatcher._upload_shopify({"title": "수행방패", "title_en": "Cultivation Shield",
                                "price": 100, "currency": "KRW"})
    assert sent["title"] == "Cultivation Shield"


def test_an_already_english_title_needs_no_translation(dispatcher, monkeypatch):
    """영문으로 수집된 상품은 그대로 나간다 — 번역을 요구하지 않는다."""
    sent = {}

    class _A:
        def validate_listing(self, p):
            from src.markets.adapters.base import ListingResult
            sent["title"] = p.title
            return ListingResult(ok=True, market="shopify", message="ok", raw={})

        def upload_product(self, p):
            from src.markets.adapters.base import ListingResult
            return ListingResult(ok=True, market="shopify", external_id="X", message="ok", raw={})

    monkeypatch.setattr("src.markets.adapters.shopify.ShopifyAdapter", _A)
    dispatcher._upload_shopify({"title": "Folding Car Desk", "price": 100, "currency": "KRW"})
    assert sent["title"] == "Folding Car Desk"


def test_a_mixed_title_is_not_english(dispatcher):
    """한 글자라도 한글이면 영문 제목이 아니다 — 반쯤 번역된 제목을 내보내지 않는다."""
    res = dispatcher._upload_shopify({"title_en": "Shield 수행방패",
                                      "price": 100, "currency": "KRW"})
    assert res.success is False and res.error_code == "title_not_english"


def test_domestic_markets_keep_korean_titles():
    """★ 국내 마켓은 한국어 제목이 **정답**이다 — 이 게이트는 Shopify 것이다."""
    import inspect
    from src.seller_console.upload_dispatcher import UploadDispatcher
    for fn in (UploadDispatcher._upload_elevenst, UploadDispatcher._upload_woocommerce):
        assert "title_not_english" not in inspect.getsource(fn)


# ---------------------------------------------------------------------------
# e) 같은 사진을 세 번 올리지 않는다
# ---------------------------------------------------------------------------

def test_detail_drops_pages_already_in_the_gallery():
    """★★ **F42e의 판정 지점** — 상세 1·2가 갤러리 1과 같은 파일이었다."""
    from src.services.image_translate_store import drop_cross_duplicates
    g, d = drop_cross_duplicates(["https://c/1.jpg", "https://c/2.jpg"],
                                 ["https://c/1.jpg", "https://c/1.jpg", "https://c/3.jpg"])
    assert g == ["https://c/1.jpg", "https://c/2.jpg"]
    assert d == ["https://c/3.jpg"]


def test_the_gallery_is_never_emptied():
    """갤러리가 대표다 — 상세에서 뺀다, 갤러리에서 빼지 않는다."""
    from src.services.image_translate_store import drop_cross_duplicates
    g, d = drop_cross_duplicates(["https://c/1.jpg"], ["https://c/1.jpg"])
    assert g == ["https://c/1.jpg"] and d == []


def test_duplicates_inside_detail_go_too():
    from src.services.image_translate_store import drop_cross_duplicates
    _, d = drop_cross_duplicates([], ["https://c/9.jpg", "https://c/9.jpg"])
    assert d == ["https://c/9.jpg"]


def test_different_addresses_are_kept_and_we_say_why():
    """★ **한계를 적는다** — 같은 그림이 다른 주소로 오면 이 방법은 못 잡는다."""
    import inspect
    from src.services import image_translate_store as S
    g, d = S.drop_cross_duplicates(["https://c/1.jpg"], ["https://c/1_copy.jpg"])
    assert d == ["https://c/1_copy.jpg"]
    doc = inspect.getdoc(S.drop_cross_duplicates) or ""
    assert "못 잡는다" in doc and "바이트 해시는 쓰지 않는다" in doc


def test_the_upload_path_applies_it():
    import inspect
    from src.seller_console import views
    assert "drop_cross_duplicates" in inspect.getsource(views.collect_upload)


# ---------------------------------------------------------------------------
# f) 원산지·브랜드 — 배선은 멀쩡하다. 값이 없다.
# ---------------------------------------------------------------------------

def test_the_wiring_carries_brand_and_origin_when_present():
    """★ 값이 있으면 **그대로 간다** — 안 보내는 게 아니다."""
    from src.channel_sync._channel_bridge import to_collected
    c = to_collected({"title": "t", "brand": "PORTER", "sell_price_krw": 19900})
    assert c["brand"] == "PORTER"

    sent = {}

    class _WC:
        @staticmethod
        def prepare_product_data(row, price):
            sent.update(row)
            return {}

        @staticmethod
        def upsert_product(prod):
            return {"id": 1}

    import src.vendors as _pkg
    from src.seller_console.upload_dispatcher import UploadDispatcher
    with patch.object(_pkg, "woocommerce_client", _WC, create=True):
        UploadDispatcher()._upload_woocommerce(
            {"title_ko": "t", "sell_price_krw": 19900, "brand": "PORTER",
             "source_country": "CN"})
    assert sent["brand"] == "PORTER"
    assert sent["source_country"] == "CN"


def test_the_share_collector_simply_has_no_such_fields():
    """★★ **f의 실측** — 공유 수집 extra에 `brand`·`source_country`가 **없다**.

    없는 값을 채우는 코드는 발명이다. 이 계약은 **없다는 사실**을 고정한다 —
    다음 사람이 「왜 빈칸이지」로 또 파지 않게.
    """
    import re
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1]
           / "src/collectors/share_collect.py").read_text(encoding="utf-8")
    blk = src[src.index("extra={"):src.index('"share_raw"') + 40]
    keys = set(re.findall(r'"([a-z_]+)":', blk))
    assert "brand" not in keys and "source_country" not in keys, keys
    assert "title" in keys and "final_url" in keys, "전제가 바뀌었다 — 실측을 다시 하라"
