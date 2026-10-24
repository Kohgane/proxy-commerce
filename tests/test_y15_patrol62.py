"""Y15 순찰 62(오너 2026-10-24) — 요청 샘플 간격 기본 10 · 사전 夹灯/床头/宿舍 · 한자 브랜드 직역 금지(左马 → 「왼쪽 마우스」)."""
from src.collectors import ko_polish as K
from src.services.image_text_glossary import option_value_tokens

# d5af2185 실제 상품명(10-23) — 번역기가 브랜드 左马를 「왼쪽 마우스」, 床头를 「침대 머리판」으로 옮겼다
_KO = "왼쪽 마우스 충전식 스탠드, 눈 보호, 장시간 사용 가능, 자석식, 침대 머리판 다기능, 무타공, 학생 기숙사 독서등, 작업용"
_SRC = "左马充电台灯护眼长续航磁吸床头多功能免打孔学生宿舍阅读灯工作"


def test_request_sample_default_every_10(monkeypatch):
    import importlib
    import src.order_webhook as W
    monkeypatch.delenv("REQ_PROBE_EVERY", raising=False)
    src = open(W.__file__, encoding="utf-8").read()
    assert 'os.getenv("REQ_PROBE_EVERY", "10") or 10' in src          # 2시간 77건 → 샘플 줄 7개(100이면 0개였다)
    assert importlib.import_module("src.order_webhook")._REQ_PROBE_EVERY in (10, int(__import__("os").getenv("REQ_PROBE_EVERY", "10")))


def test_hanzi_brand_literal_is_dropped_and_bed_head_fixed():
    out = K.fix_by_source(_KO, _SRC)
    assert "왼쪽 마우스" not in out and out.startswith("충전식 스탠드")
    assert "침대 머리맡" in out and "머리판" not in out
    # 원문에 그 브랜드가 없으면 같은 낱말을 건드리지 않는다(진짜 「왼쪽 마우스」 상품)
    assert K.fix_by_source("왼쪽 마우스 손목 받침대", "左手鼠标护腕垫").startswith("왼쪽 마우스")


def test_clip_lamp_words_only_when_source_has_them():
    assert K.fix_by_source("화이트 스포트라이트 포함 독서등", "白色夹灯版阅读灯") == "화이트 집게등 독서등"
    assert K.fix_by_source("스포트라이트 무대 조명", "舞台射灯") == "스포트라이트 무대 조명"


def test_option_value_tokens_cover_the_three_words():
    assert option_value_tokens("夹灯 宿舍床头") == "집게등 기숙사 침대 머리맡"
    assert option_value_tokens("白色 夹灯") == "화이트 집게등"
    assert option_value_tokens("白色【夹灯版】宿舍床头") == ""                # 표에 없는 글자(版)가 남으면 짓지 않는다
