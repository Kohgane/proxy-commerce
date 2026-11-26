"""오너 11-26 진단 캡처 판정 1 — 아마존 사진은 img 태그가 아니라 페이지의 사진 데이터에서. 계약.

표본 행 b6809323(tomtoc · 공유): images 14 = `_AC_US40_` 40px 6 · `_AC_SY300_SX300_` 1 · SX522 1 · 배지 svg 3 · `_SS100_` 1 ·
`images-na` 추천 2 · 옵션 0 · 상세 0. → 페이지 데이터(colorImages hiRes)만 · 버릴 것 다 버림 · 옵션·가격·A+ 같은 응답에서 ·
1MB에서 끊지 않음 · 못 읽으면 사진 비움(img로 메우지 않음) · 그 행 같은 것은 「수집이 덜 됐어요」 · 「다시 가져오기」는 서버가 바로.
"""
from __future__ import annotations

import json

import pytest

M = "https://m.media-amazon.com/images/I/"
JUNK_IMGS = "".join([
    *[f'<img src="{M}31Thumb{i}._AC_US40_.jpg">' for i in range(6)],
    f'<img src="{M}41Mid._AC_SY300_SX300_.jpg">',
    f'<img src="{M}71Big._AC_SX522_.jpg">',
    *[f'<img src="https://m.media-amazon.com/images/S/sash/badge{i}.svg">' for i in range(3)],
    f'<img src="{M}51Ss._SS100_.jpg">',
    '<img src="https://images-na.ssl-images-amazon.com/images/I/61Rec._AC_UL116_SR116,116_.jpg">' * 2,
])
COLOR = [
    {"hiRes": M + "71Big._AC_SL1500_.jpg", "thumb": M + "31Thumb0._AC_US40_.jpg", "large": M + "41Big._AC_.jpg",
     "main": {M + "71Big._AC_SX679_.jpg": [679, 1200]}, "variant": "MAIN"},
    {"hiRes": None, "thumb": M + "31Thumb1._AC_US40_.jpg", "large": M + "41Second._AC_.jpg",
     "main": {M + "41Second._AC_SX522_.jpg": [522, 927]}, "variant": "PT01"},
    {"hiRes": M + "71Big._AC_SL1500_.jpg", "thumb": "", "large": "", "variant": "PT02"},       # 같은 사진 ID — 한 번만
    {"hiRes": "https://m.media-amazon.com/images/S/sash/x.svg", "variant": "PT03"},            # 배지 — 버림
]
TWISTER = ('"dimensions" : ["size_name","color_name"], "dimensionsDisplay" : ["Size","Color"], '
           '"variationValues" : {"size_name":["40L","30L"],"color_name":["Black","Grey"]}, "asin":"B0X"')
APLUS = ('<div id="aplus"><img data-src="https://m.media-amazon.com/images/S/aplus-media-library-service-media/a1.jpg">'
         '<img src="https://m.media-amazon.com/images/S/aplus-media/sota/grey-pixel.gif"></div><div id="aplus_feature_div_end"></div>')


def _page(pad=0, with_data=True):
    data = (f"<script>P.when('A').register('ImageBlockATF', function(A){{ var data = {{ 'colorImages': {{ 'initial': {json.dumps(COLOR)} }}, "
            f"'colorToAsin': {{}} }}; }});</script><script>var t = {{ {TWISTER} }};</script>"
            '<div id="corePrice_feature_div"><span class="a-offscreen">$129.28</span></div>'
            '<script>var p = {"priceAmount":129.28,"currencyCode":"USD"};</script>' + APLUS) if with_data else ""
    return ("<html><head><title>Amazon.com: tomtoc</title></head><body><span id=\"productTitle\">tomtoc Travel Backpack 40L</span>"
            + JUNK_IMGS + ("<!--" + "x" * pad + "-->" if pad else "") + data
            + '<div id="feature-bullets"><ul><li><span class="a-list-item"> 40L carry-on size </span></li></ul></div></body></html>')


