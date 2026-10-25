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


# ── 옵션 값·상품명(순찰 99 운영 실측 5d1b6679) ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,want", [
    ("36 80-105斤", "36 40~52.5kg"),
    ("38 发发码数-105-110斤", "38 52.5~55kg"),                   # 가게 꼬리표 「发发码数-」는 뗀다
    ("42 120-135斤", "42 60~67.5kg"),
    ("均码", "프리사이즈"),
])
def test_option_value_rule_converts_jin(value, want):
    from src.collectors import ko_polish as kp
    assert kp.option_value(value)["value"] == want


def test_translator_output_jin_is_fixed():
    from src.collectors import ko_polish as kp
    assert kp.strip_size_tag(kp.fix_jin_ko("38 发发码数-105-110斤", "38 발발 코드 수 - 105-110근")) == "38 발발 코드 수 - 52.5~55kg"
    assert kp.fix_jin_ko("36 80-105斤", "36 80-105kg") == "36 40~52.5kg"
    assert kp.fix_jin_ko("샴페인", "샴페인") == "샴페인"


def test_latin_han_shop_brand_is_not_transliterated():
    from src.collectors import ko_polish as kp
    src = "Taffa 唐发发 夏季新款【真丝云纱连衣裙】飘逸优雅无袖"
    sent, info = kp.title_for_translator(src, {"shop_name": "Taffa 唐发发"})
    assert "唐发发" not in sent and "Taffa" not in sent          # 번역기엔 브랜드를 떼고 보낸다(음차 금지)
    assert info["latin"] == "Taffa" and info["han"] == "唐发发"
    assert kp.attach_brand("여름 신상 실크 원피스", info) == "Taffa 여름 신상 실크 원피스"
    assert kp.brand_prefix("小米 手机", {"shop_name": "小米旗舰店"})["latin"] == "XIAOMI"   # 기존 한자 브랜드 경로 그대로


# ── 상세 사진: 중국 가게 배송·반품 약관은 등록에서 뺀다(순찰 99 상세 17·18) ──────────────────────────────────────

def test_shop_policy_pages_are_excluded():
    from src.services import detail_image_plan as d
    why = d.text_exclusion("[服务细则] 品牌甄选顺丰速运为您免费提供配送服务,送货区域仅覆盖中国大陆地区 退货与退款 自签收起7天无理由退换货")
    assert why.startswith("가게 안내")
    why2 = d.text_exclusion("明确的穿着痕迹或污渍(香水味等)强制退货并拒绝沟通的 退换货 在线客服 반품 및 환불")
    assert why2.startswith("가게 안내")


def test_single_policy_word_does_not_exclude():
    from src.services import detail_image_plan as d
    assert d.text_exclusion("面料:100%桑蚕丝 售后卡 洗护 Details") == ""          # 조각 하나(售后卡)만 — 소재 설명
    assert d.text_exclusion("Size Guide 衣长 胸围 cm") == ""
    assert d.text_exclusion("天猫国际邀请入驻 品牌奖").startswith("스토어·수상 배너")    # 기존 규칙 그대로


def test_polished_version_with_unconverted_jin_is_redone():
    from src.services import image_edit as IE
    from src.services import image_polish as P
    boxes = [{"src": "80-105斤", "tgt": "80-105kg"}, {"src": "衣长", "tgt": "의장"}]
    good = {"by": P.POLISH_BY, "render": "local", "render_v": IE.RENDER_V, "ops": [{"id": "t0", "action": "text", "text": "40~52.5kg"}]}
    bad_drawn = dict(good, ops=[{"id": "t0", "action": "text", "text": "80-105근"}])
    not_drawn = dict(good, ops=[{"id": "t1", "action": "text", "text": "총장"}])   # 斤 상자를 안 그려 텐센트 「80-105kg」이 남음
    assert P._redo_polish(good, boxes) is False
    assert P._redo_polish(bad_drawn, boxes) is True
    assert P._redo_polish(not_drawn, boxes) is True


def test_jin_rule_beats_cached_ai_answer(monkeypatch):
    """순찰 99d(운영 10-25 18:20 재렌더 실측): 옛 다듬기 캐시 「80-105근」이 斤 환산 규칙을 덮어 또 「근」으로 그렸다."""
    from src.ai import llm
    from src.services import image_polish as P
    monkeypatch.setattr(llm, "anthropic_ready", lambda: False)
    boxes = [{"id": "t22", "src": "80-105斤", "tgt": "80-105kg"}]
    cache = {("80-105斤", "80-105kg"): {"ai": "80-105근", "pv": P.PROMPT_VER, "tries": 1, "tmt": ""}}
    out = P.polish_boxes(boxes, {"outbound": True, "rule": None}, cache=cache)
    assert out["rows"][0]["ko"] == "40~52.5kg" and out["rows"][0]["from"] == "glossary"
