"""Y13-G 5(오너 2026-10-20) — 판촉 제외 사진 규칙: **대표·상세 모두 제외**, 드로어는 「제외 · 판촉」 + 「그래도 넣기」.

피샹리 1번째 사진(로고 菲尚丽家 + 판촉 6줄)은 대표에서도 상세에서도 빠졌다 — 오너 결정으로 그게 규칙이다(넘김은 이 제외를 풀지 않는다).
"""
from src.services import image_translate_store as store
from tests.test_t3_promo_images import PLAIN, PROMO, _extra


def test_promo_photo_is_out_of_rep_and_detail_and_drawer_says_so():
    ex = _extra(PROMO, PLAIN)
    ex["detail_images"] = ["https://img.example/d0.jpg"]
    gal = store.effective_images(ex)
    det = store.effective_images(ex, kind="detail")
    promo_urls = {"https://cdn.example/p0.jpg", "https://img.example/0.jpg"}       # 번역본·원본 둘 다
    assert gal[0] == "https://cdn.example/p1.jpg"                                   # 대표 = 판촉 아닌 첫 장
    assert not promo_urls & set(gal) and not promo_urls & set(det)                  # 대표·갤러리·상세 어디에도 없다
    plan = store.effective_plan(ex)
    assert plan[0]["promo_excluded"] is True
    ex["images_ko"] = store.set_promo_include(ex, 0, True)                          # 「그래도 넣기」
    assert store.effective_images(ex)[0] == "https://cdn.example/p0.jpg"
    t = open("src/seller_console/templates/collect_preview.html", encoding="utf-8").read()
    js = t.split('data-role="imgko-promo"')[1][:600]
    assert "제외 · 판촉" in js and "그래도 넣기" in js and "대표·상세 모두에서 뺍니다" in js
