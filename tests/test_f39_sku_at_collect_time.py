"""F39 계약 — 한 값에 두 이름이 붙어 주소가 페이로드에서 사라졌다.

## 실측 (오너 2026-09-20)

수행방패 쿠팡 업로드가 **「SKU 추출 실패 … `''`」**로 정직 중단.
그런데 `vendor_sku('https://detail.tmall.com/item.htm?id=617129397971')`는
**`'617129397971'`**을 잘 낸다 — **규칙은 멀쩡했다.**

## 근원 — 초안은 `source_url`을 내고 읽는 쪽은 `url`을 읽었다

`Product.to_dict()`(`listing/auto_publish.py:124`, 디스패처 docstring이 `ProductDraft`라 부르는 그것)는
**`url` 키를 아예 안 만든다.** 그런데 페이로드를 만드는 자리는 전부 `product_data.get("url")`을
읽었다 → `''` → `vendor_sku("")` → `''` → 정직 중단.

> ★★★ **한 필드에 두 이름이 붙으면, 쓰는 쪽과 읽는 쪽은 반드시 갈린다.**
> 둘 다 정상으로 보이므로 사람은 못 본다 → **꺼내는 자리를 하나로** 만든다(`draft_url`).
> F34-2의 사본 드리프트와 동형이다 — 거기선 한 사실이 두 표에, 여기선 한 값이 두 이름에.

`test_no_payload_reader_reads_url_alone`이 **재발 감지기**다: 새 어댑터가 한 이름만 읽으면
라이브의 「SKU 추출 실패」보다 **CI가 먼저 운다**.

## 함께 잡은 것

- **수집 시점 확정**: 행에 식별자를 적는다. 못 뽑으면 목록에 「식별자 없음」 —
  업로더가 처음 알려 주면 늦다(카나리 8차 동형).
- **호스트별 기대치**: 「(아마존 ASIN 등)」은 타오바오 상품 앞에서 헷갈린다.
- **`tk`가 SKU로 나가고 있었다**: `e.tb.cn/h.…?tk=nyXpT7VA7lt` → `'nyXpT7VA7lt'`.
  `tbshare:<토큰>:<tk>` 키가 콜론 둘이라 판정을 통과했다. `tk`는 공유마다 바뀌는 토큰이고
  상품번호가 아니다 — 같은 상품이 공유마다 다른 SKU가 된다. **빈값보다 나쁘다.**

## 곁가지로 잰 것 (오너 초기 가설 — 둘 다 아니었다)

| 잰 것 | 결과 |
|---|---|
| 짧은 링크가 펴져 저장되나 | **펴진다.** `resolve_short_link` → `canonical_item_url` → `…?id=…` |
| 쿼리가 잘리나 | **안 잘린다.** `_URL_RE`는 `?`·`&`·`=`를 전부 허용한다 |
| 확장 보강이 url을 덮나 | **안 덮는다.** `update`의 허용 필드에 `url`이 없다 |

저장된 행은 멀쩡했다. **잃어버린 자리는 초안→페이로드 변환이었다.**

라이브 호출 0.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

TAOBAO_OK = "https://item.taobao.com/item.htm?id=123456789"
TAOBAO_NO_ID = "https://item.taobao.com/item.htm"
SHARE = "https://e.tb.cn/h.8IcTrtZuTU19ieN?tk=nyXpT7VA7lt"


# ---------------------------------------------------------------------------
# ① 공유 토큰은 SKU가 아니다
# ---------------------------------------------------------------------------

def test_a_share_token_is_never_a_sku():
    """★★ `tk`를 SKU로 내보내면 같은 상품이 공유마다 다른 SKU가 된다 — 빈값보다 나쁘다."""
    from src.collectors.product_key import vendor_sku
    assert vendor_sku(SHARE) == ""


def test_a_share_link_without_tk_is_also_empty():
    from src.collectors.product_key import vendor_sku
    assert vendor_sku("https://e.tb.cn/h.8IcTrtZuTU19ieN") == ""


def test_the_share_link_is_still_a_dedupe_key():
    """중복 판정 키는 그대로다 — SKU가 아닐 뿐, 같은 공유를 두 번 담는 건 여전히 잡는다."""
    from src.collectors.product_key import normalize_product_key
    assert normalize_product_key(SHARE).startswith("tbshare:h.8IcTrtZuTU19ieN")


@pytest.mark.parametrize("url,expect", [
    (TAOBAO_OK, "123456789"),
    ("https://detail.tmall.com/item.htm?id=987654321", "987654321"),
    ("https://detail.1688.com/offer/665544332211.html", "665544332211"),
    ("https://www.amazon.com/dp/B0CZ1ABCDE", "B0CZ1ABCDE"),
    (TAOBAO_NO_ID, ""),
])
def test_the_known_rules_still_hold(url, expect):
    """무회귀 — 진짜 상품번호는 그대로 뽑힌다."""
    from src.collectors.product_key import vendor_sku
    assert vendor_sku(url) == expect


# ---------------------------------------------------------------------------
# ② 호스트별로 무엇을 기대했는지 말한다 (오너 덤 지적)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url,must", [
    (TAOBAO_NO_ID, "타오바오"),
    ("https://detail.1688.com/x.html", "1688"),
    ("https://www.amazon.com/x", "ASIN"),
    ("https://www.temu.com/x", "Temu"),
    (SHARE, "공유 단축 링크"),
])
def test_the_message_says_what_was_expected(url, must):
    """★ 「(아마존 ASIN 등)」은 타오바오 상품 앞에서 헷갈린다 — 그 상품엔 ASIN이 없다."""
    from src.collectors.product_key import sku_failure_message
    msg = sku_failure_message(url)
    assert must in msg, msg


def test_an_unknown_host_says_it_is_unknown():
    """모르는 사이트에 기대값을 **지어내지 않는다**."""
    from src.collectors.product_key import sku_expectation, sku_failure_message
    assert sku_expectation("https://shop.example.com/p/1") == ""
    assert "알 수 없는 사이트" in sku_failure_message("https://shop.example.com/p/1")


def test_the_uploader_carries_the_host_specific_reason(monkeypatch):
    """★ 업로더 문장이 그 주소 기준으로 말한다 — 「아마존 ASIN 등」 고정 문구를 버렸다.

    배송 7필드 게이트가 **SKU 게이트보다 먼저** 선다. 그걸 통과시켜야 SKU 문장에 닿는다
    (게이트 순서를 바꾸지 않는다 — 계약이 코드를 따라간다).
    """
    from src.uploaders.coupang_uploader import CoupangUploader
    for k, v in (("ACCESS_KEY", "a"), ("SECRET_KEY", "s"), ("VENDOR_ID", "A01381223"),
                 ("DELIVERY_COMPANY_CODE", "KGB"), ("VENDOR_USER_ID", "shanks8"),
                 ("RETURN_CENTER_CODE", "1"), ("OUTBOUND_SHIPPING_PLACE_CODE", "2"),
                 ("RETURN_ZIP_CODE", "14600"), ("RETURN_ADDRESS", "주소"),
                 ("RETURN_CHARGE_NAME", "장말로"), ("COMPANY_CONTACT_NUMBER", "02-0-0")):
        monkeypatch.setenv(f"COUPANG_{k}", v)
    monkeypatch.setenv("COUPANG_IMAGE_SCREEN", "0")
    up = CoupangUploader()        # 실제 생성자 — 인스턴스 속성이 전부 있어야 게이트에 닿는다
    out = up.upload_product({"title": "수행방패", "price": 9900, "sku": "",
                             "url": TAOBAO_NO_ID})
    assert out["success"] is False and out.get("held") is True
    assert "타오바오" in out["error"], out["error"]
    assert "아마존 ASIN 등" not in out["error"]


def test_the_register_pipe_uses_the_same_sentence():
    import inspect
    from src.pipeline import register_pipe
    src = inspect.getsource(register_pipe)
    assert "sku_failure_message" in src


# ---------------------------------------------------------------------------
# ③ 수집 시점에 찍는다 — 모든 경로가 지나는 한 자리에서
# ---------------------------------------------------------------------------

def test_the_sku_is_stamped_on_the_row_at_collect_time():
    """★★ **F39의 판정 지점** — 수집이 끝나면 행에 식별자가 적혀 있다."""
    from src.seller_console import collect_history_store as store
    seen = {}

    def _append(**kw):
        seen.update(kw)
        return ("id-1", True)

    with patch.object(store, "_pg_backend", return_value=type("B", (), {"append": staticmethod(_append)})):
        store.append(source="share", url=TAOBAO_OK, title="수행방패", return_durable=True)
    assert seen["extra"]["vendor_sku"] == "123456789"


def test_a_row_without_an_identifier_says_so_at_collect_time():
    """★★ 못 뽑으면 **그때** 적는다 — 업로더가 처음 알려 주지 않게."""
    from src.seller_console import collect_history_store as store
    seen = {}

    def _append(**kw):
        seen.update(kw)
        return ("id-1", True)

    with patch.object(store, "_pg_backend", return_value=type("B", (), {"append": staticmethod(_append)})):
        store.append(source="share", url=TAOBAO_NO_ID, title="수행방패", return_durable=True)
    assert seen["extra"]["vendor_sku"] == ""
    assert "타오바오" in seen["extra"]["vendor_sku_expected"]


def test_every_collection_path_goes_through_that_one_gate():
    """★ 경로마다 찍으면 언젠가 한 경로가 빠진다 — `append` 하나가 관문이다."""
    import inspect
    from src.seller_console import collect_history_store as store
    src = inspect.getsource(store.append)
    assert "vendor_sku" in src
    # 백엔드 분기(PG/인메모리)보다 **먼저** 찍어야 양쪽에 다 남는다.
    assert src.index("vendor_sku") < src.index("_pg_backend()")


def test_an_explicit_sku_is_not_overwritten():
    """호출부가 이미 확정해 준 값이 있으면 그걸 쓴다(재계산으로 덮지 않는다)."""
    from src.seller_console import collect_history_store as store
    seen = {}

    def _append(**kw):
        seen.update(kw)
        return ("id-1", True)

    with patch.object(store, "_pg_backend", return_value=type("B", (), {"append": staticmethod(_append)})):
        store.append(source="ext", url=TAOBAO_NO_ID, title="t",
                     extra={"vendor_sku": "手動-123"}, return_durable=True)
    assert seen["extra"]["vendor_sku"] == "手動-123"


def test_a_stamping_failure_never_blocks_collection():
    """★ 식별자를 못 구하는 것과 **수집이 실패하는 것**은 다른 사건이다."""
    from src.seller_console import collect_history_store as store
    seen = {}

    def _append(**kw):
        seen.update(kw)
        return ("id-1", True)

    with patch("src.collectors.product_key.vendor_sku", side_effect=RuntimeError("boom")), \
         patch.object(store, "_pg_backend", return_value=type("B", (), {"append": staticmethod(_append)})):
        out = store.append(source="ext", url=TAOBAO_OK, title="t", return_durable=True)
    assert out == ("id-1", True)
    assert seen["extra"]["vendor_sku"] == ""


def test_the_in_memory_path_is_stamped_too(monkeypatch):
    """PG가 없는 개발/테스트 경로도 같은 값을 갖는다 — 갈리면 계약이 헛것을 잰다."""
    from src.seller_console import collect_history_store as store
    with patch.object(store, "_pg_backend", return_value=None):
        item_id = store.append(source="ext", url=TAOBAO_OK, title="t", seller_id="s-1")
        row = store.get(item_id, seller_id="s-1")
    assert json.loads(row["extra_json"])["vendor_sku"] == "123456789"


# ---------------------------------------------------------------------------
# ④ 목록이 등록 전에 말한다
# ---------------------------------------------------------------------------

def test_the_list_row_carries_the_identifier_state():
    """★ 화면 모델에 실린다 — 함수만 맞고 화면이 비면 소용없다."""
    import inspect
    from src.seller_console import views
    src = inspect.getsource(views._shape_collect_items)
    assert 'it["vendor_sku"]' in src and "vendor_sku_expected" in src


def test_old_rows_are_judged_now_not_trusted():
    """★ `vendor_sku`가 없던 옛 레코드는 **조회 시 계산한다**(스테일 값 신뢰 금지)."""
    import inspect
    from src.seller_console import views
    src = inspect.getsource(views._shape_collect_items)
    assert 'if not _vs and "vendor_sku" not in ex:' in src


def test_the_template_shows_the_badge():
    from pathlib import Path
    tpl = (Path(__file__).resolve().parents[1]
           / "src/seller_console/templates/collect_history_rows.html").read_text(encoding="utf-8")
    assert "식별자 없음" in tpl and "not it.vendor_sku" in tpl
    assert "it.vendor_sku_expected" in tpl, "무엇을 기대했는지 화면이 말하지 않는다"


# ---------------------------------------------------------------------------
# ⑤ 측정을 계약으로 굳힌다 (오너 가설이 아니었던 것들)
# ---------------------------------------------------------------------------

def test_the_url_regex_does_not_truncate_the_query():
    """★ 「쿼리가 잘리나」 — 안 잘린다. 그 사실을 굳혀 둔다(다음에 또 의심하지 않게)."""
    from src.collectors.share_text import _URL_RE, _clean_url
    got = _clean_url(_URL_RE.findall("【淘宝】" + TAOBAO_OK + "&ut_sk=abc 수행방패")[0])
    assert got.endswith("id=123456789&ut_sk=abc"), got


def test_the_extension_cannot_overwrite_the_stored_url():
    """★ 「확장 보강이 url을 덮나」 — 못 덮는다. 허용 필드에 `url`이 없다."""
    from src.seller_console import collect_history_store as store
    with patch.object(store, "_pg_backend", return_value=None):
        item_id = store.append(source="share", url=TAOBAO_OK, title="t", seller_id="s-2")
        store.update(item_id, seller_id="s-2", url="https://evil.example/x", title="t2")
        row = store.get(item_id, seller_id="s-2")
    assert row["url"] == TAOBAO_OK
    assert row["title"] == "t2", "허용 필드는 정상 갱신돼야 한다"


def test_a_known_item_id_is_stored_canonical():
    """★ 상품번호를 알면 **정규형으로** 저장한다 — 그래서 id 없는 행은 「몰랐던 행」이다."""
    from src.collectors.share_text import canonical_item_url
    assert canonical_item_url("123456789") == TAOBAO_OK


# ---------------------------------------------------------------------------
# ⑥ 진짜 근원 — 한 필드에 두 이름 (오너 실측 2026-09-20)
#
#   `vendor_sku('https://detail.tmall.com/item.htm?id=617129397971')` == `'617129397971'`.
#   규칙은 멀쩡했다. **주소가 페이로드에 없었다** — `ProductDraft.to_dict()`는
#   `source_url`을 내고 `url` 키를 **아예 안 만든다**. 페이로드를 만드는 자리는 전부
#   `product_data.get("url")`을 읽었다 → `''` → `vendor_sku("")` → 정직 중단.
#
#   ★★ 한 필드에 두 이름이 붙으면 쓰는 쪽과 읽는 쪽은 **반드시** 갈린다.
#      둘 다 정상으로 보이므로 사람은 못 본다 → **꺼내는 자리를 하나로** 만든다.
#      (F34-2의 사본 드리프트와 동형: 거기선 한 사실이 두 표에, 여기선 한 값이 두 이름에.)
# ---------------------------------------------------------------------------

TMALL = "https://detail.tmall.com/item.htm?id=617129397971"


def test_the_owner_measurement_reproduces():
    """★ 규칙은 멀쩡했다 — 오너가 직접 돌린 그 값을 그대로 박아 둔다."""
    from src.collectors.product_key import vendor_sku
    assert vendor_sku(TMALL) == "617129397971"


def test_the_draft_has_no_url_key_at_all():
    """★★ **F39의 진짜 근원** — 초안은 `source_url`만 낸다. `url`은 없다."""
    # 실명은 `Product`다 — 디스패처 docstring이 부르는 `ProductDraft`는 별칭이고,
    #   이름이 둘이라는 것 자체가 이번 사건의 냄새다(한 물건 두 이름).
    from src.listing.auto_publish import Product
    keys = Product(product_id="p1", title_ko="수행방패", source_url=TMALL).to_dict().keys()
    assert "source_url" in keys
    assert "url" not in keys, "초안에 url이 생겼다면 이 계약의 전제가 바뀐 것이다"


def test_draft_url_finds_the_address_whatever_its_name():
    """★★ 꺼내는 자리가 하나다 — 이름이 `url`이든 `source_url`이든 같은 값을 준다."""
    from src.seller_console.upload_dispatcher import draft_url
    assert draft_url({"source_url": TMALL}) == TMALL
    assert draft_url({"url": TMALL}) == TMALL
    assert draft_url({"product_url": TMALL}) == TMALL
    # `url`이 있으면 그게 우선이다(사람이 화면에서 고친 값).
    assert draft_url({"url": TMALL, "source_url": "https://old.example/x"}) == TMALL
    assert draft_url({"url": "", "source_url": TMALL}) == TMALL
    assert draft_url({}) == ""


def test_a_source_url_draft_now_yields_a_sku():
    """★★ **판정 지점** — `source_url`만 있는 초안이 SKU 게이트를 지난다."""
    from src.collectors.product_key import vendor_sku
    from src.listing.auto_publish import Product
    from src.seller_console.upload_dispatcher import draft_url

    payload = Product(product_id="p1", title_ko="수행방패", source_url=TMALL).to_dict()
    assert vendor_sku(payload.get("url") or "") == "", "전제: 옛 방식은 빈값이었다"
    assert vendor_sku(draft_url(payload)) == "617129397971"


def test_every_payload_builder_uses_the_one_place():
    """★ 페이로드를 만드는 자리들이 **전부** `draft_url`을 쓴다 — 한 곳만 고치면 또 갈린다."""
    import inspect
    from src.seller_console import upload_dispatcher as UD
    from src.seller_console import views

    for fn in (views._coupang_account_dispatch, views._smartstore_account_dispatch,
               views._woocommerce_dispatch):
        src = inspect.getsource(fn)
        assert 'product_data.get("url")' not in src, f"{fn.__name__}이 아직 한 이름만 읽는다"
        assert "draft_url(" in src, fn.__name__
    disp = inspect.getsource(UD.UploadDispatcher.dispatch)
    assert 'product_data.get("url"' not in disp and "draft_url(" in disp


def test_no_payload_reader_reads_url_alone():
    """★★ **스키마 순회 계약** — 초안이 안 내는 이름을 혼자 읽는 자리가 **하나도 없다**.

    이 계약이 이번 사건의 재발 감지기다. 새 어댑터가 `product_data.get("url")`을 쓰면
    **CI가 먼저 운다** — 라이브에서 「SKU 추출 실패」로 알게 되기 전에.
    """
    import ast
    from pathlib import Path

    from src.listing.auto_publish import Product
    from src.seller_console.upload_dispatcher import DRAFT_URL_KEYS

    draft_keys = set(Product(product_id="p", title_ko="t").to_dict().keys())
    # 초안이 내는 주소 이름이 하나라도 `DRAFT_URL_KEYS`에 있어야 폴백이 의미가 있다.
    assert draft_keys & set(DRAFT_URL_KEYS), (draft_keys, DRAFT_URL_KEYS)

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for rel in ("src/seller_console/views.py", "src/seller_console/upload_dispatcher.py",
                "src/pipeline/register_pipe.py", "src/pipeline/register_adapters.py"):
        p = root / rel
        if not p.exists():
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        # `draft_url` 본문은 **유일하게 허용된 자리**다(거기가 꺼내는 곳이니까).
        allowed = {n for fn in ast.walk(tree)
                   if isinstance(fn, ast.FunctionDef) and fn.name == "draft_url"
                   for n in ast.walk(fn)}
        for node in ast.walk(tree):
            if node in allowed or not isinstance(node, ast.Call):
                continue
            f = node.func
            if (isinstance(f, ast.Attribute) and f.attr == "get"
                    and isinstance(f.value, ast.Name) and f.value.id == "product_data"
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == "url"):
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, ("초안이 `url`을 안 낼 수 있다 — `draft_url()`을 쓰라: "
                           + ", ".join(offenders))
