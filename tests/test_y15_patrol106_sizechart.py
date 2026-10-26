"""순찰 106-E(오너 2026-10-26) — 사이즈표 번역 체인(원문 → 텐센트 → 다듬기 → 최종) 표본에서 나온 틀린 패턴을 규칙으로.

운영 표본(10-26): 의류 사이즈표 OCR이 있는 상품은 2건(5d1b6679 · c44dde91) + 치수 옵션 상품 9건.
  - 「发发170cm/49kg/全店38码」 → 「발발 170cm/49kg/전점 38사이즈」 (모델 별명 음차 · 「全店」 직역)
  - 옵션 「S码」·「36码」 → 못 옮김(용어집에 없음) · 「XL(建议120-140斤)」 → 「建议」 남음
  - 「超级大号」 → 「超级 대형」 · 「纯白」 → 「纯 화이트」 · 「内衬」(안감) → 텐센트 「내부 쉬이」
"""
import pytest


@pytest.mark.parametrize("src,want", [
    ("S码", "S"), ("36码", "36"), ("红色M码", "레드 M"),
    ("XL(建议120-140斤)", "XL(권장 60~70kg)"),
    ("135x115cm 超级大号", "135x115cm 특대형"),
    ("纯白（50*40*90cm）", "퓨어 화이트 (50*40*90cm)"),
    ("38码 全店", "38"),
])
def test_size_option_values_resolve_by_rule(src, want):
    from src.collectors.ko_polish import option_value
    r = option_value(src)
    assert r["value"] == want and r["left"] == ""


def test_size_suffix_rule_does_not_eat_words():
    from src.collectors.ko_polish import option_value
    assert "码" in option_value("码数说明")["draft"] or option_value("码数说明")["left"]   # 「码」로 시작하는 낱말은 그대로(한자 남음 → 보류)


@pytest.mark.parametrize("src,want", [
    ("发发170cm/49kg/全店38码", "모델 170cm · 49kg · 38 사이즈 착용"),
    ("模特:168cm/45kg/S码", "모델 168cm · 45kg · S 사이즈 착용"),
    ("170cm/98斤/M", "모델 170cm · 49kg · M 사이즈 착용"),
    ("身高168cm", ""), ("胸围80", ""), ("肩宽39", ""),
])
def test_model_caption_line(src, want):
    from src.services.image_polish import fix_model_line
    assert fix_model_line(src) == want


def test_polish_takes_the_rule_for_the_caption_without_asking_ai(monkeypatch):
    from src.ai import llm
    from src.services import image_polish as P
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(AssertionError("AI에 묻지 않는다")))
    out = P.polish_boxes([{"id": "t32", "src": "发发170cm/49kg/全店38码", "tgt": "발발 170cm/49kg/전점 38 사이즈"}], {})
    row = out["rows"][0]
    assert row["ko"] == "모델 170cm · 49kg · 38 사이즈 착용" and row["from"] == "glossary" and out["calls"] == 0
