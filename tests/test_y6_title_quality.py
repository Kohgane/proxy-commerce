"""Y6(오너 2026-10-04) — 제목 번역 품질: 고유명사 오역 사전 · 영화·게임·애니 IP 상표 게이트 · 쿠팡 상품명 20자 하한.

실측: 【BLACKHOLES】黑洞小夜灯星际穿越电影周边摆件装饰模型手办宇宙 → 번역 제목에 「스타트렉」(星际穿越=인터스텔라 오역)·
「벽등」(小夜灯=무드등)·「주변」(周边=굿즈), 쿠팡 상품명 자동 생성은 「블랙홀 미니 벽등」 9자.
"""
from __future__ import annotations

import json

from src.collectors import ko_polish as kp

SRC = "【BLACKHOLES】黑洞小夜灯星际穿越电影周边摆件装饰模型手办宇宙"
# 번역기가 실제로 낸 모양(오역 그대로) — 오너 캡처의 「블랙홀 미니 벽등」·「스타트렉」
BAD_KO = "블랙홀 미니 벽등, 스타트렉 영화 주변 장식품 장식 모델 피규어 우주"


def setup_function(_f):
    kp.reset_cache()


def test_dictionary_and_ip_removal_apply_with_source():
    out = kp.polish_ko(BAD_KO, src=SRC)
    for w in ("블랙홀", "무드등", "피규어", "장식 소품"):
        assert w in out, out
    for w in ("스타트렉", "인터스텔라", "벽등", "주변", "영화"):
        assert w not in out, out


def test_ip_name_never_reaches_the_translator():
    sent = kp.strip_cn(SRC)
    assert "星际穿越" not in sent and "黑洞小夜灯" in sent


def test_dictionary_needs_the_source_han():
    """원문에 小夜灯이 없으면 진짜 벽등은 그대로(원문을 보고만 고친다)."""
    assert kp.polish_ko("LED 벽등 실내 조명", src="LED壁灯 室内照明") == "LED 벽등 실내 조명"
    assert kp.polish_ko("LED 벽등 실내 조명") == "LED 벽등 실내 조명"


def test_korean_common_nouns_are_not_ip():
    """원피스(드레스)·마블(대리석 무늬)은 IP로 보지 않는다 — 제목·검색어가 지워지면 안 된다."""
    assert kp.polish_ko("마블 패턴 세라믹 접시") == "마블 패턴 세라믹 접시"
    assert kp.polish_ko("여름 린넨 원피스") == "여름 린넨 원피스"
    assert kp.ip_hits("여름 린넨 원피스 마블 접시") == []
    assert kp.clean_tags(["원피스", "린넨"], "여름 린넨 원피스") == ["원피스", "린넨"]
    assert kp.ip_hits("漫威 钢铁侠 手办") == ["마블 코믹스"] and kp.ip_hits("宝可梦 皮卡丘") == ["포켓몬"]


def test_trademark_hold_in_readiness():
    from src.seller_console.upload_dispatcher import UploadDispatcher
    pd = {"title_src": SRC, "title": kp.polish_ko(BAD_KO, src=SRC), "images": ["https://x/a.jpg"], "price": "69.9"}
    holds = UploadDispatcher.readiness_holds(pd, "coupang")
    tm = [h for h in holds if h["short"].startswith("상표 확인 보류")]
    assert tm and "인터스텔라" in tm[0]["short"] and tm[0]["fix"] == "trademark"
    assert "인터스텔라" not in pd["title"]                                 # 제목에선 이미 지웠다


def test_coupang_name_floor_and_dictionary_first():
    from src.uploaders import coupang_title as ct
    r = ct.build_name({"title_src": SRC, "title_ko": BAD_KO})
    name = r["name"]
    assert len(name) >= ct.MIN_LEN, name
    assert name.startswith("블랙홀 미니 무드등") and "피규어" in name
    for w in ("벽등", "스타트렉", "인터스텔라"):
        assert w not in name
    assert not r["warnings"]


def test_coupang_name_short_warns_when_nothing_to_add():
    from src.uploaders import coupang_title as ct
    r = ct.build_name({"title_ko": "무드등"})
    assert r["name"] == "무드등" and any("20자보다 짧아요" in w for w in r["warnings"])


def test_translator_job_stores_fixed_title(monkeypatch):
    """번역 워커(자동·「번역하고 다시 검증」)가 저장하는 제목도 사전·IP 삭제를 거친다."""
    from src.seller_console import collect_history_store as S
    from src.seller_console.ai import translator as T
    from src.services import option_translate_auto as A
    seller = "owner-y6-job"
    iid = S.append(source="extension", url="https://detail.tmall.hk/item.htm?id=1077964821879", seller_id=seller,
                   title=SRC, price="69.90", currency="CNY", extra={"title": SRC, "options": []})
    monkeypatch.setattr(T.AITranslator, "translate_product",
                        lambda self, p: {"title_ko": BAD_KO, "provider": "papago"})
    res = A.translate_now(seller, iid)
    assert res["status"] in ("done", "queued", "partial"), res
    ex = json.loads(S.get(iid, seller_ids={seller})["extra_json"])
    t = ex.get("title_ko") or ""
    assert "무드등" in t and "스타트렉" not in t and "벽등" not in t, t


def test_phone_card_shows_trademark_hold_and_fixed_name():
    from src.order_webhook import app
    from src.seller_console import collect_history_store as S
    seller = "owner-y6-m5"
    ex = {"title": SRC, "title_ko": BAD_KO, "price": "69.90", "currency": "CNY", "images": ["https://x/a.jpg"]}
    iid = S.append(source="extension", url="https://detail.tmall.hk/item.htm?id=1077964821879", seller_id=seller,
                   title=BAD_KO, price="69.90", currency="CNY", extra=ex)
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"] = seller
    h = c.get(f"/seller/m/item/{iid}").get_data(as_text=True)
    assert "상표 확인 보류(인터스텔라)" in h
    assert "블랙홀 미니 무드등" in h and "스타트렉" not in h.split('data-role="m5-coupang-name"')[1][:300]