URL = "https://www.amazon.com/dp/B0D1TOMTOC"


def test_images_come_from_page_data_not_img_tags():
    from src.collectors.universal_scraper import UniversalScraper
    r = UniversalScraper().parse_html(_page(), URL)
    assert r.images == [M + "71Big._AC_SL1500_.jpg", M + "41Second._AC_SX522_.jpg"]      # hiRes → main 최대판(→ large) · ID 중복 1회
    assert not any(x in " ".join(r.images) for x in ("_AC_US40_", ".svg", "/images/S/", "images-na", "_SS100_"))
    assert r.raw_meta["amazon_pdp"]["image_source"] == "colorImages"


def test_options_price_aplus_from_same_page():
    from src.collectors.universal_scraper import UniversalScraper
    r = UniversalScraper().parse_html(_page(), URL)
    assert r.options == [{"name": "Size", "values": ["40L", "30L"]}, {"name": "Color", "values": ["Black", "Grey"]}]
    assert str(r.price) == "129.28" and r.currency == "USD"
    assert r.raw_meta["detail_images"] == ["https://m.media-amazon.com/images/S/aplus-media-library-service-media/a1.jpg"]
    assert "40L carry-on size" in r.description


def test_no_page_data_means_no_photos_not_thumbnails():
    from src.collectors.universal_scraper import UniversalScraper
    r = UniversalScraper().parse_html(_page(with_data=False), URL)
    assert r.images == [] and r.raw_meta["amazon_pdp"]["image_source"] == ""


def test_dynamic_image_fallback_takes_largest():
    from src.collectors import amazon_pdp as A
    dyn = {M + "61Land._AC_SX300_.jpg": [300, 300], M + "61Land._AC_SL1500_.jpg": [1500, 1500]}
    h = '<img id="landingImage" data-a-dynamic-image="' + json.dumps(dyn).replace('"', "&quot;") + '">'
    assert A.gallery(h) == {"images": [M + "61Land._AC_SL1500_.jpg"], "source": "dynamic-image"}


def test_fetch_reads_past_one_megabyte_for_amazon(monkeypatch):
    import requests
    from src.collectors import universal_scraper as U
    body = _page(pad=1_500_000).encode()
    seen = {}

    class R:
        apparent_encoding = "utf-8"

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=65536):
            for i in range(0, len(body), chunk_size):
                yield body[i:i + chunk_size]

    def _get(url, headers=None, **kw):
        seen.update(headers or {})
        return R()
    monkeypatch.setattr(U, "_DRY_RUN", False)
    monkeypatch.setattr(requests, "get", _get)
    r = U.UniversalScraper().fetch(URL)
    assert len(body) > 1_000_000 and r.images[0] == M + "71Big._AC_SL1500_.jpg"
    assert seen.get("Accept-Encoding") == "gzip, deflate" and seen["Accept-Language"].startswith("en-US")


def test_usable_photo_by_url():
    from src.collectors.amazon_pdp import usable_photo as u
    assert not u(M + "31a._AC_US40_.jpg") and not u(M + "41a._AC_SY300_SX300_.jpg") and not u(M + "51a._SS100_.jpg")
    assert not u("https://m.media-amazon.com/images/S/sash/b.svg") and not u("https://images-na.ssl-images-amazon.com/images/I/6._AC_UL116_SR116,116_.jpg")
    assert u(M + "71a._AC_SX522_.jpg") and u(M + "71a._AC_SL1500_.jpg") and u(M + "71a.jpg")
    assert u("https://img.alicdn.com/x_60x60.jpg")                                         # 아마존이 아니면 판정 안 함


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    app.config["TESTING"] = True
    return app.test_client()


_SAMPLE_JUNK = [M + f"31T{i}._AC_US40_.jpg" for i in range(6)] + [M + "41M._AC_SY300_SX300_.jpg",
               "https://m.media-amazon.com/images/S/sash/a.svg", M + "51S._SS100_.jpg"]


