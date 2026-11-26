"""오너 11-26 저녁 ① — 오너 탭 줄이기 계약.

「다시 가져오기」가 끝나면 카드에 결과 한 줄(사진 전→후 · 잰 크기 · 옵션가) · 이미 스스에 올라간 상품이면 그 아래
「바뀐 사진을 스스에 다시 보내기」(두 번 눌러야 보냄 · 서버도 confirm 없으면 거부). 흐린 사진으로 올라간 상품은 서버가 찾아
목록 맨 위 「사진 고칠 상품 N건」 묶음으로. 크기는 **잰 장만** 말한다 · 마켓에는 묻지 않는다.
"""
from __future__ import annotations

import json

import pytest

BIG = "https://m.media-amazon.com/images/I/81a._AC_SL1500_.jpg"
TINY = "https://m.media-amazon.com/images/I/81a._AC_US40_.jpg"


def _ex(**kw):
    e = {"images": [BIG, BIG], "uploaded": [{"market": "smartstore:chezgoga", "product_id": "111", "at": "2026-11-20T00:00:00+00:00"}]}
    e.update(kw)
    return e


def _rec(at="2026-11-26T08:00:00+00:00", ok=True, before=(14, 2), after=(11, 11), sizes=None):
    a = {"images": after[0], "usable": after[1]}
    if sizes is not None:
        a["sizes"] = sizes
    return {"at": at, "ok": ok, "before": {"images": before[0], "usable": before[1]}, "after": a}


def test_url_small_only_where_measured_tokens_exist():
    from src.services.photo_fix import url_small
    assert url_small(TINY) is True and url_small(BIG) is False
    assert url_small("https://ae01.alicdn.com/kf/S1.jpg_480x480q75.jpg_.avif") is True
    assert url_small("https://ae01.alicdn.com/kf/S1.jpg_800x800q75.jpg_.avif") is False
    assert url_small("https://img.kwcdn.com/p/1.jpg?imageView2/2/w/180/q/70") is True
    assert url_small("https://shop.example.com/a.jpg") is None                       # 주소로는 모름 — 판정하지 않는다


def test_measure_counts_only_measured_and_line_never_overclaims():
    from src.services import photo_fix as PF
    sizes = {"a": 1500, "b": 1200, "c": 0}
    sz = PF.measure(["a", "b", "c"], size_of=lambda u: {"long_side": sizes[u]})
    assert sz == {"n": 3, "measured": 2, "failed": 1, "min": 1200, "max": 1500, "under": 0}
    line = PF.refetch_line({"amazon_refetch": _rec(sizes=sz), "sku_fill": {"state": "done", "priced": 12, "missing": 0}})
    assert line == "사진 14→11장 · 잰 2장 전부 긴 변 1000px 넘어요 · 1장은 못 잼 · 옵션가 12개"
    small = PF.refetch_line({"amazon_refetch": _rec(sizes={"n": 2, "measured": 2, "failed": 0, "min": 300, "max": 450, "under": 2})})
    assert "전부 500px 미만(가장 큰 장 450px)" in small
    assert PF.refetch_line({"amazon_refetch": _rec(ok=False) | {"reason": "아마존 화면을 읽지 못했어요"}}).startswith("다시 가져오지 못했어요 — 아마존")


def test_resend_targets_after_upload_only_and_not_twice():
    from src.services import photo_fix as PF
    ex = _ex(amazon_refetch=_rec())
    assert [t["market"] for t in PF.resend_targets(ex)] == ["smartstore:chezgoga"]
    ex["uploaded"][0]["photo_resent"] = {"at": "2026-11-26T09:00:00+00:00"}
    assert PF.resend_targets(ex) == []                                                  # 이미 다시 보냄
    late = _ex(amazon_refetch=_rec())
    late["uploaded"][0]["at"] = "2026-11-26T10:00:00+00:00"
    assert PF.resend_targets(late) == []                                                # 다시 가져온 뒤에 올린 등록본
    still_small = _ex(amazon_refetch=_rec(sizes={"n": 2, "measured": 2, "min": 300, "max": 450, "under": 2}))
    assert PF.resend_targets(still_small) == []                                         # 보내도 흐리다
    assert PF.resend_targets({"amazon_refetch": _rec()}) == []                          # 스스에 안 올린 상품


