"""T-S2(오너 2026-10-02 폰 등록) — 상세 본문: 가게 통계 줄 삭제 · 마켓엔 한국어만 · 가게 배너 어휘.

실측: 병기본(한국어+원문)에 「褶衣折扣店/4.8/88VIP好评率98%/平均12小时发货/客服平均10秒回复」가 원문·번역 두 벌로 실렸고,
드로어는 「병기본(한국어+원문) 전송」이라 안내했다. 상세 이미지 1장은 가게 배너(外贸尾单褶衣).

  1 `detail_drop_lines`(원격 JSON): 가게 줄을 원문·번역 모양 모두 뺀다 — `/`로 이어진 줄은 **걸린 조각만**
  2 마켓 상세 = 한국어만(병기 구분선 아래·한자만 남은 줄 버림) — 단건·일괄 같은 빌더(`build_dispatch_payload`)
  3 원문은 DB에 그대로(저장값 무변경) · 드로어 미리보기 = 등록이 보내는 그 함수 · 뺀 줄 수 표시
  4 이미지 판촉 판정 어휘에 折扣店·尾单·外贸(번역된 장의 OCR 글로 판정 — 번역 안 된 장은 글을 모른다: 정직)
"""
from __future__ import annotations

import json

SHOP_CN = "褶衣折扣店/4.8/88VIP好评率98%/平均12小时发货/客服平均10秒回复"
SHOP_KO = "주름옷 할인점 / 4.8 / 88VIP 호평률 98% / 평균 12시간 발송 / 고객 서비스 평균 10초 응답"


def test_shop_lines_drop_in_both_languages_keeping_product_segments():
    from src.collectors import ko_polish as kp
    kp.reset_cache()
    out, dropped = kp.drop_detail_lines(f"{SHOP_CN}\n소재: 폴리에스터\n{SHOP_KO}\n사이즈 / 프리 / 88VIP 전용")
    assert out == "소재: 폴리에스터\n사이즈 / 프리"
    assert len(dropped) == 11 and "88VIP 전용" in dropped


def test_market_description_is_korean_only():
    from src.seller_console.upload_dispatcher import market_description
    from src.seller_console.ai.translator import compose_bilingual
    bi = compose_bilingual(f"플리츠 셔츠\n{SHOP_KO}\n소재: 폴리에스터", f"三宅褶衣\n{SHOP_CN}\n面料：聚酯纤维")
    assert market_description(bi) == "플리츠 셔츠\n소재: 폴리에스터"
    assert market_description("面料：聚酯纤维\n소재: 폴리에스터") == "소재: 폴리에스터"   # 한자만 남은 줄은 안 나감
    assert market_description("Material: polyester") == "Material: polyester"          # 영어 원문은 그대로(번역 대상 아님)


def test_all_dispatch_paths_share_the_rule():
    from src.seller_console.upload_dispatcher import build_dispatch_payload
    extra = {"title": "t", "description": f"面料：聚酯纤维\n{SHOP_CN}", "description_ko": f"소재: 폴리에스터\n{SHOP_KO}"}
    pd = build_dispatch_payload(dict(extra), {"url": "https://item.taobao.com/item.htm?id=1"})   # 일괄 경로 모양
    assert pd["description"] == "소재: 폴리에스터"
    pd2 = build_dispatch_payload(dict(extra, description="직접 고친 한국어 상세"), None)            # 편집본이 이긴다
    assert pd2["description"] == "직접 고친 한국어 상세"
    assert extra["description"].startswith("面料")                                            # 원문 무변경


def test_drawer_preview_is_what_registration_sends():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    iid = S.append(source="extension", url="https://item.taobao.com/item.htm?id=2", seller_id="u-s2", title="t",
                   price="1", currency="CNY",
                   extra={"description": f"面料：聚酯纤维\n{SHOP_CN}", "description_ko": f"소재: 폴리에스터\n{SHOP_KO}"})
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = "u-s2"
    h = c.get(f"/seller/collect/preview/{iid}").get_data(as_text=True)
    assert "마켓 전송 미리보기 — 한국어만" in h and 'data-role="market-desc-dropped">가게 소개 줄 5개는 빼고 보내요' in h
    assert "병기본(한국어+원문)이 전송돼요" not in h
    ex = json.loads(S.get(iid, seller_ids={"u-s2"})["extra_json"])
    assert ex["description"].startswith("面料")                                               # 원문은 DB에 보관


def test_shop_banner_vocabulary_marks_translated_images_as_promo():
    from src.collectors import ko_polish as kp
    kp.reset_cache()
    assert set(kp.promo_hits("外贸尾单褶衣 折扣店")) >= {"外贸", "尾单", "折扣店"}