def _row(**ex):
    from src.seller_console import collect_history_store as S
    e = {"title_ko": "tomtoc 여행 백팩 40L", "images": list(_SAMPLE_JUNK), "price": "129.28", "currency": "USD", "mode": "share"}
    e.update(ex)
    return S.append(source="share", url=URL, title="tomtoc", price="129.28", currency="USD", image=_SAMPLE_JUNK[0],
                    seller_id="default", extra=e)


def test_card_says_half_collected_when_only_thumbnails(client):
    iid = _row()
    h = client.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-code="no_photos"' in h and "쓸 만한 사진이 없어요(사진 9장 모두 썸네일·배지예요)" in h


def test_refetch_merges_new_photos_options_and_records_before_after(monkeypatch):
    from src.collectors.universal_scraper import UniversalScraper
    from src.seller_console import collect_history_store as S
    from src.services import amazon_refetch as AR
    iid = _row()
    out = AR.run(iid, {"default"}, fetch=lambda u: UniversalScraper().parse_html(_page(), u))
    assert out["ok"] and out["before"] == {"images": 9, "usable": 0, "options": 0, "detail": 0}
    assert out["after"]["images"] == 2 and out["after"]["usable"] == 2 and out["after"]["options"] == 2 and out["after"]["source"] == "colorImages"
    ex = json.loads(S.get(iid, seller_id="default")["extra_json"])
    assert ex["images"][0].endswith("._AC_SL1500_.jpg") and ex["options"][0]["name"] == "Size" and len(ex["detail_images"]) == 1
    assert ex["amazon_refetch"]["ok"] is True


def test_refetch_without_data_keeps_old_and_says_why():
    from src.collectors.universal_scraper import UniversalScraper
    from src.seller_console import collect_history_store as S
    from src.services import amazon_refetch as AR
    iid = _row()
    out = AR.run(iid, {"default"}, fetch=lambda u: UniversalScraper().parse_html(_page(with_data=False), u))
    assert out["ok"] is False and "사진은 그대로" in out["reason"]
    assert json.loads(S.get(iid, seller_id="default")["extra_json"])["images"] == _SAMPLE_JUNK


def test_refetch_keeps_manual_photos():
    from src.collectors.universal_scraper import UniversalScraper
    from src.seller_console import collect_history_store as S
    from src.services import amazon_refetch as AR
    mine = ["https://res.cloudinary.com/x/mine.jpg"]
    iid = _row(images=mine, manual_fields={"images": "2026-11-26T00:00:00+00:00"})
    AR.run(iid, {"default"}, fetch=lambda u: UniversalScraper().parse_html(_page(), u))
    assert json.loads(S.get(iid, seller_id="default")["extra_json"])["images"] == mine


def test_recollect_button_runs_server_refetch_for_amazon(client, monkeypatch):
    from src.utils import bg_job
    started = []
    monkeypatch.setattr(bg_job, "start", lambda name, fn: (started.append(name) or True, {}))
    iid = _row()
    d = client.post(f"/seller/collect/{iid}/recollect", json={"mode": "queue"}).get_json()
    assert d["ok"] and d["server_refetch"] and started == [f"amazon-refetch:{iid}"] and "다시 읽고 있어요" in d["message"]


def test_krw_price_without_currency_code_is_krw_not_usd():
    """실측 11-26(한국 배송지 화면): `priceAmount` 107002.62 · `currencyCode` 없음 · 글자 `KRW107,003` → KRW."""
    from src.collectors import amazon_pdp as A
    from src.collectors.universal_scraper import UniversalScraper
    h = ('<span id="productTitle">x</span><script>var a = {"priceAmount":107002.62};</script>'
         '<div id="corePrice_feature_div"><span class="a-offscreen">KRW107,003</span></div>')
    assert A.price(h) == {"price": "107002.62", "currency": "KRW", "source": "priceAmount"}
    r = UniversalScraper().parse_html(h, URL)
    assert r.currency == "KRW" and str(r.price) == "107002.62"


