"""F40 계약 — 화면이 여는 주소와 등록이 보는 주소가 같아야 한다.

## 실측 (오너 2026-09-20, 카나리 3차)

F39 배포 **뒤에도** 쿠팡 등록이 `sku=''` + **「알 수 없는 사이트」**.
그런데 같은 항목의 **「원본 보기」**는 `https://detail.tmall.com/item.htm?id=617129397971`을 연다
(그 주소면 `vendor_sku` = `'617129397971'`).

## 코드로 확정한 것

| 읽는 쪽 | 읽는 자리 |
|---|---|
| 「원본 보기」(드로어 `data-url` · 편집 `{{ item.url }}`) | **행의 `url` 컬럼** |
| 일괄 등록 페이로드 | **`extra_json`** — `if not product:`일 때만 행 url을 넣었다 |

텔레그램/공유 수집의 `extra`는 **비어 있지 않고**, 그 키 목록에 **`url`이 없다**
(실측: `title·title_ko·images·price·…·final_url·share_raw`). 그래서 페이로드엔 주소가
**통째로 없었고**, 「알 수 없는 사이트」는 **주소가 틀린 게 아니라 아예 없다**는 뜻이었다.

> ★★★ **F39와 같은 병의 다음 갈래.** 거기선 한 값이 **두 이름**이었고,
> 여기선 한 값이 **두 저장 자리**(행 컬럼 ↔ `extra_json`)에 있었다.
> 화면이 여는 주소와 등록이 보는 주소는 **같은 자리에서** 나와야 한다.

## 함께 고친 것

- **후보가 여럿이면 「쓸 수 있는 것」을 고른다** — 공유 링크(`e.tb.cn/h.…?tk=…`)는 주소이지만
  상품번호가 없다. 상품번호가 나오는 후보를 먼저 찾으므로, 공유 링크는 **자연히 최후 폴백**이
  된다(호스트 목록을 따로 안 박는다).
- **고른 주소를 로그에 남긴다**(URL이라 마스킹 대상 아님 — 오너 지시).
- 실패 문장에 **본 주소의 호스트**를 싣는다. 「주소가 틀렸나」와 「주소가 없나」를 가르려고.

라이브 호출 0.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

TMALL = "https://detail.tmall.com/item.htm?id=617129397971"
SKU = "617129397971"
SHARE = "https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt"


def _telegram_extra():
    """공유/텔레그램 수집이 실제로 담는 모양 — **`url` 키가 없다**(실측)."""
    return {
        "title": "修行盾", "title_ko": "수행방패", "images": [], "price": "88",
        "currency": "CNY", "price_source": "share_link", "mode": "share",
        "share_tk": "nyXpT7VA7lt", "share_code": "CZ356",
        "site_item_id": SKU, "short_name": "h.8IcTrtZuTU19ieN",
        "final_url": TMALL, "uncollected": [], "gate_ready": True,
        "enrich_state": "pending", "share_raw": "【淘宝】…",
    }


# ---------------------------------------------------------------------------
# ① 후보 고르기 — 쓸 수 있는 주소를 고른다
# ---------------------------------------------------------------------------

def test_the_expanded_url_wins_over_the_share_link():
    """★★ **F40의 판정 지점** — 공유 링크가 먼저 있어도 **펴진 주소**를 고른다."""
    from src.seller_console.upload_dispatcher import draft_url
    assert draft_url({"url": SHARE, "final_url": TMALL}) == TMALL


def test_the_share_link_is_the_last_resort():
    """쓸 수 있는 후보가 없으면 그때만 공유 링크 — 빈값보다는 낫다(사람이 열어 볼 수 있다)."""
    from src.seller_console.upload_dispatcher import draft_url
    assert draft_url({"url": SHARE}) == SHARE


def test_final_url_is_read_at_all():
    """★ 공유 수집 extra의 실제 키다 — 이 이름을 안 읽어서 주소가 사라졌다."""
    from src.seller_console.upload_dispatcher import DRAFT_URL_KEYS, draft_url
    assert "final_url" in DRAFT_URL_KEYS
    assert draft_url(_telegram_extra()) == TMALL


def test_a_plain_url_still_wins_when_usable():
    """무회귀 — 둘 다 쓸 수 있으면 `url`이 먼저다(사람이 화면에서 고친 값)."""
    from src.seller_console.upload_dispatcher import draft_url
    other = "https://item.taobao.com/item.htm?id=111222333"
    assert draft_url({"url": other, "final_url": TMALL}) == other


def test_no_address_is_still_empty():
    from src.seller_console.upload_dispatcher import draft_url
    assert draft_url({"title": "수행방패"}) == ""


def test_a_broken_sku_calculation_does_not_lose_the_address():
    """★ 식별자 계산이 터져도 **주소는 잃지 않는다** — 첫 후보라도 돌려준다."""
    from src.seller_console.upload_dispatcher import draft_url
    with patch("src.collectors.product_key.vendor_sku", side_effect=RuntimeError("boom")):
        assert draft_url({"final_url": TMALL}) == TMALL


# ---------------------------------------------------------------------------
# ② 오너 계약 — 텔레그램 수집 티몰 상품의 쿠팡 페이로드 sku
# ---------------------------------------------------------------------------

def test_the_coupang_payload_gets_the_sku(monkeypatch):
    """★★ **오너 계약 그대로** — 텔레그램 경로로 수집한 티몰 상품의 sku == '617129397971'."""
    from src.seller_console import views

    sent = {}

    class _Up:
        CATEGORY_MAP: dict = {}

        def upload_product(self, product):
            sent.update(product)
            return {"success": True, "product_id": "p1"}

    monkeypatch.setattr("src.pipeline.coupang_replicate._account_creds",
                        lambda a: ("ak", "sk", "A01381223"))
    monkeypatch.setattr("src.uploaders.coupang_uploader.CoupangUploader",
                        lambda **kw: _Up())

    payload = dict(_telegram_extra())
    payload["sell_price_krw"] = 19900
    views._coupang_account_dispatch(payload, "gogane")
    assert sent["sku"] == SKU, sent.get("sku")
    assert sent["url"] == TMALL


def test_the_bulk_path_carries_the_row_url():
    """★★ 행의 `url` 컬럼(= 「원본 보기」가 여는 값)이 **항상** 페이로드에 실린다."""
    import inspect
    from src.seller_console import views
    src = inspect.getsource(views.collect_bulk_upload)
    assert 'product["url"] = item.get("url")' in src
    # `if not product:` 안에만 있으면 안 된다 — extra가 비어 있지 않은 게 보통이다.
    guarded = src.index("if not product:")
    always = src.rindex('product["url"] = item.get("url")')
    assert always > guarded, "행 url 주입이 여전히 빈 extra일 때만 일어난다"


def test_the_single_upload_path_fills_it_too():
    import inspect
    from src.seller_console import views
    src = inspect.getsource(views.collect_upload)
    assert 'product_data["url"] = _uit.get("url")' in src


# ---------------------------------------------------------------------------
# ③ 다음 판을 아끼는 것들 — 로그와 문장
# ---------------------------------------------------------------------------

def test_the_chosen_address_is_logged(caplog):
    """★ 오너 지시 — 고른 주소를 로그에 남긴다(URL이라 마스킹 대상 아님)."""
    import logging

    from src.seller_console.upload_dispatcher import UploadDispatcher
    with caplog.at_level(logging.INFO, logger="src.seller_console.upload_dispatcher"):
        UploadDispatcher().dispatch(_telegram_extra(), [])
    line = " ".join(r.getMessage() for r in caplog.records)
    assert TMALL in line, line
    assert "final_url" in line, "어느 이름에서 왔는지도 남긴다"


def test_an_empty_address_says_so_rather_than_unknown_site():
    """★★ 「알 수 없는 사이트」는 **주소가 틀렸다**는 뜻으로 읽힌다 — 실제로는 없었다."""
    from src.collectors.product_key import sku_failure_message
    msg = sku_failure_message("")
    assert "페이로드에 없습니다" in msg
    assert "알 수 없는 사이트" not in msg


def test_the_message_names_the_host_it_looked_at():
    """★ 본 주소의 호스트를 싣는다 — 이게 있었으면 한 판 아꼈다(오너)."""
    from src.collectors.product_key import sku_failure_message
    msg = sku_failure_message("https://item.taobao.com/item.htm")
    assert "item.taobao.com" in msg and "타오바오" in msg


def test_a_usable_address_produces_no_failure_message_path():
    """무회귀 — 진짜 상품번호가 있으면 이 문장 자체가 안 나온다."""
    from src.collectors.product_key import vendor_sku
    assert vendor_sku(TMALL) == SKU