def test_judge_and_bundle():
    from src.services import photo_fix as PF
    ready = _ex(amazon_refetch=_rec())
    small = _ex(images=[TINY, TINY])
    fine = _ex()
    fixed = _ex(amazon_refetch=_rec())                                                  # 다시 가져온 뒤 이미 다시 보냄
    fixed["uploaded"][0]["photo_resent"] = {"at": "2026-11-26T09:00:00+00:00"}
    tiny_again = _ex(images=[TINY], amazon_refetch=_rec(after=(1, 0)))                 # 다시 가져와도 작은 판뿐
    assert PF.resend_targets(tiny_again) == [] and PF.judge(tiny_again)["state"] == "small"
    assert "사진을 직접 올린 뒤" in PF.judge(tiny_again)["line"]
    assert PF.judge(ready)["state"] == "ready" and PF.judge(small)["state"] == "small"
    assert PF.judge(fine) is None and PF.judge(fixed) is None and PF.judge({"images": [TINY]}) is None
    rows = [{"id": i, "extra_json": json.dumps(e)} for i, e in enumerate([ready, small, fine])]
    b = PF.bundle(rows, lambda it: json.loads(it["extra_json"]))
    assert b == {"n": 2, "ready": 1, "small": 1, "ids": ["0", "1"]}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SELLER_CONSOLE_AUTH", "0")
    from src.order_webhook import app
    from src.seller_console import views as V
    V._PHOTO_FIX_CACHE.clear()
    app.config["TESTING"] = True
    return app.test_client()


def _row(ex):
    from src.seller_console import collect_history_store as S
    return S.append(source="share", url="https://www.amazon.com/dp/B0C38WV1F6", title="OKNIFE", price="36372", currency="KRW",
                    image="", seller_id="default", extra=ex)


def test_card_result_line_and_two_tap_resend(client):
    iid = _row(_ex(title_ko="OKNIFE 칼", amazon_refetch=_rec(sizes={"n": 11, "measured": 11, "failed": 0, "min": 1070, "max": 1500, "under": 0}),
                   sku_fill={"state": "done", "priced": 5, "missing": 0}))
    h = client.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert 'data-role="m5-refetch-result"' in h and "사진 14→11장 · 잰 11장 전부 긴 변 1000px 넘어요 · 옵션가 5개" in h
    assert 'data-role="m5-photo-resend" data-market="smartstore:chezgoga"' in h and "에 다시 보내기" in h
    assert "한 번 더 누르면 스스 사진을 바꿔요" in h                                      # 첫 탭은 확인 글
    r = client.post(f"/seller/collect/{iid}/naver-resend-photos", json={"market": "smartstore:chezgoga"})
    assert r.status_code == 400                                                         # confirm 없이는 서버도 안 보냄
    d = client.get(f"/seller/collect/{iid}/refetch-result?since=2026-11-26T07:59:00").get_json()
    assert d["done"] and d["resend"][0]["market"] == "smartstore:chezgoga" and "옵션가 5개" in d["line"]
    assert not client.get(f"/seller/collect/{iid}/refetch-result?since=2026-11-26T08:30:00").get_json()["done"]


def test_list_bundle_and_filter(client):
    a = _row(_ex(title_ko="흐린 사진 상품", images=[TINY, TINY]))
    b = _row(_ex(title_ko="멀쩡한 상품"))
    h = client.get("/seller/collect/history").get_data(as_text=True)
    assert 'data-role="photo-fix-bundle"' in h and "사진 고칠 상품" in h and "사진부터 다시 가져오기" in h
    h = client.get("/seller/collect/history?photo=1&days=365").get_data(as_text=True)
    assert a in h and b not in h


def test_filter_funnel_uses_measured_fullsize_rules_only():
    """⑤ 수집 깔때기(서버 수집기·확장 병합 공용)가 알리·테무 썸네일만 원본으로 바꾸고, 썸네일+원본 두 장은 한 장으로."""
    from src.collectors.universal_scraper import filter_product_images
    ali_t = "https://ae01.alicdn.com/kf/S12ab.jpg_480x480q75.jpg_.avif"
    ali_f = "https://ae01.alicdn.com/kf/S12ab.jpg"
    temu_t = "https://img.kwcdn.com/product/fancy/abc.jpg?imageView2/2/w/180/q/70/format/webp"
    amz = "https://m.media-amazon.com/images/I/71abc._AC_US40_.jpg"
    rak = "https://tshop.r10s.jp/shop/cabinet/x.jpg?fitin=270:270"
    out = filter_product_images([ali_t, ali_f, temu_t, amz, rak])
    assert out[0] == ali_f and ali_t not in out and out.count(ali_f) == 1
    assert "https://img.kwcdn.com/product/fancy/abc.jpg" in out
    assert amz in out and rak in out                                                   # 실측 근거 없는 소싱처는 그대로