def test_price_with_unknown_currency_is_not_used():
    from src.collectors.universal_scraper import UniversalScraper
    r = UniversalScraper().parse_html('<span id="productTitle">x</span><script>{"priceAmount":12.5}</script>', URL)
    assert r.raw_meta["amazon_pdp"]["price_source"] == "priceAmount" and str(r.price or "") != "12.5"


def test_aplus_comparison_icons_dropped():
    from src.collectors import amazon_pdp as A
    big = "https://m.media-amazon.com/images/S/aplus-media-library-service-media/ba68.__CR0,0,1464,600_PT0_SX1464_V1___.jpg"
    h = ('<div id="aplus"><img src="' + big + '"><img src="https://m.media-amazon.com/images/S/aplus-media-library-service-media/de71.__CR0,0,315,145_PT0_SX315_V1___.jpg">'
         '<img src="https://m.media-amazon.com/images/S/aplus-media-library-service-media/47a4.__AC_SR166,182___.jpg"></div><div id="aplus_feature_div_end"></div>')
    assert A.aplus_images(h) == [big]


def test_options_without_dimensions_display_use_korean_names():
    """실측 11-26: `dimensionsDisplay`가 없는 화면 — 키 이름(size_name·color_name)을 한국어로."""
    from src.collectors import amazon_pdp as A
    h = '"variationValues" : {"size_name": ["28L", "40L"], "color_name": ["Black", "Green-ripstop"]}, "x": 1'
    assert A.options(h) == [{"name": "사이즈", "values": ["28L", "40L"], "dim": "size_name"},
                            {"name": "색상", "values": ["Black", "Green-ripstop"], "dim": "color_name"}]


def test_card_flags_mostly_junk_rows_like_b6809323(client):
    """표본 b6809323: 14장 중 쓸 만한 판 1장(SX522) — 옛 수집기 행은 「수집이 덜 됐어요」로 다시 가져오게."""
    sample = _SAMPLE_JUNK + [M + "71Big._AC_SX522_.jpg"]
    iid = _row(images=sample)
    h = client.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-code="no_photos"' in h and f"사진 {len(sample)}장 중 쓸 만한 건 1장이에요" in h
    good = _row(images=[M + "71A._AC_SL1500_.jpg", M + "71B._AC_SL1500_.jpg", M + "31T._AC_US40_.jpg"])
    assert 'data-code="no_photos"' not in client.get(f"/seller/m/item/{good}").get_data(as_text=True)



def test_real_page_form_parsejson_string():
    """실측(AMZIMG2 11-26): 실제 화면은 `'colorImages': { 'initial': A.$.parseJSON('[…]') }` — 배열이 JS 문자열 안에 있다.
    hiRes(1070×1428~1500×1500 실측)를 고르고, hiRes가 없으면 main 최대판(679) — large(338~500)는 마지막."""
    from src.collectors import amazon_pdp as A
    arr = [{"hiRes": M + "81zKIbbQahL._AC_SL1500_.jpg", "thumb": M + "31g6QEu1v7L._AC_US40_.jpg", "large": M + "31g6QEu1v7L._AC_.jpg",
            "main": {M + "81zKIbbQahL._AC_SX679_.jpg": [679, 906]}, "variant": "MAIN"},
           {"hiRes": None, "thumb": M + "414tuquNi2L._AC_US40_.jpg", "large": M + "414tuquNi2L._AC_.jpg",
            "main": {M + "414tuquNi2L._AC_SX679_.jpg": [679, 850]}, "variant": "PT01", "note": "it's"}]
    raw = json.dumps(arr).replace("'", "\\'")
    h = ("P.when('A').register(\"ImageBlockATF\", function(A){ var data = { 'isMediaBlock': true, "
         "'colorImages': { 'initial': A.$.parseJSON('" + raw + "')}, 'colorToAsin': {} }; });")
    assert A.gallery(h) == {"images": [M + "81zKIbbQahL._AC_SL1500_.jpg", M + "414tuquNi2L._AC_SX679_.jpg"], "source": "colorImages"}
