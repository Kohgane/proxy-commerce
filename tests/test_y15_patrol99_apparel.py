"""순찰 99(2026-10-25 고우주 원피스 `5d1b6679` 운영 실측) — 의류 사이즈표가 만든 두 가지 틀린 값.

① 배송: 상세 1 사이즈표의 몸무게(「发发170cm/49kg」 모델 신체 · 「110-120kg」 권장 체중 구간)를 상품 무게로 읽어
   「실중량 49kg → 135kg ≥ 20kg · 대형화물(경동택배 별도)」 — 원피스가 대형화물로 등록될 뻔했다.
② 사진 글자: 텐센트가 「80-105斤」을 「80-105kg」으로(斤=500g을 환산하지 않고 단위만), AI 다듬기는 「80-105근」으로 —
   둘 다 손님이 보면 틀린 숫자. 斤 상자는 규칙으로 kg 환산(40~52.5kg).
"""
from __future__ import annotations

import pytest

SIZE_CHART = ("肩宽39 胸围80 腰围6 36 150-160 80-105kg 38 155-162 105-110근 40 162-167 110-120kg 42 167-173 120-135kg "
              "发发170cm/49kg/全店38码 手工测量可能有1-3cm误差")


def test_body_weights_are_not_product_weight():
    from src.seller_console import shipping_ratio as R
    size = R._read_size({"title": "실크 원피스", "photo_text": SIZE_CHART})
    assert size["weight_kg"] == 0.0 and size["dims_cm"] is None


@pytest.mark.parametrize("text,want", [
    ("净重 1.2kg 发发170cm/49kg", 1.2),                           # 모델 신체는 지우고 순중량은 읽는다
    ("适用体重 45-55kg 产品重量 3kg", 3.0),                         # 체중 구간(하중 낱말 + 구간)도 지운다
    ("毛重 2.5kg 最大承重 200kg", 2.5),                             # 기존(10-22 소파) 그대로
    ("重量 0.8kg 建议体重 80-120斤", 0.8),                           # 斤 구간은 애초에 kg이 아니다
])
def test_single_product_weight_survives(text, want):
    from src.seller_console import shipping_ratio as R
    assert R._read_size({"title": "x", "photo_text": text})["weight_kg"] == want


def test_estimate_dress_is_not_bulky():
    from src.seller_console import shipping_ratio as R
    pd = {"title": "타파파 실크 원피스", "price": "1058", "currency": "CNY", "photo_text": SIZE_CHART}
    est = R.estimate(pd, seller_id="", market="coupang")
    assert est["state"] != "bulky", est.get("line")


@pytest.mark.parametrize("src,tgt,want", [
    ("80-105斤", "80-105kg", "40~52.5kg"),
    ("120-135斤", "120-135근", "60~67.5kg"),
    ("80-105斤", "80~105 kg", "40~52.5kg"),
    ("适合体重90斤以内", "체중 90kg 이내", "체중 45kg 이내"),
    ("衣长", "의장", "의장"),                                        # 斤 없음 — 손대지 않는다(용어집은 따로)
    ("净重500g", "순중량 500g", "순중량 500g"),
])
def test_fix_jin_converts_to_kg(src, tgt, want):
    from src.services import image_polish as P
    assert P.fix_jin(src, tgt) == want


def test_check_accepts_converted_numbers():
    from src.services import image_polish as P
    assert P.check("80-105斤", "80-105kg", "40~52.5kg") == ""   # 원문 숫자 80·105가 없어도 환산값이라 통과
    assert "숫자 누락" in P.check("80-105斤 配3件", "80-105kg 3개 포함", "40~52.5kg")   # 斤 아닌 숫자(3)는 여전히 지킨다


def test_polish_boxes_jin_rows_skip_ai(monkeypatch):
    from src.services import image_polish as P
    called = []
    monkeypatch.setattr(P, "_ask", lambda rows, ctx, terms: called.append([r["id"] for r in rows]) or {"got": {}, "error": "", "capped": False})
    from src.ai import llm
    monkeypatch.setattr(llm, "anthropic_ready", lambda: True)
    out = P.polish_boxes([{"id": "t0", "src": "80-105斤", "tgt": "80-105kg"},
                          {"id": "t1", "src": "衣长", "tgt": "의장"}], {"outbound": True, "rule": None})
    rows = {r["id"]: r for r in out["rows"]}
    assert rows["t0"]["ko"] == "40~52.5kg" and rows["t0"]["from"] == "glossary"
    assert all("t0" not in ids for ids in called)                 # 斤 상자는 AI에 안 묻는다
    assert rows["t1"]["glossary"] == "총장"                        # 용어집: 衣长 → 총장


def test_apparel_glossary_terms():
    from src.services import image_polish as P
    assert P.apply_glossary("衣长", "의장") == "총장"
    assert P.apply_glossary("均码", "균일 코드") == "프리사이즈"
    assert P.apply_glossary("肩宽", "견폭") == "어깨너비"
    assert P.apply_glossary("发发170cm/49kg/全店38码", "발발 170cm/49kg/전점 38 사이즈") == "발발 170cm/49kg/전 상품 38 사이즈"
