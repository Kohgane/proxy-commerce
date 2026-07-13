"""tests/test_v63_field_loss_matrix.py — v63 STEP2: 필드 손실 지도 + 어댑터 품질 게이트.

저장된 collect_status만 집계(추측 0). 도메인별 [필드×tier×결과] 매트릭스 + 충족률.
디폴트 마켓 90% 미만 = '미완'(가짜 완료 서술 금지). 옵션은 존재 시만 분모(무옵션 미감점).
"""
from __future__ import annotations

from src.collectors.field_loss_matrix import (
    domain_of, item_completeness, build_field_loss_matrix, adapter_quality_gate,
    COMPLETE_THRESHOLD,
)


def test_domain_of():
    assert domain_of("https://www.amazon.com/dp/B0/ref=x") == "amazon"
    assert domain_of("https://www.amazon.co.jp/dp/B0") == "amazon"
    assert domain_of("https://www.temu.com/kr/g-601.html") == "temu"
    assert domain_of("https://yoshidakaban.com/products/x") == "yoshida"
    assert domain_of("https://unknown-shop.net/x") == "unknown-shop.net"


def _full_extra():
    return {
        "title": "제품 A", "price": "12000", "price_status": "",
        "images": ["a.jpg", "b.jpg", "c.jpg", "d.jpg"],
        "options": [{"name": "색상", "values": ["Black", "White"]}],
        "description": "이 제품은 원목으로 만든 튼튼한 책상입니다. 조립이 간편합니다.",
    }


def test_item_completeness_full():
    c = item_completeness(_full_extra())
    # 제목·가격·이미지≥3·옵션·상세 전부 → 5/5.
    assert c["filled"] == 5 and c["applicable"] == 5 and c["ratio"] == 1.0


def test_item_completeness_no_options_not_penalized():
    e = _full_extra(); e.pop("options")
    c = item_completeness(e)
    # 옵션 없으면 분모에서 제외(존재 시만) → 4/4 = 1.0 (무옵션 미감점).
    assert c["applicable"] == 4 and c["ratio"] == 1.0


def test_item_completeness_missing_images_and_price():
    e = {"title": "제품", "price": "", "price_status": "needs_check",
         "images": ["a.jpg"], "description": "짧음"}
    c = item_completeness(e)
    # 제목만 present(가격 needs_check·이미지<3·상세<20자·옵션없음) → 1/4.
    assert c["per_field"]["title"] is True
    assert c["per_field"]["price"] is False
    assert c["per_field"]["images3"] is False
    assert c["per_field"]["detail"] is False
    assert c["applicable"] == 4 and c["filled"] == 1


def test_matrix_groups_by_domain_and_tier():
    items = [
        {"url": "https://www.amazon.com/dp/B01/ref=x", "extra": {
            **_full_extra(),
            "collect_status": {"fields": [
                {"key": "price", "ok": True, "source": "Tier1(API/상태)"},
                {"key": "images", "ok": True, "source": "Tier2(DOM)"},
                {"key": "options", "ok": True, "source": "Tier2(DOM)"},
                {"key": "detail", "ok": True, "source": "Tier2(DOM)"},
            ]},
        }},
        {"url": "https://www.temu.com/g-1.html", "extra": {
            "title": "t", "price": "", "price_status": "needs_check", "images": ["x.jpg"],
            "description": "짧",
            "collect_status": {"fields": [
                {"key": "price", "ok": False, "source": "없음"},
                {"key": "images", "ok": True, "source": "Tier1(API/상태)"},
            ]},
        }},
    ]
    m = build_field_loss_matrix(items)
    doms = {d["domain"]: d for d in m["domains"]}
    assert "amazon" in doms and "temu" in doms
    assert m["total_items"] == 2
    # amazon: 필드별 tier 집계.
    az = doms["amazon"]
    assert az["field_source"]["price"]["Tier1(API/상태)"] == 1
    assert az["field_present"]["images"] == 1
    # amazon 완비 → complete True '완료'; temu 결손 → complete False '미완'.
    assert az["complete"] is True and az["status"] == "완료"
    assert doms["temu"]["complete"] is False and doms["temu"]["status"] == "미완"


def test_adapter_gate_flags_incomplete():
    # amazon 3건 중 2건 결손 → 충족률 < 90% → 미완.
    items = [
        {"url": "https://www.amazon.com/dp/B0%d/ref=x" % i, "extra": (
            _full_extra() if i == 0 else
            {"title": "t", "price": "", "price_status": "needs_check", "images": [], "description": "짧"}
        )} for i in range(3)
    ]
    gate = adapter_quality_gate(items)
    az = [g for g in gate if g["adapter"] == "amazon"][0]
    assert az["complete"] is False and az["status"] == "미완"
    assert az["completeness"] < COMPLETE_THRESHOLD
    assert "price" in az["weak_fields"] and "images3" in az["weak_fields"]


def test_yoshida_is_control_not_gated():
    items = [{"url": "https://yoshidakaban.com/products/x", "extra": {"title": "t", "price": "", "images": []}}]
    m = build_field_loss_matrix(items)
    y = [d for d in m["domains"] if d["domain"] == "yoshida"][0]
    assert y["is_default_market"] is False and y["status"] == "대조군"
    # 게이트는 디폴트 마켓만 → 요시다 미포함.
    assert all(g["adapter"] != "yoshida" for g in adapter_quality_gate(items))


def test_field_loss_route_registered(flask_client):
    # 미인증 시 401(auth 게이트), 스코프 본인만.
    r = flask_client.get("/seller/collect/field-loss")
    assert r.status_code in (200, 401)
    if r.status_code == 200:
        j = r.get_json()
        assert "matrix" in j and "adapter_gate" in j
